# main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import yaml
from typing import Literal

from llm_client import generate_rewrite, _OLLAMA_HOST_ENV
import os

app = FastAPI(title="Prompt Rewriter – Profile Aware")

# Folders
RULES_DIR = Path("rules")
TPL_DIR   = Path("templates")

# Profiles registry (add more as you create them)
PROFILES: dict[str, dict[str, str]] = {
    "t4all": {
        "rules": "rules_t4all_v2.yaml",
        "template": "system_prompt_t4all_v2.txt",
    },
    "default": {
        "rules": "rules.yaml",
        "template": "system_prompt.txt",
    },
}


def _safe_join(base: Path, name: str) -> Path:
    """
    Allow only basenames that exist under the base directory.
    Prevents directory traversal, absolute paths, etc.
    """
    p = (base / name).resolve()
    if base.resolve() not in p.parents and p.parent != base.resolve():
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {name}")
    return p

def _load_rules(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load rules: {e}")

class RewriteRequest(BaseModel):
    raw_prompt: str

    # Optional context
    context: str | None = None
    stack: str | None = None
    files: list[str] | None = None
    errors: str | None = None
    function_spec: str | None = None

    # Profile selection (pick one of your registered profiles)
    profile: Literal["t4all", "default"] | None = "t4all"

    # Optional explicit overrides (filenames only, relative to folders)
    rules_file: str | None = None          # e.g. "my_rules.yaml"
    template_file: str | None = None       # e.g. "my_system_prompt.txt"


@app.get("/config")
def show_config():
    """
    Quick check endpoint to confirm which Ollama host and compute mode are in use.
    """
    return {
        "_OLLAMA_HOST_ENV": _OLLAMA_HOST_ENV,
        "compute_mode": os.getenv("PROMPT_OPTIMIZER_COMPUTE", "auto").strip().lower(),
    }



@app.get("/profiles")
def list_profiles():
    """List registered profiles + discover available files on disk."""
    rules_files = sorted(p.name for p in RULES_DIR.glob("*.y*ml"))
    tpl_files   = sorted(p.name for p in TPL_DIR.glob("*.txt"))
    return {
        "profiles": PROFILES,
        "available": {"rules": rules_files, "templates": tpl_files},
        "folders": {"rules_dir": str(RULES_DIR), "templates_dir": str(TPL_DIR)},
    }


@app.post("/rewrite")
def rewrite_prompt(req: RewriteRequest):
    # Determine files from profile, then apply explicit overrides if provided
    prof = PROFILES.get(req.profile or "t4all", PROFILES["t4all"])
    rules_name = req.rules_file or prof["rules"]
    tpl_name   = req.template_file or prof["template"]

    rules_path = _safe_join(RULES_DIR, rules_name)
    tpl_path   = _safe_join(TPL_DIR,   tpl_name)

    rules = _load_rules(rules_path)

    prompt = generate_rewrite(
        raw_text=req.raw_prompt,
        rules=rules,
        context=req.context,
        stack=req.stack,
        files=req.files,
        errors=req.errors,
        function_spec=req.function_spec,
        system_prompt_path=tpl_path,
    )
    return {"rewritten_prompt": prompt.strip()}
