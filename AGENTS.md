# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this repo is

A prompt-engineering research repo (Microsoft Applied Robotics Research, IEEE Access 2023) that converts natural-language instructions into sequences of executable robot actions. Almost all of the "logic" lives in plain-text prompt files, not in Python. The Python is a thin, deliberately duplicated harness that assembles those prompts, calls a chat model, and parses the JSON reply.

## Commands

```bash
pip install -r requirements.txt          # openai==0.28.1, tiktoken, virtualhome==2.3.0

# Scripts MUST be run from inside their own example directory (see "Relative paths" below)
cd examples/task_decomposition        && python aimodel.py --scenario shelf   # shelf|fridge|drawer|table|window
cd examples/task_decomposition_logic  && python aimodel.py --scenario shelf
cd examples/task_decomposition_dual_arm && python aimodel.py --scenario fridge
cd examples/task_decomposition_dual_arm && python aimodel.py --scenario office_p [--image path.png]

# VirtualHome examples take no CLI args; edit dir_name / scenario dir in __main__ instead.
# They require a running VirtualHome v2.2.4 Unity simulator (UnityCommunication() at import time).
cd examples/task_decomposition_virtualhome && python task_planning.py
```

There is no test suite, linter config, or CI. The established verification step for a change is `python -m compileall -q <example_dir>` plus a real end-to-end run of the affected scenario.

## Credentials

**[examples/task_decomposition_dual_arm/aimodel.py](examples/task_decomposition_dual_arm/aimodel.py) is the exception** — it has been migrated to **Vertex AI Gemini** and no longer uses `openai` or `secrets.json` at all. It builds a `genai.Client(vertexai=True, ...)` from a service-account JSON (default `~/.config/robopara/p-150gk23k-718446bc2ebd.json`, project `p-150gk23k`, location `global`, model `gemini-3.7-flash`), overridable via `vertex_credentials_path` / `vertex_model` / `vertex_project` / `vertex_location` or `GOOGLE_APPLICATION_CREDENTIALS` / `VERTEX_MODEL` / `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`. Its constructor takes no `credentials` positional and no `use_azure`; the old OpenAI-compatible path is kept commented out in place. Requires `google-genai` and `google-auth`.

The other six copies still use the two backends below, selected by `use_azure` in each script's `__main__`. Every `__main__` passes `use_azure=False`.

- **GigaToken / Sub2API** (default): OpenAI-compatible endpoint. Defaults are `https://sub2api.gigaapi.cc/v1`, model `gpt-5.4`, key read from `~/.config/robopara/gigatoken-key.txt`. Overridable per-call via `gigatoken_api_path` / `gigatoken_base_url` / `gigatoken_model`, or via `GIGATOKEN_API_KEY_PATH` / `GIGATOKEN_BASE_URL` / `GIGATOKEN_MODEL` / `GIGATOKEN_API_KEY`. The key must stay outside the repo.
- **Azure OpenAI**: reads `credentials["azureopenai"]` from [secrets.json](secrets.json). Note the checked-in `secrets.json` uses the key `chatengine`, not `azureopenai` — the Azure path will `KeyError` until that block is renamed. `api_version` must be `'2022-12-01'` (gpt-35-turbo 0301, uses the legacy `<|im_start|>` Completion API) or `'2023-05-15'` (ChatCompletion).

## Architecture

### The `ChatGPT` class is copy-pasted, not shared

Each of these carries its own near-identical `ChatGPT` implementation:

- [examples/task_decomposition/aimodel.py](examples/task_decomposition/aimodel.py)
- [examples/task_decomposition_logic/aimodel.py](examples/task_decomposition_logic/aimodel.py)
- [examples/task_decomposition_dual_arm/aimodel.py](examples/task_decomposition_dual_arm/aimodel.py) — the only one with image support
- [examples/task_decomposition_virtualhome/task_planning.py](examples/task_decomposition_virtualhome/task_planning.py) and [feedback_test.py](examples/task_decomposition_virtualhome/feedback_test.py)
- [examples/task_decomposition_virtualhome_supplementary/task_planning_detail.py](examples/task_decomposition_virtualhome_supplementary/task_planning_detail.py) and [task_planning_addexamples.py](examples/task_decomposition_virtualhome_supplementary/task_planning_addexamples.py)

A fix to the API/parsing layer must be replicated by hand into each copy that needs it. They are not identical — the VirtualHome variants use `temperature=2.0` (vs `0.1`) and have no `--image` or `--scenario` argument parsing. Do not "helpfully" factor them into a shared module unless asked; the per-example self-containment is intentional in this repo.

### Relative paths pin the working directory

Every script hardcodes `./system`, `./prompt`, `./query`, `./out`, `last_response.txt`, and `../../secrets.json`. Running from the repo root fails. Any new script belongs in an example directory and should follow the same convention.

