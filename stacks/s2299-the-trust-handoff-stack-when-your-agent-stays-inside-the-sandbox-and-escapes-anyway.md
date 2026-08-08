# S-2299 · The Trust Handoff Stack — When Your Agent Stays Inside the Sandbox and Escapes Anyway

Your agent never broke the sandbox. It followed every rule, made every tool call within policy, and never attempted a kernel exploit. Then the host got owned anyway — not through the sandbox boundary, but through the gap between what the sandbox restricts and what a trusted downstream component later does with agent-generated content.

This is the Trust Handoff Flaw: the assumption that restricting what an agent *does* restricts what *gets done* through the agent.

## Forces
- Sandboxing assumes the boundary between agent and host is the trust boundary — but the real boundary is between sandboxed agent and *every downstream consumer* of agent output
- Workspace files (README, configs, hooks, package manifests) are legitimately written by the agent, making them invisible to sandbox enforcement
- Trusted tooling outside the sandbox — git hooks, package managers, CI runners — assumes the human wrote the files it processes
- Capability minimization restricts what the agent can call; sandboxing restricts what those calls affect. Neither addresses files written by the agent that downstream tools later execute
- The agent has a legitimate reason to write every poisoned file type: a coding agent that can't write config files is broken

## The move

**Treat every file the agent writes as untrusted input to every tool that will ever read it.**

The Trust Handoff Flaw has four structural failure modes. Each requires a different fix.

### Failure Mode 1: Configuration Poisoning

The agent writes files that a trusted component reads at an *uncontrolled future time*.

```bash
# Agent legitimately writes to .git/hooks/post-commit
# Later: git commit → runs hook as user → arbitrary code execution

# Agent writes to .devcontainer.json
# Later: VSCode opens project → applies devcontainer config → runs arbitrary command

# Agent writes to .vscode/settings.json  
# Later: VSCode applies settings → extension executes arbitrary code

# Agent writes to package.json scripts
# Later: npm install → runs postinstall hook → arbitrary code execution
```

**Fix:** Deny write access to lifecycle-hook paths (`*.git/hooks/*`, `.devcontainer/`, `.vscode/`, `package.json` scripts) *regardless of sandbox classification*. These paths are not workspace content — they are execution contracts.

### Failure Mode 2: Denylist Incompleteness

The sandbox blocks known-bad commands but not their indirect paths.

```python
# Denylist approach: block "curl", "wget", "pip install"
# But agent writes a Python script that calls subprocess.run(["curl", ...])

# Or: agent writes a shell script that uses ${HOME}/bin/curl (not blocked)

# Or: agent writes a symlink at /tmp/curl → /usr/bin/curl
# Now "curl" in denylist doesn't match the symlink path
```

**Fix:** Denylists are incomplete by construction. Use allowlists with explicit capability declarations. If the agent's workflow legitimately requires network access, declare it as a named capability with a purpose, not a blanket deny-on-known-bad.

### Failure Mode 3: Privileged Local Daemon

A trusted daemon running *outside* the sandbox processes agent-generated files.

```bash
# Agent writes to a watched directory
# Later: inotify/watchman detects change → triggers daemon action
# Daemon runs with elevated privileges → executes agent's payload

# Agent writes to /dev/shm or /tmp with sticky bit
# Later: another process in the same namespace reads and executes

# Agent writes a .so library to a location ld.so.conf loads from
# Later: any binary using the dynamic linker loads the malicious .so
```

**Fix:** Audit every daemon, watcher, and auto-loader on the host. For each: determine if it processes files written by the agent's UID or within the sandbox's filesystem scope. If yes, it is in the attack surface. Isolate or disable any auto-loader that triggers on agent-writable paths.

### Failure Mode 4: Unsafe Command Allowlist

The sandbox allows a command; the command allows arbitrary execution.

```bash
# "git" is in the allowlist
# git hooks, git config, git aliases → arbitrary code execution via git

# "docker" is in the allowlist
# docker run --privileged → breakout from container
# docker socket accessible → host takeover

# "npm" is in the allowlist
# npm install → runs package postinstall scripts as root-equivalent

# "python" is in the allowlist
# python -c "import os; os.system('...')" → arbitrary code execution
```

**Fix:** Every allowed command needs a behavioral profile. Not just "can call git" but "can call `git status`, `git log`, `git diff` only — not `git commit` (which triggers hooks) or `git config` (which writes user-level config with code execution). Use command-level allowlists with argument parsing, not binary-level allowlists.

### The Architectural Principle

```
Sandbox boundary ≠ Trust boundary

Trust boundary = intersection of:
  - What the agent can write
  - What downstream tools will consume
  - What those tools will execute with elevated privilege
```

Every time the agent writes a file, it is expanding the intersection. The agent is not writing to a void — it is writing to a shared world where trusted tools will eventually process that content.

The fix is not more sandboxing. It is **trusted-component hardening**: assume every file the agent creates is a potential exploit payload until it has passed through a deprivileging layer (content scanner, format validator, privilege-stripper) before reaching any component with execution capability.

## Receipt
> Verified 2026-08-07 — CSA Research Note (2026-07-22): "AI Coding Agent Sandbox Escapes: The Trust Handoff Flaw." Pillar Security, week-of-sandbox-escapes (July 20, 2026). Seven CVEs across Cursor (CVE-2026-48124), OpenAI Codex CLI, Google Gemini CLI, Google Antigravity. Common finding: none broke the sandbox directly. All exploited the gap between sandboxed write operations and trusted downstream reads. Source: https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/07/CSA_research_note_ai_coding_agent_sandbox_escapes_20260722-csa-styled.pdf

## See also
- [S-2274 · The Isolation Spectrum Stack](stacks/s2274-the-isolation-spectrum-stack-when-your-agent-runs-code-and-nobody-drew-the-fence.md) — architectural isolation options and their enforcement boundaries
- [S-1720 · The Tool Poisoning Defense Stack](stacks/s1720-the-tool-poisoning-defense-stack-when-your-approved-mcp-server-pulls-a-fast-one-at-runtime.md) — runtime verification for supply chain integrity
- [S-2291 · The MCP Supply Chain Stack](stacks/s2291-the-failure-domain-stack-when-your-agent-succeeds-at-failing-and-no-one-catches-it.md) — credential scoping for tool registry attacks
