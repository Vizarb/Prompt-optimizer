
---

# Prompt Rewriter (Profile-Aware, Local, CPU-Only)

A tiny local service that rewrites rough, human-style requests into **clean, rules-aware prompts** you can paste into ChatGPT (or any LLM).
It supports **profiles** (e.g., `t4all`, `default`) and lets you **override** the rules and system prompt per request.

* Runs locally on **CPU** (keeps your GPU free for T4All).
* Uses **Ollama** with tiny instruction models (default: `qwen2.5-coder:3b-instruct`).
* One endpoint: `POST /rewrite` (plus `GET /profiles`).
* Output: **only** the rewritten prompt (no commentary).

---

## Features

* **Profile selection** (`t4all`, `default`, extendable).
* **Per-request overrides**: choose `rules_file` and/or `template_file` at call time.
* **Richer context**: include `stack`, `files`, `errors`, `function_spec`.
* **Automatic coder/general model pick** (code-heavy inputs → coder model).
* **CPU-only Ollama** compatible .
* **CLI client (`rewrite.py`)** to send requests directly from the terminal.

---

## Folder Structure

```
prompt_optimizer/
├─ main.py
├─ llm_client.py
├─ rewrite.py
├─ rules/
│  ├─ rules_t4all.yaml
│  └─ rules.yaml
├─ templates/
│  ├─ system_prompt_t4all.txt
│  └─ system_prompt.txt
├─ requirements.txt
└─ README.md
```

You can add more files under `rules/` and `templates/` and register them as profiles (see below).

---

## Requirements

* Python 3.10+
* **Ollama** (Windows / Linux / macOS)
* Internet once to pull models (local thereafter)

---

## Install

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
. .venv/bin/activate

pip install -U pip
pip install -r requirements.txt
# (or) pip install fastapi uvicorn pyyaml requests
```

---

## Install & Run Ollama (CPU-only recommended)

**Windows**

```powershell
$env:OLLAMA_NUM_GPU_LAYERS="0"
ollama serve
```

**Linux / WSL**

```bash
curl -fsSL https://ollama.com/install.sh | sh
OLLAMA_NUM_GPU_LAYERS=0 ollama serve
```

**macOS**

```bash
brew install ollama
OLLAMA_NUM_GPU_LAYERS=0 ollama serve
```

Pull models (optional — the API can auto-pull if missing):

```bash
ollama pull qwen2.5-coder:3b-instruct
ollama pull qwen2.5:3b-instruct
```

---

## Run the API

```bash
uvicorn main:app --reload
```

Visit docs at:
`http://127.0.0.1:8000/docs`

---

## Profiles & Files

**Registered profiles** (editable in `main.py`):

```python
PROFILES = {
  "t4all":   {"rules": "rules_t4all.yaml",   "template": "system_prompt_t4all.txt"},
  "default": {"rules": "rules.yaml",         "template": "system_prompt.txt"}
}
```

* You can create more rules/templates (e.g., `rules_freemarket.yaml`, `system_prompt_freemarket.txt`) and add a profile.
* Safety: only files **inside** `rules/` and `templates/` are allowed.

List available files and profiles:

```
GET /profiles
```

---

## API

### `GET /profiles`

Returns all currently registered profiles and the files available in `rules/` and `templates/`.

**Response Example:**

```json
{
  "profiles": {
    "t4all": {"rules": "rules_t4all.yaml", "template": "system_prompt_t4all.txt"},
    "default": {"rules": "rules.yaml", "template": "system_prompt.txt"}
  },
  "available": {
    "rules": ["rules_t4all.yaml", "rules.yaml"],
    "templates": ["system_prompt_t4all.txt", "system_prompt.txt"]
  },
  "folders": {
    "rules_dir": "rules",
    "templates_dir": "templates"
  }
}
```

**Field descriptions:**

