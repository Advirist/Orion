# Orion

A personal AI assistant inspired by Jarvis, built in Python on top of a local Ollama model. Orion supports tool-calling (filesystem access, sandboxed to a dedicated playground directory), streaming responses, a confirmation gate for any mutating action, and an independent verification layer that checks the assistant's claims against actual tool results before they're shown to the user.

## Status

Actively in development. Currently local-only (Ollama), with a planned future migration to a cloud LLM. Tool access is intentionally sandboxed to a `playground/` directory during this development phase.

## Features

- **Tool-calling**, via Ollama's function-calling support:
  - `list_directory` — list contents of a directory within the sandbox.
  - `read_file` — read a file's contents, with pagination for large files.
  - `write_file` — write or overwrite a file, with a confirmation prompt before any overwrite.
- **Sandboxing** — every filesystem tool resolves and validates paths against a fixed playground root. Absolute paths are rejected, and path traversal (`../`) is blocked via containment checks.
- **Confirmation gate** — any tool marked as mutating requires explicit user confirmation (via terminal prompt) before it runs.
- **Streaming responses** — model output streams live to the terminal rather than waiting for a complete response.
- **Verification layer** — after a tool call, a separate model checks whether the main assistant's response accurately reflects what the tool actually returned. If a mismatch is detected, the assistant is asked to reconsider and respond again before the user sees the answer. All flagged mismatches are logged for review.
- **Persistent history** — conversation history is saved to disk between sessions.

## Project structure

```
Orion/
├── orion.py            # Main entry point — the conversation loop
├── config.py           # Shared constants (model names, sandbox root)
├── prompts.py           # System prompt (not committed — see below)
│
├── llm/
│   ├── model_client.py  # Talks to the main conversational model
│   └── verifier.py      # Talks to the verification model
│
├── storage/
│   ├── history.py       # Conversation history load/save
│   └── errors.py        # Logs flagged verifier mismatches
│
├── tools/
│   ├── __init__.py       # Aggregates tool schemas and registry
│   ├── dispatch.py       # Routes a tool call to its implementation
│   └── filesystem.py     # Tool implementations (list/read/write)
│
├── tests/
│   └── test.py           # Standalone verifier test cases
│
└── playground/           # Sandboxed directory tools operate within
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com), running locally
- The following models pulled via Ollama:
  - `qwen2.5:7b` — main conversational model
  - `qwen3:8b` — verification model

## Setup

1. Clone the repo and create a virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install ollama
   ```
3. Pull the required models:
   ```
   ollama pull qwen2.5:7b
   ollama pull qwen3:8b
   ```
4. Create `prompts.py` in the project root, defining a `SYSTEM_PROMPT` string. This file is intentionally not committed — see below.
5. Update `config.py` if your playground directory or model names differ from the defaults.
6. Run it:
   ```
   python orion.py
   ```
   Type `/e` at any prompt to end the session.

## A note on `prompts.py`

`prompts.py` is excluded from version control, since it contains Orion's personality/system prompt, which is a personal, tunable part of the project. To run Orion yourself, create this file with your own `SYSTEM_PROMPT` string before running `orion.py`.

## Design notes

- **Every filesystem tool is scoped to `playground/`.** This is deliberate: tool capabilities are being built and tested incrementally, with safety checks (path containment, confirmation prompts, result verification) proven out before any expansion beyond the sandbox is considered.
- **The verification layer is a safety net, not a guarantee.** It catches cases where the assistant's stated summary doesn't match the actual tool result, but it depends on a second model's judgment, which — like any model — isn't perfect. It has been tested against a fixed set of known failure patterns before being trusted to run automatically.
- **Tools distinguish between read-only and mutating actions.** Only mutating actions require confirmation before running, checked centrally at the dispatch layer rather than duplicated per-tool.

## Roadmap

- Whitelisted, argument-validated shell command execution (still sandboxed initially).
- Migration to a cloud LLM once local development is stable.
- Possible model routing (a coding-specialized model alongside the general assistant model).
