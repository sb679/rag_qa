#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture WeChat article content from the Windows desktop client.

This script mirrors the Android capture package format so the existing
import_wechat_mobile_package.py importer can continue to work unchanged.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


DEFAULT_PROFILE_STORE = Path("data/wechat_collector/desktop_capture/device_profiles.json")


def _normalize_account_id(raw: str) -> str:
    text = (raw or "").strip().lower()
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-"}:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    normalized = "".join(cleaned).strip("_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized[:64]


def _normalize_operator_id(raw: str) -> str:
    return _normalize_account_id(raw)


def _normalize_machine_name(raw: str) -> str:
    return _normalize_account_id(raw) or "desktop"


def _utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_match_text(raw: str) -> str:
    return re.sub(r"\s+", "", str(raw or "")).strip().lower()


def _split_match_terms(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    terms: List[str] = []
    whole = _normalize_match_text(text)
    if len(whole) >= 2:
        terms.append(whole)
    for chunk in re.split(r"[，,。！？!？、；;:：/|\s]+", text):
        normalized = _normalize_match_text(chunk)
        if len(normalized) < 2 or normalized in terms:
            continue
        terms.append(normalized)
    return terms


_GENERIC_WINDOW_TEXTS = {
    _normalize_match_text("微信"),
    _normalize_match_text("weixin"),
    _normalize_match_text("wechat"),
}


def _assess_context_relevance(window_text: str, ocr_text: str, search_query: str, article_title: str) -> Dict[str, object]:
    combined_text = "\n".join(part for part in [window_text, ocr_text] if part).strip()
    normalized = _normalize_match_text(combined_text)
    matched_terms: List[str] = []
    score = 0.0

    title_terms = _split_match_terms(article_title)
    if title_terms:
        whole_title = title_terms[0]
        if whole_title and whole_title in normalized:
            matched_terms.append(str(article_title or "").strip())
            score += 8.0
        for term in title_terms[1:]:
            if term in normalized:
                matched_terms.append(term)
                score += 3.0

    query_term = _normalize_match_text(search_query)
    if len(query_term) >= 2 and query_term in normalized:
        matched_terms.append(str(search_query or "").strip())
        score += 2.0

    if not combined_text:
        reason = "empty_window"
    elif not matched_terms:
        reason = "no_expected_terms"
    else:
        reason = "matched"

    return {
        "score": round(score, 2),
        "matched_terms": matched_terms,
        "reason": reason,
        "window_text_length": len(window_text or ""),
        "ocr_text_length": len(ocr_text or ""),
    }


def _default_context_threshold(search_query: str, article_title: str) -> float:
    if str(article_title or "").strip():
        return 4.0
    if str(search_query or "").strip():
        return 2.0
    return 0.0


def _group_ocr_lines(entries: List[Dict[str, object]], tolerance: float = 24.0) -> List[Dict[str, object]]:
    lines: List[Dict[str, object]] = []
    for entry in sorted(entries, key=lambda item: (float(item.get("cy", 0.0)), float(item.get("cx", 0.0)))):
        cy = float(entry.get("cy", 0.0))
        text = str(entry.get("text", "") or "").strip()
        if not text:
            continue
        if lines and abs(cy - float(lines[-1]["cy"])) <= tolerance:
            lines[-1]["items"].append(entry)
            texts = [str(item.get("text", "") or "").strip() for item in lines[-1]["items"]]
            lines[-1]["text"] = " ".join(part for part in texts if part)
            lines[-1]["cy"] = sum(float(item.get("cy", 0.0)) for item in lines[-1]["items"]) / len(lines[-1]["items"])
        else:
            lines.append({"cy": cy, "text": text, "items": [entry]})
    return lines


def _pick_search_result_from_ocr(entries: List[Dict[str, object]], query: str) -> Optional[Tuple[int, int]]:
    normalized_query = _normalize_match_text(query)
    if len(normalized_query) < 2:
        return None

    lines = _group_ocr_lines(entries)
    preferred_markers = [
        _normalize_match_text("公众号"),
        _normalize_match_text("订阅号"),
        _normalize_match_text("服务号"),
    ]
    rejected_markers = [
        _normalize_match_text("群聊"),
        _normalize_match_text("群"),
        _normalize_match_text("聊天记录"),
        _normalize_match_text("最近记录"),
        _normalize_match_text("最近使用"),
    ]

    preferred_min_y: Optional[float] = None
    rejected_ranges: List[Tuple[float, float]] = []
    for index, line in enumerate(lines):
        normalized_line = _normalize_match_text(str(line.get("text", "") or ""))
        if any(marker and marker in normalized_line for marker in preferred_markers):
            preferred_min_y = float(line.get("cy", 0.0))
        if any(marker and marker in normalized_line for marker in rejected_markers):
            start_y = float(line.get("cy", 0.0))
            next_y = float(lines[index + 1].get("cy", start_y + 90.0)) if index + 1 < len(lines) else start_y + 120.0
            rejected_ranges.append((start_y - 18.0, next_y - 8.0))

    candidates: List[Tuple[int, float, Dict[str, object]]] = []
    for entry in entries:
        text = str(entry.get("text", "") or "").strip()
        normalized_text = _normalize_match_text(text)
        if normalized_query not in normalized_text:
            continue
        cy = float(entry.get("cy", 0.0))
        if preferred_min_y is not None and cy <= preferred_min_y + 18.0:
            continue
        if any(start <= cy <= end for start, end in rejected_ranges):
            continue
        score = 0
        if normalized_text == normalized_query:
            score += 4
        if preferred_min_y is not None:
            score += 2
        score += max(0, 2 - abs(len(normalized_text) - len(normalized_query)))
        candidates.append((score, cy, entry))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    winner = candidates[0][2]
    return int(float(winner.get("cx", 0.0))), int(float(winner.get("cy", 0.0)))


def _emit_progress(enabled: bool, event_type: str, **payload) -> None:
    if not enabled:
        return
    print(json.dumps({"type": event_type, **payload}, ensure_ascii=False), flush=True)


def _safe_json_load(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_profile_store(path: Path) -> Dict[str, object]:
    payload = _safe_json_load(path)
    profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    last_profile = str(payload.get("last_profile", "") or "").strip() if isinstance(payload, dict) else ""
    if not isinstance(profiles, dict):
        profiles = {}
    return {
        "profiles": profiles,
        "last_profile": last_profile,
    }


def _save_profile_store(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_profile_name(operator_id: str, account_id: str, machine_name: str) -> str:
    op = _normalize_operator_id(operator_id) or "anonymous"
    acc = _normalize_account_id(account_id) or "default"
    machine = _normalize_machine_name(machine_name)
    return f"{op}__{machine}__{acc}"


def _resolve_profile(store: Dict[str, object], requested_name: str) -> Dict[str, object]:
    profiles = store.get("profiles", {}) if isinstance(store.get("profiles", {}), dict) else {}
    profile_name = (requested_name or "").strip()
    if not profile_name:
        profile_name = str(store.get("last_profile", "") or "").strip()
    if not profile_name:
        return {}
    payload = profiles.get(profile_name, {})
    return payload if isinstance(payload, dict) else {}


def _filter_profiles(store: Dict[str, object], operator_id: str) -> Dict[str, object]:
    profiles = store.get("profiles", {}) if isinstance(store.get("profiles", {}), dict) else {}
    normalized_operator = _normalize_operator_id(operator_id)
    if not normalized_operator:
        return profiles
    filtered: Dict[str, object] = {}
    for name, payload in profiles.items():
        if not isinstance(payload, dict):
            continue
        if _normalize_operator_id(str(payload.get("operator_id", "") or "")) == normalized_operator:
            filtered[name] = payload
    return filtered


def _merge_cli_with_profile(args: argparse.Namespace, profile: Dict[str, object]) -> argparse.Namespace:
    if not profile:
        return args

    if not getattr(args, "operator_id", ""):
        args.operator_id = str(profile.get("operator_id", "") or "")
    if not getattr(args, "account_id", ""):
        args.account_id = str(profile.get("account_id", "") or "")
    if not getattr(args, "display_name", ""):
        args.display_name = str(profile.get("display_name", "") or "")
    if not getattr(args, "search_query", ""):
        args.search_query = str(profile.get("search_query", "") or "")
    if not getattr(args, "article_title", ""):
        args.article_title = str(profile.get("article_title", "") or "")
    if not getattr(args, "source_url", ""):
        args.source_url = str(profile.get("last_source_url", "") or "")
    if not getattr(args, "wechat_path", ""):
        args.wechat_path = str(profile.get("wechat_path", "") or "")
    if not getattr(args, "window_title_re", ""):
        args.window_title_re = str(profile.get("window_title_re", "") or "")
    if not getattr(args, "steps", 0) and profile.get("steps"):
        try:
            args.steps = int(profile.get("steps", 0) or 0)
        except Exception:
            pass
    if not getattr(args, "wait_sec", 0.0) and profile.get("wait_sec"):
        try:
            args.wait_sec = float(profile.get("wait_sec", 0.0) or 0.0)
        except Exception:
            pass
    if not getattr(args, "settle_delay_sec", 0.0) and profile.get("settle_delay_sec"):
        try:
            args.settle_delay_sec = float(profile.get("settle_delay_sec", 0.0) or 0.0)
        except Exception:
            pass
    return args


def _persist_profile(
    store_path: Path,
    store: Dict[str, object],
    profile_name: str,
    machine_name: str,
    args: argparse.Namespace,
    session_dir: Path,
) -> None:
    profiles = store.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        store["profiles"] = profiles

    profiles[profile_name] = {
        "profile_name": profile_name,
        "operator_id": getattr(args, "operator_id", ""),
        "machine_name": machine_name,
        "account_id": args.account_id,
        "display_name": (args.display_name or args.account_id).strip() or args.account_id,
        "search_query": (args.search_query or "").strip(),
        "article_title": (args.article_title or "").strip(),
        "last_source_url": (args.source_url or "").strip(),
        "wechat_path": (args.wechat_path or "").strip(),
        "window_title_re": str(args.window_title_re or ""),
        "steps": int(args.steps),
        "wait_sec": float(args.wait_sec),
        "settle_delay_sec": float(args.settle_delay_sec),
        "last_capture_dir": str(session_dir),
        "last_capture_at": _utc_now(),
        "login_hint": "WeChat login state is kept by the Windows desktop client itself. Keep the client logged in for later unattended captures.",
    }
    store["last_profile"] = profile_name
    _save_profile_store(store_path, store)


@dataclass
class CaptureStep:
    step: int
    screenshot_path: str
    ui_dump_path: str
    ui_text: str
    captured_at: str
    context_score: float = 0.0
    context_matched_terms: List[str] = field(default_factory=list)
    context_reason: str = "unchecked"
    context_recovered: bool = False


class WeChatDesktopAutomator:
    def __init__(self, wechat_path: str = "", window_title_re: str = ".*微信.*", settle_delay_sec: float = 1.0):
        self.wechat_path = str(wechat_path or "").strip()
        self.window_title_re = str(window_title_re or ".*微信.*")
        self.settle_delay_sec = max(0.0, float(settle_delay_sec or 0.0))
        self.backend = "uia"
        self._desktop = None
        self._application = None
        self._keyboard = None
        self._timings = None
        self._ocr_engine = None
        self._ocr_checked = False

    def _ensure_dependencies(self) -> None:
        if self._desktop is not None:
            return
        try:
            from pywinauto import Desktop
            from pywinauto import Application
            from pywinauto import keyboard
            from pywinauto.timings import Timings
        except ImportError as exc:
            raise RuntimeError("缺少 pywinauto，请在 rag_qa/.venv 中安装 pywinauto==0.6.9") from exc
        self._desktop = Desktop
        self._application = Application
        self._keyboard = keyboard
        self._timings = Timings

    def _sleep(self, sec: Optional[float] = None) -> None:
        time.sleep(self.settle_delay_sec if sec is None else max(0.0, float(sec)))

    def _ensure_ocr_engine(self):
        if self._ocr_checked:
            return self._ocr_engine
        self._ocr_checked = True
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            self._ocr_engine = None
            return None
        try:
            self._ocr_engine = RapidOCR()
        except Exception:
            self._ocr_engine = None
        return self._ocr_engine

    def _build_ocr_variants(self, image_path: Path, purpose: str = "generic") -> List[Dict[str, object]]:
        try:
            base_image = Image.open(image_path).convert("RGB")
        except Exception:
            return []

        variants: List[Dict[str, object]] = [{
            "image": base_image.copy(),
            "offset_x": 0,
            "offset_y": 0,
            "scale_x": 1.0,
            "scale_y": 1.0,
        }]

        enhanced_full = ImageOps.grayscale(base_image)
        enhanced_full = enhanced_full.resize((enhanced_full.width * 2, enhanced_full.height * 2), Image.Resampling.LANCZOS)
        enhanced_full = ImageEnhance.Contrast(enhanced_full).enhance(2.2)
        enhanced_full = ImageEnhance.Sharpness(enhanced_full).enhance(2.0)
        enhanced_full = enhanced_full.filter(ImageFilter.SHARPEN)
        variants.append({
            "image": enhanced_full.convert("RGB"),
            "offset_x": 0,
            "offset_y": 0,
            "scale_x": 2.0,
            "scale_y": 2.0,
        })

        if purpose == "search":
            width, height = base_image.size
            left = 0
            top = int(height * 0.10)
            right = int(width * 0.46)
            bottom = int(height * 0.88)
            crop = base_image.crop((left, top, right, bottom))
            variants.append({
                "image": crop.copy(),
                "offset_x": left,
                "offset_y": top,
                "scale_x": 1.0,
                "scale_y": 1.0,
            })

            crop_enhanced = ImageOps.grayscale(crop)
            crop_enhanced = crop_enhanced.resize((crop_enhanced.width * 3, crop_enhanced.height * 3), Image.Resampling.LANCZOS)
            crop_enhanced = ImageEnhance.Contrast(crop_enhanced).enhance(2.6)
            crop_enhanced = ImageEnhance.Sharpness(crop_enhanced).enhance(2.4)
            crop_enhanced = crop_enhanced.filter(ImageFilter.SHARPEN)
            variants.append({
                "image": crop_enhanced.convert("RGB"),
                "offset_x": left,
                "offset_y": top,
                "scale_x": 3.0,
                "scale_y": 3.0,
            })

        return variants

    def _dedupe_ocr_entries(self, entries: List[Dict[str, object]]) -> List[Dict[str, object]]:
        deduped: List[Dict[str, object]] = []
        for entry in sorted(entries, key=lambda item: (-float(item.get("score", 0.0)), len(str(item.get("text", "") or "")))):
            normalized = _normalize_match_text(str(entry.get("text", "") or ""))
            if not normalized:
                continue
            cx = float(entry.get("cx", 0.0))
            cy = float(entry.get("cy", 0.0))
            duplicated = False
            for existing in deduped:
                if _normalize_match_text(str(existing.get("text", "") or "")) != normalized:
                    continue
                if abs(float(existing.get("cx", 0.0)) - cx) <= 18.0 and abs(float(existing.get("cy", 0.0)) - cy) <= 18.0:
                    duplicated = True
                    break
            if not duplicated:
                deduped.append(entry)
        deduped.sort(key=lambda item: (float(item.get("cy", 0.0)), float(item.get("cx", 0.0))))
        return deduped

    def _candidate_windows(self) -> List[object]:
        self._ensure_dependencies()
        windows = []
        for window in self._desktop(backend=self.backend).windows():
            try:
                title = str(window.window_text() or "").strip()
            except Exception:
                continue
            if not title:
                continue
            if re.search(self.window_title_re, title, flags=re.IGNORECASE):
                windows.append(window)
        return windows

    def connect_or_launch(self, timeout_sec: float = 20.0):
        self._ensure_dependencies()
        deadline = time.time() + max(1.0, float(timeout_sec or 1.0))
        last_error: Optional[Exception] = None
        if self.wechat_path:
            path_obj = Path(self.wechat_path).expanduser()
            if not path_obj.exists():
                raise RuntimeError(f"微信桌面端程序不存在: {path_obj}")
            try:
                subprocess.Popen([str(path_obj)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as exc:
                last_error = exc
        while time.time() < deadline:
            windows = self._candidate_windows()
            if windows:
                window = windows[0]
                self._activate_window(window)
                return window
            self._sleep(1.0)
        if last_error is not None:
            raise RuntimeError(f"无法启动或连接微信桌面端: {last_error}") from last_error
        raise RuntimeError("未找到微信桌面端窗口，请先登录并打开 PC 微信")

    def _activate_window(self, window) -> None:
        try:
            if window.is_minimized():
                window.restore()
        except Exception:
            pass
        try:
            window.set_focus()
        except Exception:
            pass
        self._sleep()

    def _iter_descendants(self, window, depth: int = 3) -> Iterable[object]:
        queue = [(window, 0)]
        while queue:
            current, level = queue.pop(0)
            if level > depth:
                continue
            try:
                children = current.children()
            except Exception:
                children = []
            for child in children:
                yield child
                queue.append((child, level + 1))

    def _best_text_match(self, window, query: str, exact: bool = False):
        keyword = str(query or "").strip()
        if not keyword:
            return None
        scored: List[tuple[int, object]] = []
        for item in self._iter_descendants(window, depth=4):
            try:
                text = str(item.window_text() or "").strip()
            except Exception:
                continue
            if not text:
                continue
            if exact and text == keyword:
                scored.append((300, item))
                continue
            if keyword == text:
                scored.append((280, item))
                continue
            if keyword in text:
                scored.append((220 - abs(len(text) - len(keyword)), item))
                continue
            if text in keyword and len(text) >= 2:
                scored.append((140 - abs(len(text) - len(keyword)), item))
        if not scored:
            return None
        scored.sort(key=lambda entry: entry[0], reverse=True)
        return scored[0][1]

    def _click_control(self, control) -> None:
        try:
            control.click_input()
            self._sleep()
            return
        except Exception:
            pass
        try:
            control.invoke()
            self._sleep()
            return
        except Exception:
            pass
        raise RuntimeError("无法点击目标控件")

    def _click_point(self, x: int, y: int) -> None:
        try:
            from pywinauto import mouse
        except ImportError as exc:
            raise RuntimeError("缺少 pywinauto，请在 rag_qa/.venv 中安装 pywinauto==0.6.9") from exc
        mouse.click(button="left", coords=(int(x), int(y)))
        self._sleep()

    def _fallback_search_box_point(self, window) -> tuple[int, int]:
        rect = window.rectangle()
        return rect.left + 220, rect.top + 82

    def _fallback_public_account_result_point(self, window) -> tuple[int, int]:
        rect = window.rectangle()
        return rect.left + 240, rect.top + 725

    def _find_search_edit(self, window):
        candidates = []
        for item in self._iter_descendants(window, depth=4):
            try:
                info = item.element_info
                control_type = str(getattr(info, "control_type", "") or "")
                text = str(item.window_text() or "").strip()
            except Exception:
                continue
            if control_type == "Edit":
                score = 100
                if "搜索" in text:
                    score += 100
                candidates.append((score, item))
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        return candidates[0][1]

    def _set_text(self, control, value: str) -> None:
        try:
            control.set_edit_text("")
            control.type_keys(value, with_spaces=True, set_foreground=True)
            self._sleep()
            return
        except Exception:
            pass
        self._activate_window(control.top_level_parent())
        self._keyboard.send_keys("^a")
        self._keyboard.send_keys("{BACKSPACE}")
        self._keyboard.send_keys(value, with_spaces=True, pause=0.02)
        self._sleep()

    def _prepare_search_query(self, window, keyword: str) -> None:
        edit = self._find_search_edit(window)
        if edit is not None:
            try:
                edit.click_input()
            except Exception:
                pass
            self._set_text(edit, keyword)
            return
        fallback_x, fallback_y = self._fallback_search_box_point(window)
        self._click_point(fallback_x, fallback_y)
        self._keyboard.send_keys("^a")
        self._keyboard.send_keys("{BACKSPACE}")
        self._keyboard.send_keys(keyword, with_spaces=True, pause=0.02)
        self._sleep()

    def _capture_temp_entries(self, window) -> List[Dict[str, object]]:
        with tempfile.NamedTemporaryFile(prefix="wechat_window_", suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            image = window.capture_as_image()
            if image is None:
                return []
            image.save(temp_path)
            return self._ocr_entries_for_image(temp_path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _right_pane_has_meaningful_content(self, window) -> bool:
        rect = window.rectangle()
        split_x = rect.left + int((rect.right - rect.left) * 0.55)
        control_texts: List[str] = []
        try:
            for control in window.descendants():
                try:
                    control_rect = control.rectangle()
                    center_x = (control_rect.left + control_rect.right) / 2
                    if center_x < split_x:
                        continue
                    text = (control.window_text() or "").strip()
                    normalized = _normalize_match_text(text)
                    if len(normalized) < 2:
                        continue
                    if normalized in _GENERIC_WINDOW_TEXTS:
                        continue
                    control_texts.append(text)
                except Exception:
                    continue
        except Exception:
            control_texts = []
        long_control_texts = [text for text in control_texts if len(_normalize_match_text(text)) >= 4]
        if len(long_control_texts) >= 2 or len(control_texts) >= 4:
            return True
        entries = self._capture_temp_entries(window)
        useful = []
        for entry in entries:
            text = str(entry.get("text", "") or "").strip()
            cx = rect.left + float(entry.get("cx", 0.0))
            if cx < split_x:
                continue
            normalized = _normalize_match_text(text)
            if len(normalized) < 2:
                continue
            if normalized in _GENERIC_WINDOW_TEXTS:
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}", text):
                continue
            useful.append(text)
        long_items = [text for text in useful if len(_normalize_match_text(text)) >= 4]
        return len(long_items) >= 2 or len(useful) >= 4

    def _target_context_is_stable(self, window, checks: int = 4, interval_sec: float = 0.6) -> bool:
        consecutive_hits = 0
        for index in range(max(1, checks)):
            try:
                current_window = self.connect_or_launch(timeout_sec=1.0)
            except Exception:
                current_window = window
            if self._right_pane_has_meaningful_content(current_window):
                consecutive_hits += 1
                if consecutive_hits >= 2:
                    return True
            else:
                consecutive_hits = 0
            if index < checks - 1:
                self._sleep(interval_sec)
        return False

    def _try_open_search_target(self, window, keyword: str, *, use_ocr: bool, use_text_match: bool, use_fixed_point: bool) -> bool:
        self._prepare_search_query(window, keyword)
        self._sleep(1.2)
        if use_ocr:
            ocr_point = self._ocr_search_result_point(window, keyword)
            if ocr_point is not None:
                self._click_point(*ocr_point)
                self._sleep(1.0)
                if self._target_context_is_stable(window):
                    return True
        if use_text_match:
            target = self._best_text_match(window, keyword)
            if target is not None:
                try:
                    self._click_control(target)
                    self._sleep(1.0)
                    if self._target_context_is_stable(window):
                        return True
                except Exception:
                    pass
        if use_fixed_point:
            fallback_x, fallback_y = self._fallback_public_account_result_point(window)
            self._click_point(fallback_x, fallback_y)
            self._sleep(1.0)
            if self._target_context_is_stable(window):
                return True
        return False

    def open_chat(self, search_query: str) -> None:
        keyword = str(search_query or "").strip()
        if not keyword:
            return
        window = self.connect_or_launch(timeout_sec=2.0)
        self._activate_window(window)
        strategies = [
            {"use_ocr": True, "use_text_match": False, "use_fixed_point": False},
            {"use_ocr": False, "use_text_match": True, "use_fixed_point": False},
            {"use_ocr": False, "use_text_match": False, "use_fixed_point": True},
        ]
        for strategy in strategies:
            if self._try_open_search_target(window, keyword, **strategy):
                return
        raise RuntimeError(f"未能稳定打开搜索目标: {keyword}")

    def open_history(self) -> str:
        window = self.connect_or_launch(timeout_sec=2.0)
        self._activate_window(window)
        patterns = ["历史消息", "全部消息", "聊天信息", "更多消息"]
        for label in patterns:
            target = self._best_text_match(window, label, exact=False)
            if target is None:
                continue
            try:
                self._click_control(target)
                return label
            except Exception:
                continue
        raise RuntimeError("未找到历史消息入口，请先在 PC 微信中打开公众号会话或资料页")

    def open_article(self, article_title: str) -> str:
        keyword = str(article_title or "").strip()
        if not keyword:
            return ""
        window = self.connect_or_launch(timeout_sec=2.0)
        self._activate_window(window)
        attempted_terms = _split_match_terms(keyword) or [keyword]
        for term in attempted_terms:
            target = self._best_text_match(window, term, exact=False)
            if target is None:
                continue
            try:
                self._click_control(target)
                self._sleep(1.2)
                return term
            except Exception:
                continue
        raise RuntimeError(f"未在当前微信窗口中找到文章标题: {keyword}")

    def current_reader_window(self):
        windows = self._candidate_windows()
        if not windows:
            raise RuntimeError("未找到微信桌面端窗口")
        active = None
        for window in windows:
            try:
                if window.has_focus():
                    active = window
                    break
            except Exception:
                continue
        return active or windows[0]

    def capture_window(self, output_path: Path) -> str:
        window = self.current_reader_window()
        self._activate_window(window)
        title = str(window.window_text() or "").strip()
        image = window.capture_as_image()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        return title

    def extract_window_text(self) -> str:
        window = self.current_reader_window()
        values: List[str] = []
        seen = set()
        for item in [window, *list(self._iter_descendants(window, depth=5))]:
            try:
                text = " ".join(str(item.window_text() or "").split()).strip()
            except Exception:
                continue
            if len(text) < 2 or text in seen:
                continue
            seen.add(text)
            values.append(text)
        return "\n".join(values)

    def extract_screenshot_text(self, image_path: Path) -> str:
        values: List[str] = []
        seen = set()
        for item in self._ocr_entries_for_image(image_path, purpose="content"):
            normalized = " ".join(str(item.get("text", "") or "").split()).strip()
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            values.append(normalized)
        return "\n".join(values)

    def _ocr_entries_for_image(self, image_path: Path, purpose: str = "generic") -> List[Dict[str, object]]:
        engine = self._ensure_ocr_engine()
        if engine is None:
            return []
        entries: List[Dict[str, object]] = []
        for variant in self._build_ocr_variants(image_path, purpose=purpose):
            variant_image = variant["image"]
            offset_x = int(variant.get("offset_x", 0))
            offset_y = int(variant.get("offset_y", 0))
            scale_x = float(variant.get("scale_x", 1.0))
            scale_y = float(variant.get("scale_y", 1.0))
            with tempfile.NamedTemporaryFile(prefix="wechat_ocr_variant_", suffix=".png", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            try:
                variant_image.save(temp_path)
                try:
                    result, _ = engine(str(temp_path))
                except Exception:
                    result = []
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            for item in result or []:
                try:
                    box, text, score = item
                except Exception:
                    continue
                normalized = " ".join(str(text or "").split()).strip()
                if not normalized:
                    continue
                center_x = (sum(float(point[0]) for point in box) / 4) / max(1.0, scale_x)
                center_y = (sum(float(point[1]) for point in box) / 4) / max(1.0, scale_y)
                entries.append({
                    "text": normalized,
                    "score": float(score),
                    "cx": center_x + offset_x,
                    "cy": center_y + offset_y,
                })
        return self._dedupe_ocr_entries(entries)

    def _ocr_search_result_point(self, window, search_query: str) -> Optional[tuple[int, int]]:
        if not str(search_query or "").strip():
            return None
        with tempfile.NamedTemporaryFile(prefix="wechat_search_", suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            image = window.capture_as_image()
            if image is None:
                return None
            image.save(temp_path)
            entries = self._ocr_entries_for_image(temp_path, purpose="search")
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        point = _pick_search_result_from_ocr(entries, search_query)
        if point is None:
            return None
        rect = window.rectangle()
        return rect.left + point[0], rect.top + point[1]

    def recover_article_context(self, search_query: str, article_title: str, skip_history: bool) -> Dict[str, object]:
        actions: List[str] = []
        errors: List[str] = []
        if str(search_query or "").strip():
            try:
                self.open_chat(search_query)
                actions.append("reopen_chat")
            except Exception as exc:
                errors.append(f"open_chat: {exc}")
        if not skip_history:
            try:
                history_label = self.open_history()
                actions.append(f"open_history:{history_label}")
            except Exception as exc:
                errors.append(f"open_history: {exc}")
        if str(article_title or "").strip():
            try:
                opened_label = self.open_article(article_title)
                actions.append(f"open_article:{opened_label}")
            except Exception as exc:
                errors.append(f"open_article: {exc}")
        return {
            "actions": actions,
            "errors": errors,
            "recovered": bool(actions),
        }

    def scroll_reader(self) -> str:
        window = self.current_reader_window()
        self._activate_window(window)
        self._keyboard.send_keys("{PGDN}")
        self._sleep(1.0)
        return "page_down"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture WeChat article pages from the Windows desktop client")
    parser.add_argument("--account-id", default="", help="Target EduRAG account_id")
    parser.add_argument("--operator-id", default="", help="Operator/user identifier for multi-user profile isolation")
    parser.add_argument("--display-name", default="", help="Optional display name")
    parser.add_argument("--search-query", default="", help="WeChat desktop search keyword for selecting the公众号会话")
    parser.add_argument("--article-title", default="", help="Article title or title fragment to click after entering the history view")
    parser.add_argument("--source-url", default="", help="Optional article URL stored into the package metadata")
    parser.add_argument("--title", default="", help="Optional manual title override")
    parser.add_argument("--author", default="", help="Optional manual author")
    parser.add_argument("--published-at", default="", help="Optional manual publish time")
    parser.add_argument("--body-text", default="", help="Optional inline body text when you already have a trusted copy")
    parser.add_argument("--body-text-file", default="", help="Optional local UTF-8 text file with the article body")
    parser.add_argument("--wechat-path", default="", help="Optional WeChat.exe path; when omitted the script connects to an existing window")
    parser.add_argument("--window-title-re", default=".*微信.*", help="Regex used to find the WeChat desktop window")
    parser.add_argument("--steps", type=int, default=4, help="Number of capture steps/screenshots")
    parser.add_argument("--wait-sec", type=float, default=0.0, help="Optional wait time before each capture")
    parser.add_argument("--settle-delay-sec", type=float, default=1.0, help="Wait time after each UI action before continuing")
    parser.add_argument("--launch-timeout-sec", type=float, default=20.0, help="Max time to wait for the WeChat window to appear")
    parser.add_argument("--auto-scroll", action="store_true", help="Automatically page down between capture steps")
    parser.add_argument("--skip-history", action="store_true", help="Do not try to click the history entry; capture from the current article window directly")
    parser.add_argument("--profile", default="", help="Remembered profile name; defaults to last used profile or account_id")
    parser.add_argument(
        "--profile-store",
        default=str(DEFAULT_PROFILE_STORE).replace("\\", "/"),
        help="JSON file that stores remembered desktop capture profiles",
    )
    parser.add_argument("--list-profiles", action="store_true", help="List remembered profiles and exit")
    parser.add_argument("--forget-profile", action="store_true", help="Delete the selected remembered profile and exit")
    parser.add_argument("--no-remember", action="store_true", help="Do not save/update the remembered profile after capture")
    parser.add_argument("--json-output", action="store_true", help="Print a machine-readable JSON result instead of human text")
    parser.add_argument("--progress-json", action="store_true", help="Emit JSON progress lines for each major capture step")
    parser.add_argument("--disable-context-check", action="store_true", help="Do not validate whether the current page still matches the target article")
    parser.add_argument("--disable-auto-recover", action="store_true", help="Do not try to reopen the target page when the current page looks irrelevant")
    parser.add_argument("--context-score-threshold", type=float, default=0.0, help="Override the minimum relevance score required before a capture step is considered on-target")
    parser.add_argument(
        "--output-dir",
        default="data/wechat_collector/desktop_capture",
        help="Base output directory for desktop capture packages",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    profile_store_path = Path(args.profile_store).expanduser().resolve()
    profile_store = _load_profile_store(profile_store_path)

    if args.list_profiles:
        profiles = _filter_profiles(profile_store, args.operator_id)
        payload = {
            "last_profile": profile_store.get("last_profile", ""),
            "operator_id": _normalize_operator_id(args.operator_id),
            "profiles": profiles,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    requested_profile_name = (args.profile or "").strip()
    remembered_profile = _resolve_profile(profile_store, requested_profile_name)
    args = _merge_cli_with_profile(args, remembered_profile)

    selected_profile_name = requested_profile_name or str(remembered_profile.get("profile_name", "") or "").strip()
    machine_name = _normalize_machine_name(platform.node())

    if args.forget_profile:
        profile_name = selected_profile_name or _build_profile_name(args.operator_id, _normalize_account_id(args.account_id), machine_name)
        profiles = profile_store.get("profiles", {}) if isinstance(profile_store.get("profiles", {}), dict) else {}
        payload = profiles.get(profile_name, {}) if isinstance(profiles.get(profile_name, {}), dict) else {}
        profile_operator = _normalize_operator_id(str(payload.get("operator_id", "") or ""))
        if profile_name in profiles and (not args.operator_id or profile_operator == _normalize_operator_id(args.operator_id)):
            profiles.pop(profile_name, None)
            if profile_store.get("last_profile", "") == profile_name:
                profile_store["last_profile"] = ""
            _save_profile_store(profile_store_path, profile_store)
            print(f"forgot profile: {profile_name}")
        else:
            print(f"profile not found: {profile_name}")
        return

    account_id = _normalize_account_id(args.account_id)
    if not account_id:
        raise ValueError("account_id is required unless it already exists in a remembered profile")
    args.account_id = account_id
    args.operator_id = _normalize_operator_id(args.operator_id or remembered_profile.get("operator_id", ""))

    automator = WeChatDesktopAutomator(
        wechat_path=args.wechat_path,
        window_title_re=args.window_title_re,
        settle_delay_sec=args.settle_delay_sec,
    )
    window = automator.connect_or_launch(timeout_sec=args.launch_timeout_sec)
    window_title = str(window.window_text() or "").strip()
    _emit_progress(args.progress_json, "desktop_ready", window_title=window_title, account_id=account_id, operator_id=args.operator_id)

    profile_name = selected_profile_name or _build_profile_name(operator_id=args.operator_id, account_id=account_id, machine_name=machine_name)
    context_check_enabled = not args.disable_context_check
    auto_recover_enabled = context_check_enabled and not args.disable_auto_recover
    context_threshold = float(args.context_score_threshold or 0.0) or _default_context_threshold(args.search_query, args.article_title)

    if args.search_query:
        automator.open_chat(args.search_query)
        _emit_progress(args.progress_json, "chat_selected", search_query=str(args.search_query).strip())

    history_label = ""
    if not args.skip_history:
        try:
            history_label = automator.open_history()
            _emit_progress(args.progress_json, "history_opened", entry_label=history_label)
        except Exception as exc:
            _emit_progress(args.progress_json, "history_open_failed", error=str(exc))

    opened_article = ""
    if args.article_title:
        try:
            opened_article = automator.open_article(args.article_title)
            _emit_progress(args.progress_json, "article_opened", article_title=opened_article)
        except Exception as exc:
            _emit_progress(args.progress_json, "article_open_failed", error=str(exc), article_title=str(args.article_title).strip())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = Path(args.output_dir).resolve() / f"{account_id}_{timestamp}"
    screenshots_dir = session_dir / "screenshots"
    dumps_dir = session_dir / "ui_dumps"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    dumps_dir.mkdir(parents=True, exist_ok=True)

    steps: List[CaptureStep] = []
    last_scroll_driver = ""
    _emit_progress(
        args.progress_json,
        "capture_started",
        session_dir=str(session_dir),
        total_steps=max(1, int(args.steps)),
        auto_scroll=bool(args.auto_scroll),
        driver="desktop_page_down",
        context_check_enabled=context_check_enabled,
        auto_recover_enabled=auto_recover_enabled,
        context_threshold=context_threshold,
    )
    for step in range(1, max(1, int(args.steps)) + 1):
        if step > 1 and args.auto_scroll:
            last_scroll_driver = automator.scroll_reader()
            _emit_progress(args.progress_json, "auto_scrolled", step=step, total=max(1, int(args.steps)), scroll_driver=last_scroll_driver)
        if args.wait_sec > 0:
            time.sleep(args.wait_sec)

        screenshot_path = screenshots_dir / f"step_{step:02d}.png"
        ui_dump_path = dumps_dir / f"step_{step:02d}.txt"
        context_recovered = False
        active_title = automator.capture_window(screenshot_path)
        ui_text = automator.extract_window_text()
        ocr_text = automator.extract_screenshot_text(screenshot_path) if context_check_enabled else ""
        context_check = _assess_context_relevance(ui_text, ocr_text, args.search_query, args.article_title) if context_check_enabled else {
            "score": 0.0,
            "matched_terms": [],
            "reason": "disabled",
        }
        if context_check_enabled:
            _emit_progress(
                args.progress_json,
                "context_checked",
                step=step,
                total=max(1, int(args.steps)),
                score=context_check["score"],
                matched_terms=context_check["matched_terms"],
                reason=context_check["reason"],
            )
        if auto_recover_enabled and context_check["score"] < context_threshold and (args.search_query or args.article_title):
            recovery = automator.recover_article_context(
                search_query=args.search_query,
                article_title=args.article_title,
                skip_history=bool(args.skip_history),
            )
            context_recovered = bool(recovery.get("recovered"))
            _emit_progress(
                args.progress_json,
                "context_recovered",
                step=step,
                total=max(1, int(args.steps)),
                actions=recovery.get("actions", []),
                errors=recovery.get("errors", []),
            )
            active_title = automator.capture_window(screenshot_path)
            ui_text = automator.extract_window_text()
            ocr_text = automator.extract_screenshot_text(screenshot_path) if context_check_enabled else ""
            context_check = _assess_context_relevance(ui_text, ocr_text, args.search_query, args.article_title) if context_check_enabled else context_check
        ui_dump_path.write_text(ui_text, encoding="utf-8")
        steps.append(
            CaptureStep(
                step=step,
                screenshot_path=str(screenshot_path.relative_to(session_dir)).replace("\\", "/"),
                ui_dump_path=str(ui_dump_path.relative_to(session_dir)).replace("\\", "/"),
                ui_text=ui_text,
                captured_at=_utc_now(),
                context_score=float(context_check["score"]),
                context_matched_terms=list(context_check["matched_terms"]),
                context_reason=str(context_check["reason"]),
                context_recovered=context_recovered,
            )
        )
        _emit_progress(
            args.progress_json,
            "capture_step",
            step=step,
            total=max(1, int(args.steps)),
            screenshot=str(screenshot_path),
            ui_dump=str(ui_dump_path),
            window_title=active_title,
            context_score=context_check["score"],
            context_reason=context_check["reason"],
            context_recovered=context_recovered,
        )

    body_text = str(args.body_text or "").strip()
    if args.body_text_file:
        body_text = Path(args.body_text_file).expanduser().resolve().read_text(encoding="utf-8")

    manifest = {
        "version": 1,
        "capture_type": "windows_wechat_desktop",
        "captured_at": _utc_now(),
        "machine_name": machine_name,
        "profile_name": profile_name,
        "operator_id": args.operator_id,
        "account_id": account_id,
        "display_name": (args.display_name or account_id).strip() or account_id,
        "source_url": (args.source_url or "").strip(),
        "title": (args.title or args.article_title or "").strip(),
        "author": (args.author or "").strip(),
        "published_at": (args.published_at or "").strip(),
        "body_text": body_text,
        "search_query": (args.search_query or "").strip(),
        "article_title_query": (args.article_title or "").strip(),
        "history_entry": history_label,
        "auto_scroll": bool(args.auto_scroll),
        "driver": "desktop_page_down",
        "last_scroll_driver": last_scroll_driver,
        "context_check_enabled": context_check_enabled,
        "auto_recover_enabled": auto_recover_enabled,
        "context_threshold": context_threshold,
        "window_title_re": str(args.window_title_re or ""),
        "screenshots": [
            {
                "step": item.step,
                "path": item.screenshot_path,
                "ui_dump_path": item.ui_dump_path,
                "ui_text": item.ui_text,
                "captured_at": item.captured_at,
                "context_check": {
                    "score": item.context_score,
                    "matched_terms": item.context_matched_terms,
                    "reason": item.context_reason,
                    "recovered": item.context_recovered,
                },
            }
            for item in steps
        ],
    }
    manifest_path = session_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_remember:
        _persist_profile(
            store_path=profile_store_path,
            store=profile_store,
            profile_name=profile_name,
            machine_name=machine_name,
            args=args,
            session_dir=session_dir,
        )
        _emit_progress(args.progress_json, "profile_saved", profile_name=profile_name, profile_store=str(profile_store_path))

    result_payload = {
        "ok": True,
        "manifest_path": str(manifest_path),
        "session_dir": str(session_dir),
        "profile_name": profile_name,
        "operator_id": args.operator_id,
        "machine_name": machine_name,
        "account_id": account_id,
        "screenshots": len(steps),
        "auto_scroll": bool(args.auto_scroll),
        "driver": "desktop_page_down",
        "scroll_driver_used": last_scroll_driver,
        "remembered": not args.no_remember,
        "window_title": window_title,
    }
    _emit_progress(args.progress_json, "capture_finished", **result_payload)

    if args.json_output:
        print(json.dumps(result_payload, ensure_ascii=False))
        return

    print(f"Saved manifest: {manifest_path}")
    if not args.no_remember:
        print(f"Remembered profile: {profile_name}")
    print("Next step:")
    print(f"  python import_wechat_mobile_package.py --package \"{session_dir}\"")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("capture aborted by user", file=sys.stderr)
        raise SystemExit(130)