| Field                                             | Type           | Description                                                                                                          |
| ------------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------- |
| **`profiles`**                                    | `object`       | Key-value pairs of all profiles defined in `main.py`. Each profile maps to its default `rules` and `template` files. |
| **`available.rules`**                             | `list[string]` | Lists all YAML rule files physically found under `rules/`.                                                           |
| **`available.templates`**                         | `list[string]` | Lists all TXT system prompts available under `templates/`.                                                           |
| **`folders.rules_dir` / `folders.templates_dir`** | `string`       | Paths to the base directories used for validation and safe file resolution.                                          |

---

### `POST /rewrite`

This endpoint takes a rough, human-style request and rewrites it into a structured, professional prompt according to your selected profile.

**Endpoint:**

```
POST http://127.0.0.1:8000/rewrite
```

**Request Body Example:**

```json
{
  "raw_prompt": "string (required)",
  "context": "string (optional)",
  "stack": "string (optional)",
  "files": ["path1", "path2"],
  "errors": "string (optional)",
  "function_spec": "string (optional)",
  "profile": "t4all | default (optional, defaults to 't4all')",
  "rules_file": "filename.yaml (optional; overrides profile rules)",
  "template_file": "filename.txt (optional; overrides profile template)"
}
```

---

### **Parameter Reference**

| Field               | Type           | Description                                                                                                                            |
| ------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **`raw_prompt`**    | `string`       | The actual message you want rewritten. Example: `"fix those errors and implement the new function"`                                    |
| **`context`**       | `string`       | Additional notes or background to help the model understand intent. Example: `"Feature improves subtitle sync across T4All pipeline."` |
| **`stack`**         | `string`       | Describes your tech stack so the rewriter tailors responses. Example: `"Python + FastAPI + SQLite; React + TypeScript"`                |
| **`files`**         | `list[string]` | Files involved in the change (helps infer scope). Example: `["t4a/services/subtitles.py", "t4a/db/helpers.py"]`                        |
| **`errors`**        | `string`       | Optional snippet of error or test logs. Example: `"pytest: 2 failed; mypy: missing type annotation; ruff F401"`                        |
| **`function_spec`** | `string`       | Describes the new function or logic to implement. Example: `"Add karaoke auto-sync phase; ensure idempotence; log timings in DB."`     |
| **`profile`**       | `string`       | Selects which rule/template combo to use (`t4all` by default). Extendable via `main.py`.                                               |
| **`rules_file`**    | `string`       | Overrides the default YAML rules file. Must exist inside `/rules/`. Example: `"rules_t4all.yaml"`                                      |
| **`template_file`** | `string`       | Overrides the default TXT system prompt file. Must exist inside `/templates/`. Example: `"system_prompt_t4all.txt"`                    |

---

### **Response**

```json
{
  "rewritten_prompt": "string"
}
```

This field contains your fully rewritten, formatted prompt ready for ChatGPT or any LLM.

**Example Response:**

```json
{
  "rewritten_prompt": "### Goal\nImplement an automated subtitle synchronization phase between Whisper and FFmpeg burn-in..."
}
```

---

## Ready-to-Use Requests

(Examples unchanged — see above)

---

## `rewrite.py` CLI (local client)

A lightweight CLI client that sends prompts to your running API and prints only the rewritten text to stdout.
Supports piping, profiles, and overrides.

Usage examples:

```bash
python rewrite.py "fix those errors and implement the new function"
echo "add subtitle auto-sync step" | python rewrite.py
python rewrite.py "fix typing and update tests" --profile default
python rewrite.py "implement new ffmpeg burn options" --stack "Django+DRF+PostgreSQL; React+TS+RTK; Docker" --files t4a/services/burn.py
```

---

## Behavior & Tips

* **Model selection:** Automatically switches between coder/general models.
* **CPU-only mode:** Use `OLLAMA_NUM_GPU_LAYERS=0` to avoid GPU load.
* **Adaptive output structure:**
  - For implementation prompts → `Goal → Inputs → Constraints → Tasks → Output Format → Acceptance Criteria`
  - For review/refactor prompts → uses the same order with adaptive section names.
* **Rules:** Hierarchical (HIGH/MEDIUM/LOW priority) enforcing architecture, typing, tests, style, logging, OS behavior, and CI.
* **OS handling:** assumes **Windows** by default but prefers cross-platform code whenever feasible (`pathlib` over `os.path`, portable shell syntax).
* **Overrides:** Only filenames within `rules/` and `templates/` are valid.

