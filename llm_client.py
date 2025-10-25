# llm_client.py
from __future__ import annotations

import os
import time
from pathlib import Path
import requests

# Prefer coder for code-heavy prompts; keep a general fallback
MODEL_CODER   = os.getenv("PROMPT_OPTIMIZER_MODEL_CODER",   "qwen2.5-coder:3b-instruct")
MODEL_GENERAL = os.getenv("PROMPT_OPTIMIZER_MODEL_GENERAL", "qwen2.5:3b-instruct")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


# -------------------- Ollama helpers --------------------

def _ollama_up(timeout: float = 1.5) -> bool:
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=timeout)
        return r.ok
    except Exception:
        return False


def _ensure_model(name: str, timeout_sec: float = 180.0) -> None:
    """
    Ensure the model exists locally; if not, pull it via the REST API.
    """
    try:
        tags = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).json()
        if any(m.get("name") == name for m in tags.get("models", [])):
            return
    except Exception:
        # if tags call fails we try to pull anyway
        pass

    # Trigger pull (non-streaming request; server streams progress internally)
    resp = requests.post(f"{OLLAMA_HOST}/api/pull", json={"name": name}, timeout=30)
    resp.raise_for_status()

    # Wait until available in /api/tags
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            tags = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).json()
            if any(m.get("name") == name for m in tags.get("models", [])):
                return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError(f"Model '{name}' not ready after pull; check Ollama logs.")


# -------------------- Prompt building --------------------

def _build_rules_text(rules: dict) -> str:
    parts: list[str] = []
    for section, lines in rules.items():
        parts.append(f"### {section.upper()}")
        for item in lines:
            parts.append(f"- {item}")
    return "\n".join(parts)


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
        "import ", "from ", "export ",
        "try:", "except ", "raise ",
        "{", "}", ";"
    )
    return any(marker in text for marker in code_markers)


def _pick_model(raw_text: str, context_blob: str) -> str:
    haystack = f"{raw_text}\n{context_blob}"
    return MODEL_CODER if _looks_like_code(haystack) else MODEL_GENERAL


# -------------------- Public API --------------------

def generate_rewrite(
    *,
    raw_text: str,
    rules: dict,
    context: str | None = None,
    stack: str | None = None,
    files: list[str] | None = None,
    errors: str | None = None,
    function_spec: str | None = None,
    system_prompt_path: str | Path | None = None,
) -> str:
    if not _ollama_up():
        raise RuntimeError(
            f"Ollama server is not reachable at {OLLAMA_HOST}.\n"
            "Start it (CPU-only example):\n"
            "  OLLAMA_NUM_GPU_LAYERS=0 ollama serve"
        )

    system_prompt_path = Path(system_prompt_path or "templates/system_prompt_t4all.txt")
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    merged_rules = _build_rules_text(rules)
    context_blob = _build_context_blob(
        context=context,
        stack=stack,
        files=files,
        errors=errors,
        function_spec=function_spec,
    )

    full_prompt = (
        f"{system_prompt}\n\n"
        f"Context:\n{context_blob}\n\n"
        f"Rules:\n{merged_rules}\n\n"
        f"User Request:\n{raw_text.strip()}\n"
    )

    model = _pick_model(raw_text, context_blob)
    _ensure_model(model)

    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_ctx": 2048
        },
    }

    r = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    rewritten = (data.get("response") or "").strip()
    if not rewritten:
        raise RuntimeError("Empty response from model. Check Ollama logs.")
    return rewritten
