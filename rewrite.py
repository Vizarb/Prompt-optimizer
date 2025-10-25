#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

import requests


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="rewrite",
        description="Client for the local Prompt Rewriter API (prints rewritten prompt to stdout).",
    )
    p.add_argument(
        "raw_prompt",
        nargs="?",
        help="The rough, human-style prompt. If omitted, the script reads from STDIN.",
    )
    p.add_argument(
        "--host",
        default=os.getenv("REWRITER_HOST", "http://127.0.0.1:8000"),
        help="API host (default: %(default)s or env REWRITER_HOST)",
    )
    p.add_argument(
        "--profile",
        default="t4all",
        choices=["t4all", "default"],
        help="Profile to use (default: %(default)s).",
    )
    p.add_argument(
        "--rules-file",
        dest="rules_file",
        help="Override rules file name inside ./rules (e.g. rules_t4all.yaml).",
    )
    p.add_argument(
        "--template-file",
        dest="template_file",
        help="Override system prompt template inside ./templates (e.g. system_prompt_t4all.txt).",
    )
    p.add_argument(
        "--stack",
        help='Optional stack hint (e.g., "Django+DRF+PostgreSQL; React+TS+RTK; Docker; GA").',
    )
    p.add_argument(
        "--files",
        nargs="*",
        help="File/dir paths involved (space-separated).",
    )
    p.add_argument(
        "--errors",
        help="Paste linter/type/test errors or a short summary.",
    )
    p.add_argument(
        "--function-spec",
        dest="function_spec",
        help="Function name/signature/behavior spec text.",
    )
    return p.parse_args()


def read_raw_prompt_from_stdin() -> str:
    if sys.stdin.isatty():
        # No stdin input and no positional provided → show hint and exit.
        print("No prompt provided. Pass a positional argument or pipe text via STDIN.", file=sys.stderr)
        print('Example:  echo "fix those errors and implement the function" | python rewrite.py', file=sys.stderr)
        sys.exit(2)
    return sys.stdin.read().strip()


def main() -> None:
    args = parse_args()

    raw_prompt = args.raw_prompt.strip() if args.raw_prompt else read_raw_prompt_from_stdin()

    payload = {
        "raw_prompt": raw_prompt,
        "profile": args.profile,
    }

    # Optional context
    if args.stack:
        payload["stack"] = args.stack
    if args.files:
        payload["files"] = args.files  # type: List[str]
    if args.errors:
        payload["errors"] = args.errors
    if args.function_spec:
        payload["function_spec"] = args.function_spec

    # Optional explicit overrides
    if args.rules_file:
        payload["rules_file"] = args.rules_file
    if args.template_file:
        payload["template_file"] = args.template_file

    url = args.host.rstrip("/") + "/rewrite"

    try:
        r = requests.post(url, json=payload, timeout=180)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[rewrite] request failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = r.json()
        text = data.get("rewritten_prompt", "").strip()
    except json.JSONDecodeError:
        print("[rewrite] invalid JSON response from server", file=sys.stderr)
        sys.exit(1)

    if not text:
        print("[rewrite] empty response", file=sys.stderr)
        sys.exit(1)

    # Print only the prompt (so it’s easy to pipe into files/clipboard tools)
    print(text)


if __name__ == "__main__":
    main()
