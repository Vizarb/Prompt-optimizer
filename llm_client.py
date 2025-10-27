from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any
import os
import time
import requests

# -------------------- Config --------------------
# "auto" (default): let the Ollama server decide (GPU if Desktop, CPU if you started CPU-only)
# "cpu"           : add CPU-safe options on each request (num_gpu=0 / num_gpu_layers=0)
COMPUTE_MODE = os.getenv("PROMPT_OPTIMIZER_COMPUTE", "auto").strip().lower()  # "auto" | "cpu"

MODEL_CODER   = os.getenv("PROMPT_OPTIMIZER_MODEL_CODER",   "qwen2.5-coder:3b-instruct")
MODEL_GENERAL = os.getenv("PROMPT_OPTIMIZER_MODEL_GENERAL", "qwen2.5:3b-instruct")

# If user pins a host, we’ll prefer it; otherwise we probe common defaults lazily.
_OLLAMA_HOST_ENV = os.getenv("OLLAMA_HOST")  # may be None


# -------------------- Ollama helpers --------------------

def _ollama_up(base: str, timeout: float = 1.5) -> bool:
    try:
        r = requests.get(f"{base}/api/tags", timeout=timeout)
        return r.ok
    except Exception:
        return False


def _ensure_model(base: str, name: str, timeout_sec: float = 180.0) -> None:
    """Ensure model exists; otherwise pull and wait until listed in /api/tags."""
    try:
        tags = requests.get(f"{base}/api/tags", timeout=3).json()
        if any(m.get("name") == name for m in tags.get("models", [])):
            return
    except Exception:
        pass

    resp = requests.post(f"{base}/api/pull", json={"name": name}, timeout=30)
    resp.raise_for_status()

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            tags = requests.get(f"{base}/api/tags", timeout=3).json()
            if any(m.get("name") == name for m in tags.get("models", [])):
                return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError(f"Model '{name}' not ready after pull; check Ollama logs.")


def _resolve_ollama_host_now() -> str:
    """
    Resolve a reachable Ollama base URL *at call time*.
    Preference order:
      1) Explicit OLLAMA_HOST (if reachable)
      2) Desktop default:  http://127.0.0.1:11434
      3) CPU-only example: http://127.0.0.1:12345
    Falls back to the explicit/env or desktop default even if unreachable,
    so callers can still produce a helpful error.
    """
    candidates: list[str] = []
    if _OLLAMA_HOST_ENV:
        candidates.append(_OLLAMA_HOST_ENV)
    candidates.extend(["http://127.0.0.1:11434", "http://127.0.0.1:12345"])

    for base in candidates:
        if _ollama_up(base, timeout=1.0):
            return base
    # Nothing is up; return best-effort for error messages:
    return _OLLAMA_HOST_ENV or "http://127.0.0.1:11434"


# -------------------- Rules & Prompt building --------------------

def _normalize_rules(data: Any) -> tuple[list[dict[str, Any]], bool, str]:
    include_tests = True
    os_default = "windows"

    if isinstance(data, list):
        entries = [{"text": str(x).strip(), "priority": "medium"} for x in data if str(x).strip()]
        return entries, include_tests, os_default

    if isinstance(data, dict) and "rules" not in data:
        entries = []
        for _section, lines in data.items():
            if isinstance(lines, list):
                for item in lines:
                    entries.append({"text": str(item).strip(), "priority": "medium"})
        return entries, include_tests, os_default

    if isinstance(data, dict):
        include_tests = bool(data.get("include_tests", True))
        os_default = str(data.get("os_default", "windows")).lower()
        rules_block = data.get("rules", {})
        raw_entries: Iterable
        if isinstance(rules_block, dict):
            raw_entries = rules_block.values()
        else:
            raw_entries = rules_block
        entries = []
        for r in raw_entries:
            if isinstance(r, str):
                txt = r.strip()
                if txt:
                    entries.append({"text": txt, "priority": "medium"})
            elif isinstance(r, dict):
                txt = str(r.get("text", "")).strip()
                if not txt:
                    continue
                pr = str(r.get("priority", "medium")).lower()
                cond = r.get("condition")
                entries.append({"text": txt, "priority": pr, "condition": cond})
        return entries, include_tests, os_default

    raise TypeError(f"Unsupported rules YAML root: {type(data).__name__}")


