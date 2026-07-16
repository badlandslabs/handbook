# S-1114 · The MCP Config Is the Attack Surface Stack — When Your Server Launch File Runs Arbitrary Commands

Your MCP server passes every security review. Your prompt injection guardrails are solid. Your agent sandbox is tight. Then a dependency updates, a new tool gets added to your config, or a developer clones a repository with a pre-built `mcp.json` — and arbitrary code executes at the moment the config loads. No SQL injection. No buffer overflow. Just a config file with a `command` field pointing somewhere it shouldn't.

In April 2026, OX Security disclosed what became known as **"The Mother of All AI Supply Chains"**: MCP's STDIO transport feeds configuration values directly into OS command execution without sanitization. This isn't a code vulnerability in a specific server — it's a **design property of the transport layer** implemented across Python, TypeScript, Java, and Rust SDKs. 150+ million SDK downloads. 200,000 estimated deployed servers. 7,000+ exposed on the public internet. Anthropic's position: working as designed, sanitization is the developer's responsibility.

## Forces

- **The trust boundary is the config file.** In every traditional protocol, configuration governs settings. In MCP STDIO, configuration governs *process creation* — the `command` field tells the OS what to execute. When you load an MCP server config, you are loading a process invocation.
- **SDK ergonomics hide the execution.** The `mcp.json` config file looks declarative — a structured manifest of tool definitions. The implementation detail that it's also a `subprocess.Popen` call is invisible to developers. Reviewers checking for "does this config expose sensitive data" miss "does this config tell the OS to run something."
- **The config travels further than you think.** MCP configs get committed to repos, shared in issues, included in onboarding templates, and bundled into workspace setups. A malicious config has the same trust surface as a `package.json` with a post-install script — except there's no `npm audit` equivalent for MCP server configs.
- **Anthropic called it by-design.** Unlike a traditional CVE where you wait for a patch, the upstream position as of May 2026 is that this behavior is intentional. Teams cannot plan on an upstream fix arriving. The defense is architectural, not patchable.
- **The compound blast radius.** A poisoned config doesn't just run a command — it runs in the context of the agent host, with the same OS permissions, environment variables, and file system access. The LLM sees the compromised server as a trusted tool. The attacker's code runs authorized.

## The move

**The fix lives in three layers: the config boundary, the spawn guard, and the runtime monitor.**

### Layer 1 — Config provenance gate

Every MCP server config loaded in production must come from a reviewed, version-pinned source. The critical rule: **never load a config you didn't write**.

```
# Anti-pattern: auto-loading configs from repo roots
mcp import ./workspace/.mcp/mcp.json

# Pattern: pinned config with hash verification
mcp add server --digest sha256:abc123... \
  --command "python3" \
  --args "/reviewed/path/server.py"
```

Treat the config file as executable code for review purposes. Does the `command` field match the expected binary? Are the arguments constrained to a known-good set? Does the config reference a path inside the reviewed codebase or an external dependency?

**The config review checklist:**
- `command`: is this the expected binary at the expected path?
- `args`: are all arguments statically known, not derived from environment or user input?
- `env`: are environment variables explicitly set, not inherited wholesale?
- `cwd`: is the working directory locked to a known-safe path?
- Source: was this config written by your team, or imported from elsewhere?

### Layer 2 — Spawn guard: sandbox the process before it runs

Even a reviewed config can be compromised at runtime (dependency update, symlink attack, path hijack). Isolate every MCP server process.

```
# Process-level isolation
capsicum(4)     # FreeBSD: capability mode — drop all rights except needed fds
seccomp(2)      # Linux: syscall allowlist — block execve/shell commands
namespace       # Linux: mount + PID namespace — isolate filesystem view
# Or via container:
docker run --read-only --no-new-privileges --cap-drop ALL \
  --tmpfs /tmp your-mcp-server
```

The goal: even if the config runs a malicious command, the process has no write access to the filesystem, no ability to spawn further processes, and no access to credentials outside its declared scope.

For MCP servers that must access the filesystem, use **bind mounts with read-only or narrow write paths** rather than full filesystem access. A server that only needs to read `./data/` should not see `/home/`, `/etc/`, or `~/.ssh/`.

**Process allowlisting** is the most effective defense against the STDIO design:

```
# macOS: Apple Sandbox (sandbox.sb)
(version 1)
(allow process-exec)
(deny default)
(allow process-exec* (literal "/reviewed/path/server.py"))

# Linux: seccomp allowlist (seccomp-profile.json)
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "syscalls": [
    {"names": ["read", "write", "close", "exit"], "action": "SCMP_ACT_ALLOW"}
  ]
}
```

### Layer 3 — Config state monitor

The config file is the most dangerous because it changes infrequently — security reviews run once, and the file silently evolves between reviews. Set a watch.

```
# Watch for config file modifications
inotifywait -m -e modify -e create \
  /path/to/.mcp/mcp.json | while read; do
  # Alert + re-verify digest before next agent restart
  sha256sum /path/to/.mcp/mcp.json
  # Compare against known-good baseline
  diff <(sha256sum /path/to/.mcp/mcp.json) /trusted/mcp.json.sha256
done
```

For MCP configs committed to repositories, **require code review for any change to the `command` or `args` fields** specifically — not just the config file as a whole, but the executable directives within it. A standard PR review misses this because the fields look like "just configuration."

### Layer 4 — SSE transport as the hardening target

The STDIO transport is the vector. The **SSE (Server-Sent Events) transport** is the safer alternative for production deployments — it communicates over HTTP rather than spawning child processes. If your MCP SDK and server support SSE, migrate the transport:

```
# Instead of stdio:
mcp-server --transport stdio

# Use SSE:
mcp-server --transport sse --port 8080
# Host agent connects via HTTPS to https://server:8080/sse
```

SSE eliminates the child process entirely, removing the config-as-execution attack surface. The tradeoff: SSE requires the server to be network-reachable and introduces a different trust model (network-level rather than process-level). Evaluate per server.

## Verification

1. **Load an attack config** with a benign `command` field (`echo "injected"`): confirm the host does not execute it when loaded in a sandboxed environment without the explicit `command` field.
2. **Audit all MCP configs** in your repos with `grep -r '"command"' .mcp/`: flag any that reference external paths or non-pinned tool sources.
3. **Run MCP servers in containers** with `--read-only --cap-drop ALL` and confirm they still function with their declared tools.
4. **Migrate critical servers** to SSE transport: confirm tool functionality is preserved without stdio spawn.

## See also

- [S-285 · MCP's Security Trap: The Standard That Ships Compromised](s285-mcp-security-trap-the-standard-that-ships-compromised.md) — compound probability of compromise across N MCP servers
- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — ecosystem-level CVE proliferation and marketplace compromise
- [S-874 · The MCP Config Drift Stack](s874-the-mcp-config-drift-stack-when-your-agent-has-a-secret-security-hole-you-dont-know-about.md) — silent permission scope expansion between review cycles
