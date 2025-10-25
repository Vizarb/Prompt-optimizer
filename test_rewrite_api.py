#!/usr/bin/env python
from __future__ import annotations

import os
import sys
import json
import textwrap
from typing import Final, List, Dict, Any

import requests


# ---- Config ----

REWRITER_HOST: Final[str] = os.getenv("REWRITER_HOST", "http://127.0.0.1:8000")
REWRITE_URL:   Final[str] = REWRITER_HOST.rstrip("/") + "/rewrite"

# Choose which profile to test by default ("t4all" | "default")
PROFILE: Final[str] = os.getenv("REWRITER_PROFILE", "t4all")

# Optional file overrides (filenames must live under ./rules and ./templates)
RULES_FILE_OVERRIDE: Final[str | None]    = os.getenv("REWRITER_RULES_FILE")      # e.g. "rules_t4all.yaml"
TEMPLATE_FILE_OVERRIDE: Final[str | None] = os.getenv("REWRITER_TEMPLATE_FILE")   # e.g. "system_prompt_t4all.txt"

# Whether to enforce section headers in the response
STRICT_SECTIONS: Final[bool] = os.getenv("REWRITER_STRICT_SECTIONS", "1") not in ("0", "false", "False")


# ---- Helpers ----

def ensure_api() -> None:
    """
    Fails fast if the FastAPI rewriter is not reachable.
    """
    try:
        r = requests.get(REWRITER_HOST.rstrip("/") + "/profiles", timeout=3)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        msg = textwrap.dedent(f"""
            Could not reach the Prompt Rewriter API.
            Tried: {REWRITER_HOST}/profiles

            Fix:
              1) Ensure the API is running:  uvicorn main:app --reload
              2) If running elsewhere, set REWRITER_HOST (e.g., http://127.0.0.1:8000)
              3) Visit {REWRITER_HOST}/docs to confirm

            Raw error: {exc!r}
        """).strip()
        raise SystemExit(msg)


def post_rewrite(payload: Dict[str, Any]) -> str:
    """
    POST /rewrite and return the rewritten prompt string.
    """
    r = requests.post(REWRITE_URL, json=payload, timeout=180)
    try:
        r.raise_for_status()
    except requests.HTTPError as exc:  # noqa: BLE001
        raise SystemExit(f"HTTP {r.status_code} from /rewrite: {r.text}") from exc

    try:
        data = r.json()
    except json.JSONDecodeError as exc:  # noqa: BLE001
        raise SystemExit(f"Non-JSON response from /rewrite: {r.text!r}") from exc

    rewritten = (data.get("rewritten_prompt") or "").strip()
    if not rewritten:
        raise SystemExit("Empty 'rewritten_prompt' in response.")
    return rewritten


def check_t4all_sections(text: str) -> None:
    """
    Ensures the canonical 6 sections exist in order (loose check).
    """
    if not STRICT_SECTIONS:
        return

    headers = ["Goal", "Inputs", "Constraints", "Tasks", "Output Format", "Acceptance Criteria"]
    # Allow "Constraints & Standards" in place of "Constraints"
    text_upper = text
    ok = True
    last_pos = -1
    for h in headers:
        alt = "Constraints & Standards" if h == "Constraints" else None
        idx = text_upper.find(h)
        if idx < 0 and alt:
            idx = text_upper.find(alt)
        if idx < 0 or idx < last_pos:
            ok = False
            break
        last_pos = idx

    if not ok:
        raise SystemExit(
            "Response did not contain all expected section headers in order:\n"
            "  Goal → Inputs → Constraints (or Constraints & Standards) → Tasks → Output Format → Acceptance Criteria\n"
            f"\nGot:\n{text[:1000]}..."
        )


# ---- Main test ----

def main() -> int:
    ensure_api()

    # Example rough input; adjust freely
    raw_prompt = (
        "add subtitle auto-sync step after whisper transcription and before ffmpeg burn, and log it in the db"
    )

    # Example context fields (all optional)
    payload: Dict[str, Any] = {
        "raw_prompt": raw_prompt,
        "profile": PROFILE,  # "t4all" by default
        "files": ["t4a/services/subtitles.py", "t4a/db/helpers.py"],
        "function_spec": "Insert karaoke auto-sync phase; record phase_start/finish; ensure idempotence.",
        # You can add "stack", "context", "errors" if you want:
        # "stack": "Django+DRF+PostgreSQL; React+TypeScript+RTK; Docker; GA",
        # "errors": "pytest: 1 failed; mypy: clean; ruff: F401 in subtitles.py",
    }

    # Optional per-request overrides (filenames only)
    if RULES_FILE_OVERRIDE:
        payload["rules_file"] = RULES_FILE_OVERRIDE
    if TEMPLATE_FILE_OVERRIDE:
        payload["template_file"] = TEMPLATE_FILE_OVERRIDE

    rewritten = post_rewrite(payload)

    print("\n--- Rewritten Prompt ---\n")
    print(rewritten)
    print("\n------------------------\n")

    check_t4all_sections(rewritten)
    print("OK: response contains expected sections (T4All profile).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
