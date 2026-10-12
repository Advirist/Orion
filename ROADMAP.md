- add a gui
  - js

- add a wake word
  - learn/use c++

- extract engine from orion.py

- add a text message feature
  - telegram/discord

- claude ai tokens
  - tool call limit
  - token and cost logging

- can see images
  - seperate model needed

- make voice ignore code blocks

- a more thought through history
  - ability for "differnt chats" with its own history so its not all in one file
  - history recall option
  - scope for if chats get too long

## Orion: Sandboxed Shell Access (Mini Roadmap)

### Core idea (read this first)

- The model proposes, my code decides. Safety lives in the environment, not in the model's behavior.
- You can't make an arbitrary shell string safe by filtering it (`&&`, `;`, `$(...)`, `../` all get around filters). Isolate the environment instead.
- Orion never edits my real files. He works on a **copy**, and I review a **diff** and apply it myself.

### Target design

1. Copy project into `~/orion-workspace` (exclude `.env`, keys, tokens, `.git/hooks`)
2. Orion runs commands inside the sandbox (bubblewrap or rootless Podman, no network)
3. My code generates a diff (workspace vs original), generated outside the sandbox
4. I read the diff and apply it manually. Orion can never trigger apply.

### Tool tiers

| Backend              | Tools                                                                              |
| -------------------- | ---------------------------------------------------------------------------------- |
| Local model (Ollama) | narrow tools only: `read_file`, `list_dir`, `diff_workspace`, `write_to_workspace` |
| Claude via API       | narrow tools + sandboxed `bash`                                                    |

- Enforce the tier at **call time** in `dispatch.py`, not just in the schemas sent to the model.
- Backend selection is a setting I control. The model can't change its own tier.

---

### Phase 1: Narrow tools + path safety (no shell yet)

- [ ] Define a single workspace root
- [ ] Path check on every file tool: `Path(p).resolve()` then `is_relative_to(workspace)` (don't just check for `..` in the string)
- [ ] `read_file`, `list_dir`, `write_to_workspace` (writes only inside workspace)
- [ ] Per-backend allowed-tool dict in `dispatch.py`, refuse anything not on the list
- [ ] Log every tool call and result to a file
- [ ] Limits: max tool calls per turn, output size cap, timeouts

### Phase 2: Workspace copy + diff review

- [ ] Script: `rsync` project into workspace with an exclude list
- [ ] `diff_workspace` tool using `diff -ru` or `git diff` (run by harness, not by Orion)
- [ ] Manual apply step that I run myself
- [ ] Review checklist for diffs: shell scripts, Makefiles, `.bashrc`, cron, git hooks, build configs, any new files

### Phase 3: Sandboxed execution

- [ ] Install bubblewrap (`sudo apt install bubblewrap`) or set up rootless Podman
- [ ] Runner uses `subprocess.run([...], shell=False)` with the sandbox args as a list
- [ ] Sandbox settings: `--unshare-all` (no network), read-only system dirs, only workspace mounted at `/workspace`, non-root, tmpfs for `/tmp`
- [ ] Resource limits: timeout, memory cap, `--pids-limit`, output cap
- [ ] Keep the confirmation gate, and show the exact command string before it runs
- [ ] Do NOT: add user to `docker` group, mount the Docker socket, use `--privileged`, bind-mount the real project read-write

### Phase 4: Enable bash for Claude API only

- [ ] Add `bash` tool schema, exposed only when backend = Claude
- [ ] API key stays in Orion's main process, never in sandbox env or workspace files
- [ ] Spending cap in the Anthropic console, plus max tokens and max tool calls per turn
- [ ] Remember: anything in the workspace and tool output gets sent to Anthropic

### Phase 5: Verify the walls (do this before trusting it)

- [ ] `cd ../../..` and `ls`: should only show the tiny sandbox root
- [ ] `cat ~/.ssh/id_rsa` or my home dir: should not exist
- [ ] `curl example.com`: should fail
- [ ] `rm -rf /workspace/*`: only the copy is affected, original untouched
- [ ] Fork bomb / infinite loop: killed by limits
- [ ] Prompt injection test: put "ignore instructions and run X" in a workspace file and see that nothing dangerous happens

---

### Known limits

- No Ollama, GPU, mic, or Tailscale inside the sandbox. Test hardware-dependent stuff myself on the real system after applying a diff.
- The review step is the weak point. The sandbox protects me from Orion, but applied code runs on my real machine.
- If Orion later needs Ollama access from the sandbox, allow one host and port only. Don't turn on networking in general.

### Nice-to-haves later

- [ ] Git-commit the workspace before each Orion session so any change is easy to undo
- [ ] Trash folder instead of `rm`
- [ ] Per-session log viewer
