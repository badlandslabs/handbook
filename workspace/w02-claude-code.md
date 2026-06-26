# W-02 · Claude Code

Claude Code is a terminal-based AI coding assistant. It reads your repo, runs tools (shell, file edit, grep, search), and acts on your codebase with your permission.

## Forces
- IDE plugins are passive (suggest); Claude Code is active (reads context, runs commands, edits files)
- It works in the terminal, so it runs where your code runs — servers, containers, CI
- Autonomous mode moves fast and can make changes you didn't intend; permissions matter
- It's Anthropic-native, so it works best with Claude models, but can route to local models via env var

## The move

**Install:**
```bash
npm install -g @anthropic-ai/claude-code
claude login  # OAuth via browser
```

**Key modes:**
- `claude` — interactive session (reads your codebase, asks permission before actions)
- `claude -p "prompt"` — non-interactive, prints output and exits
- `claude -c` — continue the most recent session

**Route to a local model (no API cost):**
```bash
ANTHROPIC_BASE_URL=http://localhost:11435 ANTHROPIC_API_KEY=ollama claude -p "explain this file"
```
See [S-01](../stacks/s01-local-model-dispatch.md) for the full receipt.

**Key settings (`.claude/settings.json` in your repo):**
```json
{
  "permissions": {
    "allow": ["Bash(git *)", "Bash(npm *)", "Read", "Edit"]
  }
}
```

**Skills (slash commands):** Custom workflows defined in `.claude/skills/`. Invoke with `/skill-name`. Create your own to encode project-specific procedures.

**CLAUDE.md:** Place a `CLAUDE.md` in your repo root to give Claude Code standing instructions about the project. It reads this at session start.

## Receipt
> Verified 2026-06-25 — this entire session runs inside Claude Code on Windows 11. Non-interactive `-p` flag confirmed. `--base-url` flag confirmed absent (returns `unknown option`). Local model dispatch via env var confirmed working.

## See also
[S-01](../stacks/s01-local-model-dispatch.md) · [S-10](../stacks/s10-mcp.md) · [W-01](w01-ai-dev-environment.md)

## Go deeper
Keywords: `Claude Code` · `CLAUDE.md` · `MCP servers` · `Claude Code hooks` · `agentic coding` · `claude -p`
