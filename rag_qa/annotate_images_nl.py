# -*- coding:utf-8 -*-
"""Apply natural-language image annotations to image annotation JSON.

Usage examples:
    python annotate_images_nl.py --account-id my_wechat_account --article-id a25d005bbdcbb34e --instruction "第1张是装饰图，不要索引；第3张摘要：武协换届现场合影；第3张标签：换届,合影"
    python annotate_images_nl.py --account-id my_wechat_account --article-id a25d005bbdcbb34e --instruction "第1、2、5张保留；第4张是表情包不要索引；第6张备注：这张是大会现场"
  python annotate_images_nl.py --account-id my_wechat_account --article-id a25d005bbdcbb34e --instruction-file instructions.txt
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import requests

from base import Config

BASE_DIR = Path(__file__).resolve().parent


def _load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _call_parse_api(conf: Config, prompt: str) -> Optional[Dict[str, object]]:
    key = (conf.DASHSCOPE_API_KEY or "").strip()
    if not key or key.startswith("demo-key"):
        return None

    endpoint = f"{conf.DASHSCOPE_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": conf.WECHAT_TEXT_STRUCT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是JSON转换器。请把用户的中文标注指令解析为 JSON: "
                    "{actions:[{target_type:'index|image_id',target:'1或image_id',op:'keep|drop|summary|tags|notes',value:'字符串或数组'}]}。"
                    "只输出JSON，不要解释。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 800,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            return None
        content = content.strip()
        match = re.search(r"\{[\s\S]*\}", content)
        text = match.group(0) if match else content
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return None
    except Exception:
        return None


def _fallback_parse(instruction: str) -> Dict[str, object]:
    actions: List[Dict[str, object]] = []
    chunks = [seg.strip() for seg in re.split(r"[；;\n]", instruction) if seg.strip()]
    for chunk in chunks:
        targets = re.findall(r"第\s*(\d+(?:\s*[、,，]\s*\d+)*)\s*张", chunk)
        if not targets:
            continue
        indices: List[str] = []
        for target_block in targets:
            for idx in re.split(r"[、,，]\s*", target_block):
                idx = idx.strip()
                if idx and idx.isdigit():
                    indices.append(idx)
        if not indices:
            continue
        text = chunk

        for idx in indices:
            if re.search(r"不要索引|剔除|删除|无效|表情包|装饰图|贴纸|表情", text):
                actions.append({"target_type": "index", "target": idx, "op": "drop", "value": ""})
            if re.search(r"保留|有效|索引", text):
                actions.append({"target_type": "index", "target": idx, "op": "keep", "value": ""})

        ms = re.search(r"摘要[:：]\s*(.+)$", text)
        if ms:
            for idx in indices:
                actions.append({"target_type": "index", "target": idx, "op": "summary", "value": ms.group(1).strip()})

        mt = re.search(r"标签[:：]\s*(.+)$", text)
        if mt:
            tags = [t.strip() for t in re.split(r"[,，]", mt.group(1)) if t.strip()]
            for idx in indices:
                actions.append({"target_type": "index", "target": idx, "op": "tags", "value": tags})

        mn = re.search(r"备注[:：]\s*(.+)$", text)
        if mn:
            for idx in indices:
                actions.append({"target_type": "index", "target": idx, "op": "notes", "value": mn.group(1).strip()})

    # Support direct target expressions without explicit "第X张" if user is writing around local path or image_id.
    for chunk in chunks:
        if re.search(r"装饰图|表情包|贴纸|无效图", chunk) and not re.search(r"第\s*\d+\s*张", chunk):
            continue

    return {"actions": actions}


def apply_nl_annotations(account_id: str, article_id: str, instruction: str) -> Dict[str, object]:
    conf = Config()
    ann_path = BASE_DIR / "data" / "wechat_collector" / "wechat_data" / account_id / "docs" / f"{article_id}.image_annotations.json"
    payload = _load_json(ann_path)

    annotations = payload.get("annotations", [])
    if not isinstance(annotations, list):
        raise ValueError("Invalid annotations payload")

    by_image_id = {}
    by_index = {}
    for i, ann in enumerate(annotations, start=1):
        if not isinstance(ann, dict):
            continue
        image_id = str(ann.get("image_id", "")).strip()
        if image_id:
            by_image_id[image_id] = ann
        by_index[str(i)] = ann

    table_lines = []
    for i, ann in enumerate(annotations, start=1):
        if not isinstance(ann, dict):
            continue
        table_lines.append(f"{i}. image_id={ann.get('image_id','')}; local_path={ann.get('local_path','')}")

    parse_prompt = (
        "图片列表:\n" + "\n".join(table_lines) + "\n\n"
        "用户指令:\n" + instruction
    )

    parsed_api = _call_parse_api(conf, parse_prompt)
    parsed = parsed_api or _fallback_parse(instruction)
    actions = parsed.get("actions", []) if isinstance(parsed, dict) else []
    if not isinstance(actions, list):
        actions = []

    changed = 0
    applied = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        target_type = str(action.get("target_type", "index")).strip().lower()
        target = str(action.get("target", "")).strip()
        op = str(action.get("op", "")).strip().lower()
        value = action.get("value", "")

        ann = None
        if target_type == "image_id":
            ann = by_image_id.get(target)
        else:
            ann = by_index.get(target)
        if ann is None:
            continue

        if op == "drop":
            ann["keep_for_index"] = False
            changed += 1
        elif op == "keep":
            ann["keep_for_index"] = True
            changed += 1
        elif op == "summary":
            ann["manual_summary"] = str(value).strip()
            changed += 1
        elif op == "tags":
            tags = value if isinstance(value, list) else [t.strip() for t in re.split(r"[,，]", str(value)) if t.strip()]
            ann["manual_tags"] = [str(t).strip() for t in tags if str(t).strip()]
            changed += 1
        elif op == "notes":
            ann["manual_notes"] = str(value).strip()
            changed += 1
        else:
            continue

        applied.append({
            "image_id": ann.get("image_id", ""),
            "op": op,
            "target": target,
        })

    payload["annotations"] = annotations
    payload["last_instruction"] = instruction
    payload["last_instruction_at"] = __import__("datetime").datetime.now().isoformat()
    _save_json(ann_path, payload)

    return {
        "annotations_path": str(ann_path),
        "changed": changed,
        "applied": applied,
        "parser": "api" if parsed_api is not None else "fallback",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply natural language annotation instructions")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--article-id", required=True)
    parser.add_argument("--instruction", default="")
    parser.add_argument("--instruction-file", default="")
    args = parser.parse_args()

    text = (args.instruction or "").strip()
    if args.instruction_file:
        text = Path(args.instruction_file).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("instruction is empty")

    result = apply_nl_annotations(
        account_id=args.account_id,
        article_id=args.article_id,
        instruction=text,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
