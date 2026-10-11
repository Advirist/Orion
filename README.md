# Orion

A personal AI assistant inspired by Jarvis, written in Python and powered by a local [Ollama](https://ollama.com) model. Orion is an **observer**: it can look at your files, git repository, computer, and the weather, and answer questions about what it finds. It cannot change anything. You can talk to it by typing or by voice, and it can answer out loud.

Every answer that relies on a tool is checked by a second pass that compares Orion's reply against what the tools actually returned.

## Status

In active development and used daily on Ubuntu Linux. Everything runs locally, with one exception: the weather tool contacts a public weather service.

## What it can do

27 read-only tools, grouped by what they inspect.

| Area                         | Tools                                                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Files (inside `playground/`) | `list_directory`, `read_file`, `search_files`, `directory_tree`, `file_stats`, `file_diff`, `find_duplicates` |
| Git (Orion's own repository) | `git_status`, `git_log`, `git_diff`, `git_branch`, `git_show`, `git_blame`, `git_stash_list`                  |
| System                       | `cpu_memory_status`, `disk_usage`, `battery_status`, `network_status`, `running_processes`, `uptime`          |
| Code                         | `lint_file` (syntax check only; never runs code), `list_dependencies`, `todo_scanner`                         |
| Media                        | `image_info` (metadata only), `pdf_text_extract`                                                              |
| Time and weather             | `current_datetime`, `weather_check` (uses the free Open-Meteo service)                                        |

If you ask Orion to write something, it puts the text in its reply for you to copy. It never writes files itself.

## How it works

1. You type a message, or speak it.
2. The model (Qwen3 8B) decides whether it needs a tool and calls one.
3. `tools/dispatch.py` checks the call against the tool's real signature, then runs it.
4. The result goes back to the model, which answers in plain sentences.
5. The verifier compares that answer to the tool results from the same turn. If it doesn't match, Orion is asked to answer again, and the mismatch is logged.
6. If voice mode is on, the reply is spoken.

### Safety design

- **Sandboxed file access.** File tools only work inside `playground/`. Absolute paths are rejected, `..` tricks are caught by resolving paths before checking containment, and recursive tools skip symlinks.
- **No free-form commands.** Git and dependency tools run against fixed locations. Commit references must be `HEAD`, `HEAD~N`, or a hex hash, and file paths are validated and passed after `--`, so the model can't smuggle in git options.
- **Argument validation.** Unknown or missing arguments return a clear error listing what the tool accepts. They are never silently ignored.
- **Mutating-tool gate.** Tools flagged as mutating require a typed `yes` before they run. No mutating tools are currently enabled; `write_file` exists in the code but is switched off.
- **Fails loudly at startup.** Orion refuses to launch if tool schemas and the registry disagree, if two tools share a name, or if a tool is misnamed in the live-data list.
- **Bounded output.** Large results are truncated so one call can't flood the model's context.
- **Stale readings removed.** Results from live-data tools (battery, memory, git status, directory listings) from earlier in a conversation are replaced with a short note before each model call, so Orion re-checks instead of repeating an old number. The saved history is not modified.

### Verification layer

After a turn that used tools, a second model call judges whether Orion's reply accurately reflects every tool result from that turn, including earlier failed attempts. Mismatches are logged and Orion retries once.

It was evaluated against a fixed set of known failure patterns before being trusted. It has limits you should know about:

- It only runs on turns where a tool was called, so it can't catch a made-up answer given with no tool call.
- The assistant and the verifier are the same model, so they can share blind spots.
- You can always see the raw `[Tool call result: ...]` line in the terminal. Treat it as the source of truth.

## Project structure

```
Orion/
├── orion.py              # main loop
├── requirements.txt
├── settings/
│   ├── config.py         # model names, paths, context size, Ollama connection
│   └── prompts.py        # system prompt
├── llm/
│   ├── model_client.py   # streams replies from the model
│   ├── verifier.py       # checks replies against tool results
│   └── context.py        # removes stale live-data results before each call
├── tools/
│   ├── __init__.py       # combines all tool modules and runs startup checks
│   ├── dispatch.py       # argument validation and the confirmation gate
│   ├── _common.py        # shared path checks, argument parsing, truncation
│   ├── filesystem.py     # list_directory, read_file, search_files
│   ├── file_inspection.py
│   ├── git.py
│   ├── system.py
│   ├── code_inspection.py
│   ├── clock.py
│   ├── media.py
│   └── weather.py
├── storage/
│   ├── history.py        # saves and loads conversation history
│   └── errors.py         # logs verifier mismatches and failed commands
├── voice/
│   ├── voice_io.py       # speech-to-text and text-to-speech
│   └── models/           # Piper voice files
└── playground/           # the folder file tools are allowed to see
```

Adding a tool module takes one import line and one list entry in `tools/__init__.py`.

## Setup

**Requirements:** Python 3.10 or newer (developed on 3.13 and 3.14), Ollama, and Linux. Voice uses `aplay`, so it is Linux-oriented.

1. Install system packages:
   ```bash
   sudo apt install ffmpeg alsa-utils
   ```
2. Pull the model:
   ```bash
   ollama pull qwen3:8b
   ```
3. Create a virtual environment and install dependencies. The list is large because it includes PyTorch and CUDA libraries:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Add a Piper voice. Download an `.onnx` voice and its matching `.onnx.json` file into `voice/models/`, keeping the two filenames identical apart from the extension. Then set `PIPER_VOICE_MODEL` in `settings/config.py` to the `.onnx` filename.
5. Run it:
   ```bash
   python orion.py
   ```

Type `/e` at the prompt to end a session.

### Running the model on another machine (optional)

By default Orion talks to Ollama on `localhost`. To use a model running elsewhere, such as a desktop with a GPU reached over [Tailscale](https://tailscale.com), create a `.env` file:

```
OLLAMA_HOST=http://<other-machine-address>:11434
```

If the model can't be reached, Orion retries, then exits with a clear message after 3 consecutive failures.

### Model and memory notes

- One model, `qwen3:8b`, does both jobs, so only one needs to fit in GPU memory. On an 8 GB card, a context window of 12288 tokens (`NUM_CTX` in `settings/config.py`) stays fully on the GPU. Ollama's default of 4096 is too small for 27 tool descriptions and silently cuts them off.
- Check what's loaded with `ollama ps`. If `PROCESSOR` shows a CPU/GPU split, lower `NUM_CTX`.
- The first reply after the model has been idle is slow while it loads.

## Using voice

- At the prompt, press Enter with nothing typed to start recording, then Enter again to stop. Type anything instead to skip voice.
- Once you've used voice, Orion speaks its replies and listens for your next message. Press Ctrl+C while recording to go back to the type-or-voice prompt.
- Speech recognition uses Whisper (`small`) and speech output uses Piper, both running locally.
- Orion uses your system's default microphone and remembers the last one it used. To force a specific microphone, set `DEFAULT_MIC_DEVICE` in `settings/config.py` to part of its name.
- USB microphones sometimes record silence until they are unplugged and replugged.

## Known limitations

- The conversation history grows without limit and is sent to the model on every call. Only stale live-data results are trimmed.
- A small local model sometimes picks the wrong one of two similar tools, or paraphrases results loosely. The verifier catches contradictions, not every embellishment.
- The weather tool sends the city name you ask about to Open-Meteo. It reports which place it matched, since names can be ambiguous.
- Code blocks in replies would be read aloud in voice mode.

## Roadmap

- A graphical interface
- A spoken wake word, alongside push-to-talk
- Trimming or summarizing old history
- An optional hosted-model backend (the Anthropic API) in place of local Ollama
- Image understanding through a vision model (`image_info` currently reads metadata only)
- A way to send messages to and from Orion (design not yet decided)