---

## Add/Extend Profiles

1. Create new files:

   * `rules/rules_freemarket.yaml`
   * `templates/system_prompt_freemarket.txt`
2. Register in `main.py`:

   ```python
   PROFILES["freemarket"] = {
     "rules": "rules_freemarket.yaml",
     "template": "system_prompt_freemarket.txt",
   }
   ```
3. Use:

   ```json
   { "raw_prompt": "…" , "profile": "freemarket" }
   ```

---

## CPU-Only vs GPU Mode

By default, Ollama uses your **GPU** when available for faster inference.
To keep your GPU free for other workloads (for example, the **T4All** pipeline), you can start a **CPU-only Ollama server** and point the Prompt Optimizer to it.

### **1. GPU (Default Mode)**

When you start Ollama normally, it automatically detects and uses your GPU.

```powershell
# Windows
ollama serve
```

```bash
# Linux / macOS
ollama serve
```

This starts a GPU-enabled Ollama server on the default port **11434**.
Your optimizer will automatically use it if `OLLAMA_HOST` isn’t overridden.

---

### **2. CPU-Only Mode (Recommended for Prompt Optimizer)**

Run a dedicated Ollama instance that uses **only the CPU**, leaving your GPU free for other apps.

**Windows PowerShell**

```powershell
# Hide GPUs and force CPU inference for this shell only
$env:CUDA_VISIBLE_DEVICES = ""
$env:OLLAMA_LLM_LIBRARY   = "cpu_avx2"   # use "cpu" on older CPUs
$env:OLLAMA_HOST          = "127.0.0.1:12345"
ollama serve
```

**Linux / macOS**

```bash
export CUDA_VISIBLE_DEVICES=
export OLLAMA_LLM_LIBRARY=cpu_avx2
export OLLAMA_HOST=127.0.0.1:12345
ollama serve
```

This launches a CPU-only Ollama server on **port 12345**.
You’ll see logs such as:

```
Listening on 127.0.0.1:12345
inference compute id=cpu library=cpu
entering low vram mode
```

---

### **3. Point the Optimizer to the CPU-Only Server**

Start the FastAPI service (Prompt Optimizer) in a separate terminal and set its `OLLAMA_HOST`
to the full URL of the CPU-only instance:

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:12345"
uvicorn main:app --reload --port 8800
```

Check configuration:

```bash
curl http://127.0.0.1:8800/config
```

Expected:

```json
{"ollama_host": "http://127.0.0.1:12345"}
```

The Optimizer will now send all rewrite requests to the CPU-only server while your GPU remains free for T4All or other projects.

---

### **4. Quick Verification**

1. Confirm the Ollama server is responding:

   ```bash
   curl http://127.0.0.1:12345/api/tags
   ```

   You should see a JSON list of models.

2. Check that GPU usage stays at 0 % while generating (Task Manager or `nvidia-smi`).

3. To return to GPU mode, simply stop the CPU server and run `ollama serve` normally again.

---

## Troubleshooting

* **404 Not Found:** POST to `/rewrite`, not `/`.
* **500 Internal Server Error:** Start Ollama first:

  ```bash
  OLLAMA_NUM_GPU_LAYERS=0 ollama serve
  ```
* **Model missing:**

  ```bash
  ollama pull qwen2.5-coder:3b-instruct
  ```
* **Invalid path:** Only files inside `rules/` and `templates/` are allowed.
* **Empty response:** Check Ollama logs or reduce prompt length.

---

## Environment Variables

* `OLLAMA_HOST` — Ollama API URL (default: `http://127.0.0.1:11434`)
* `REWRITER_HOST` — API base for `rewrite.py` (default: `http://127.0.0.1:8000`)
* `PROMPT_OPTIMIZER_MODEL_CODER` — default `qwen2.5-coder:3b-instruct`
* `PROMPT_OPTIMIZER_MODEL_GENERAL` — default `qwen2.5:3b-instruct`

---

## License

MIT (or your preference)

---

