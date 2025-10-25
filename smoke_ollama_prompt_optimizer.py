from __future__ import annotations

import os
import sys
from typing import Final, List, Dict

import ollama  # pip install ollama


def get_ollama_host() -> str:
    # Ollama desktop listens on 11434 by default
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def ensure_daemon() -> None:
    """
    Fails fast if the Ollama daemon is not reachable.
    """
    host = get_ollama_host()
    try:
        # This will raise if daemon is unreachable
        _ = ollama.list()
    except Exception as exc:  # noqa: BLE001
        msg = (
            "Could not reach the Ollama daemon.\n"
            f"Tried host: {host}\n\n"
            "Fix:\n"
            "  1) Ensure Ollama Desktop is running (it should expose :11434)\n"
            "  2) Or set OLLAMA_HOST, e.g.: export OLLAMA_HOST=http://127.0.0.1:11434\n"
            "  3) Try: `ollama list` in your shell to confirm connectivity\n"
            f"Raw error: {exc!r}"
        )
        raise SystemExit(msg) from exc


def ensure_model(model: str) -> None:
    """
    Pulls the model if it's not present locally.
    """
    models = {m["model"] for m in ollama.list().get("models", [])}
    # Model names from `ollama list` look like "qwen2.5-coder:3b"
    if model not in models:
        print(f"Model '{model}' not found locally. Pulling…", flush=True)
        ollama.pull(model)
        print("Pull complete.", flush=True)


def run_prompt_optimizer(model: str, user_prompt: str) -> str:
    """
    Sends a prompt-optimization request to a local model via Ollama.
    """
    system_msg: Final[str] = (
        "You are a prompt optimizer. Improve clarity, structure, and intent. "
        "Preserve constraints (SOLID, DRY, KISS) and return only the rewritten prompt."
    )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_prompt},
    ]

    resp = ollama.chat(model=model, messages=messages)
    content = resp.get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError("Empty response from model.")
    return content


def main() -> int:
    # Safe default that exists in the Ollama library and is lightweight enough for CPU
    model = os.environ.get("O_LLAMA_MODEL", "qwen2.5-coder:3b")
    # Example input; replace with whatever you like:
    input_prompt = (
        "Rewrite this prompt so a model can implement a small Python function and tests, "
        "following SOLID, DRY, and KISS. The function sums even numbers in a list."
    )

    ensure_daemon()
    ensure_model(model)
    improved = run_prompt_optimizer(model, input_prompt)

    print("\n--- Improved Prompt ---\n")
    print(improved)
    print("\n-----------------------\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