def _build_rules_text(data: Any) -> str:
    entries, include_tests, _os_default = _normalize_rules(data)
    filtered = []
    for e in entries:
        cond = e.get("condition")
        if cond == "include_tests" and not include_tests:
            continue
        filtered.append(e)
    order = {"high": 0, "medium": 1, "low": 2}
    filtered.sort(key=lambda e: order.get(e.get("priority", "medium"), 1))
    return "\n".join(e["text"] for e in filtered if e.get("text")).strip()


def _build_context_blob(
    *,
    context: str | None,
    stack: str | None,
    files: list[str] | None,
    errors: str | None,
    function_spec: str | None,
) -> str:
    chunks: list[str] = []
    if context:
        chunks.append(context)
    if stack:
        chunks.append(f"Stack: {stack}")
    if files:
        chunks.append("Files:\n- " + "\n- ".join(files))
    if errors:
        chunks.append("Errors:\n" + errors)
    if function_spec:
        chunks.append("Function Spec:\n" + function_spec)
    return "\n\n".join(chunks)


def _looks_like_code(text: str) -> bool:
    if "```" in text:
        return True
    code_markers = (
        "def ", "class ", "interface ", "function ",
        "public ", "private ", "const ", "let ",
        "import ", "implement ", "implementation ", "from ", "export ", "module ", "feature ",
        "try:", "except ", "raise ", "{", "}", ";"
    )
    return any(marker in text for marker in code_markers)


def _pick_model(raw_text: str, context_blob: str) -> str:
    haystack = f"{raw_text}\n{context_blob}"
    return MODEL_CODER if _looks_like_code(haystack) else MODEL_GENERAL


# -------------------- Public API --------------------

def get_current_ollama_host() -> str:
    """Expose the host we would use *right now* (for /config)."""
    return _resolve_ollama_host_now()


def generate_rewrite(
    *,
    raw_text: str,
    rules: Any,
    context: str | None = None,
    stack: str | None = None,
    files: list[str] | None = None,
    errors: str | None = None,
    function_spec: str | None = None,
    system_prompt_path: str | Path | None = None,
) -> str:
    base = _resolve_ollama_host_now()
    if not _ollama_up(base):
        raise RuntimeError(
            f"Ollama server is not reachable at {base}.\n"
            "Start it (examples):\n"
            "  # GPU/Desktop default:    ollama serve\n"
            "  # CPU-only instance:      OLLAMA_NUM_GPU_LAYERS=0 OLLAMA_HOST=127.0.0.1:12345 ollama serve"
        )

    system_prompt_path = Path(system_prompt_path or "templates/system_prompt_t4all.txt")
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    merged_rules = _build_rules_text(rules)
    context_blob = _build_context_blob(
        context=context, stack=stack, files=files, errors=errors, function_spec=function_spec
    )

    full_prompt = (
        f"{system_prompt}\n\n"
        f"Context:\n{context_blob}\n\n"
        f"Rules:\n{merged_rules}\n\n"
        f"User Request:\n{raw_text.strip()}\n"
    )

    model = _pick_model(raw_text, context_blob)
    _ensure_model(base, model)

    options: dict[str, Any] = {
        "temperature": 0.2,
        "top_p": 0.9,
        "num_ctx": 2048,
    }
    if COMPUTE_MODE == "cpu":
        options["num_gpu"] = 0
        options["num_gpu_layers"] = 0

    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": options,
    }

    r = requests.post(f"{base}/api/generate", json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    rewritten = (data.get("response") or "").strip()
    if not rewritten:
        raise RuntimeError("Empty response from model. Check Ollama logs.")
    return rewritten