### Prompt assembly

`system/system.txt` becomes the system message. Then each file named in `prompt_load_order` (`prompt_role`, `prompt_function`, `prompt_environment`, `prompt_output_format`, `prompt_example`) is split on the literal markers `[user]\n` and `[assistant]\n` into alternating few-shot turns. **An `assert len(...) % 2 == 0` enforces that every prompt file starts with `[user]` and ends with an `[assistant]` reply** — the conventional assistant reply is a short "Understood. I will wait for further instructions." When editing a prompt file, keep the markers paired or the script dies on import of the prompt.

`query/query.txt` is the runtime template: `[ENVIRONMENT]` is replaced with `json.dumps(environment)` and `[INSTRUCTION]` with the user's sentence. The stored `self.instruction` (the filled query) is re-appended on every feedback turn so the model keeps the output-format rules in view.

`create_prompt()` token-counts with `cl100k_base` and, if over `max_token_length - max_completion_length` (8000 − 2000), drops the two oldest messages and recurses. Those oldest messages are few-shot examples, so heavy truncation silently degrades output quality.

### The response contract is the real interface

The model must return a Python-dict-shaped JSON with `task_cohesion` (`task_sequence`, `step_instructions`, `object_names`), `environment_before`, `environment_after`, `instruction_summary`, and `question`. `task_sequence` entries come from the fixed ROBOT ACTION LIST in `prompt/prompt_function.txt` (`move_hand`, `grasp_object`, `release_object`, `detach_from_plane`/`attach_to_plane`, `open_by_rotate`/`slide`, `wipe_on_plane`, …); dual-arm variants take `left`/`right` as the argument. Environment state uses the STATE LIST in `prompt/prompt_environment.txt` (`on_something()`, `inside_something()`, `next_to()`, `inside_hand()`, `open()`, `closed()`).

`generate()` extracts the fenced block via `extract_json_part()`, writes the raw extraction to `last_response.txt` (gitignored — a debugging artifact for failed parses), replaces `'` with `"`, then `json.loads`. It reads `json_dict["environment_after"]` into `self.environment`; the caller feeds that back as the environment for the next instruction, so **multi-step scenarios are stateful and the model is the source of truth for world state**.

### Interactive feedback loop

After each response the `__main__` loop blocks on `input()`. Empty accepts the result and advances the environment; `q` exits; any other text is sent back with `is_user_feedback=True` for a regeneration. Accepted results are dumped to `./out/<scenario>/<i>.json`.

### Image / multimodal path (dual_arm only)

`office_p` passes an `image_path` (default [img/env_office_p2.jpg](img/env_office_p2.jpg), overridable with `--image`). When an image is present the environment dict is replaced by the literal string `'Refer to the attached image.'` and the user content becomes a `[{type: text}, {type: image, mime_type, data}]` list, where `data` is the raw bytes from `load_image()` (PNG/JPEG/WebP only, per `SUPPORTED_IMAGE_TYPES`). `get_text_content()` exists so token counting skips the image; `to_parts()` converts each entry into a `types.Part` (`from_text` / `from_bytes`) at `create_prompt()` time.

Because this example targets Gemini, `create_prompt()` returns a `types.Content` list rather than OpenAI messages: the system message is passed separately as `GenerateContentConfig(system_instruction=...)`, and the internal `'assistant'` sender maps to Gemini's `'model'` role. `max_output_tokens` is deliberately left unset — Gemini counts thinking tokens against it, so a cap truncates the task JSON; `max_completion_length` now only serves as the `create_prompt()` truncation headroom.

### Adding a scenario

Add an `elif scenario_name == '<name>':` branch in the script's `__main__` defining `environment` (or `image_path`) and `instructions`. Environment dicts and instructions live in Python, not in data files — that is the repo's convention for the non-VirtualHome examples. VirtualHome examples instead load numbered scenarios from `scenarios/`, `scenarios_highlevel/`, or `scenarios_variation/`, selected by uncommenting lines in `__main__`.

## Conventions

- `openai==0.28.1` legacy SDK: module-level globals (`openai.api_key`, `openai.api_base`, `openai.api_type`) and `openai.ChatCompletion.create(...)`. Do not migrate to the 1.x client without an explicit request — it would touch every duplicated class.
- Python is autopep8-formatted with aggressive line wrapping (~72–79 cols, hanging-indent argument lists). Match it.
- Prompt `.txt` files are the paper's published artifacts; treat edits to them as substantive experimental changes, not cleanup.
- Change notes go in `changelog/YYYY-MM-DD-NN-<slug>.md` and are **written in Chinese** (per the user's `code-changelog` skill). `NN` is a zero-padded sequence number within that date (`01`, `02`, ...) so the order of changes is recoverable — `changelog/` is gitignored, so filenames are the only ordering signal. Write the note as part of landing the change, without asking first.
