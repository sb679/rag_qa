#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert a browser-exported WeChat cookie string into cookies.jar.

Typical usage:
  python convert_wechat_cookie_to_jar.py

The script will first try to read the clipboard. If the clipboard is empty,
it will prompt you to paste a cookie string such as:
  key1=value1; key2=value2; key3=value3

The generated jar can be loaded directly by run_wechat_collector.py.
"""

from __future__ import annotations

import argparse
import os
import re
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


DEFAULT_DOMAIN = "mp.weixin.qq.com"
DEFAULT_PATH = "/"


def _read_clipboard_text() -> str:
    try:
        import tkinter as tk
    except Exception:
        return ""

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            return (root.clipboard_get() or "").strip()
        except Exception:
            return ""
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def _normalize_cookie_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    if "\n" in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) == 1:
            return lines[0]

        if len(lines) >= 2 and all("=" not in line or "\t" in line for line in lines):
            pairs = []
            for line in lines:
                if "\t" in line:
                    name, value = line.split("\t", 1)
                    name = name.strip()
                    value = value.strip()
                    if name and value:
                        pairs.append(f"{name}={value}")
            if pairs:
                return "; ".join(pairs)

    return text


def _split_cookie_pairs(cookie_text: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for chunk in cookie_text.split(";"):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in {
            "path",
            "domain",
            "expires",
            "max-age",
            "secure",
            "httponly",
            "samesite",
        }:
            continue
        pairs.append((name, value))
    return pairs


def _build_cookie(name: str, value: str, domain: str, path: str, secure: bool) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=True,
        secure=secure,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def convert_cookie_text_to_jar(
    cookie_text: str,
    output_path: Path,
    domain: str = DEFAULT_DOMAIN,
    path: str = DEFAULT_PATH,
    secure: bool = True,
) -> int:
    normalized_text = _normalize_cookie_text(cookie_text)
    pairs = _split_cookie_pairs(normalized_text)
    if not pairs:
        raise ValueError("No cookie pairs found. Paste a Cookie header like a=b; c=d")

    jar = LWPCookieJar(str(output_path))
    for name, value in pairs:
        jar.set_cookie(_build_cookie(name, value, domain=domain, path=path, secure=secure))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    jar.save(ignore_discard=True, ignore_expires=True)
    return len(pairs)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert browser cookie text to cookies.jar")
    parser.add_argument("--cookie", type=str, default=None, help="Raw Cookie header string")
    parser.add_argument("--cookie-file", type=str, default=None, help="Path to a text file containing cookie text")
    parser.add_argument("--output", type=str, default="cookies.jar", help="Output LWPCookieJar path")
    parser.add_argument("--domain", type=str, default=DEFAULT_DOMAIN, help="Cookie domain")
    parser.add_argument("--path", type=str, default=DEFAULT_PATH, help="Cookie path")
    parser.add_argument("--insecure", action="store_true", help="Mark cookies as non-secure")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    cookie_text = ""
    source = ""

    if args.cookie:
        cookie_text = args.cookie
        source = "--cookie"
    elif args.cookie_file:
        cookie_path = Path(args.cookie_file).expanduser().resolve()
        cookie_text = cookie_path.read_text(encoding="utf-8")
        source = str(cookie_path)
    else:
        cookie_text = _read_clipboard_text()
        if cookie_text:
            source = "clipboard"
        else:
            print("Paste the Cookie header string below, then press Enter:")
            cookie_text = input().strip()
            source = "stdin"

    output_path = Path(args.output).expanduser().resolve()
    cookie_count = convert_cookie_text_to_jar(
        cookie_text=cookie_text,
        output_path=output_path,
        domain=args.domain.strip() or DEFAULT_DOMAIN,
        path=args.path.strip() or DEFAULT_PATH,
        secure=not args.insecure,
    )

    print(f"ok: saved {cookie_count} cookies to {output_path}")
    print(f"source={source}")
    print(f"domain={args.domain.strip() or DEFAULT_DOMAIN}")


if __name__ == "__main__":
    main()