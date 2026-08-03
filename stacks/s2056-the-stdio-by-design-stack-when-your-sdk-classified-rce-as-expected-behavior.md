# [S-2056] · The STDIO-"By Design" Stack

You connect your agent to an MCP server. The SDK lets you specify a `command` and `args`. Those args are built from a string the model produced — which read a GitHub issue, a search result, an email. The OS spawns a process running whatever the attacker slipped into that string. Anthropic's position: working as designed. No SDK patch is coming.

This is the MCP STDIO command-injection class. It has 40+ CVEs, affects every SDK language Anthropic ships, and the upstream vendor says it's your threat model to manage.

## Forces

- Every MCP server that shelles out to a command built from model-supplied input is exploitable the moment that input is attacker-controlled
- The "local-only" label on STDIO transport convinced teams their agents weren't network-reachable — they are
- "By design" means no upstream fix: the attack surface is structural, not patchable at the SDK level
- The fix surface (allowlist validation) is application-level — every team must implement it independently

## The move

**1. Name the attack class: command-argument injection via STDIO transport**

The MCP SDK's `StdioServerParameters(command=..., args=...)` passes arguments directly to the OS process-spawn layer with no sanitization. Any model-supplied string that reaches these parameters is a potential RCE vector.

The CVE family (CVE-2026-30623, CVE-2025-54994, CVE-2026-40933, and 37 more) all share the same root cause: the SDK treats the command and args as opaque strings to pass through, not as attacker-controlled input to validate.

**2. Know the trigger condition**

Not every MCP server is vulnerable. Only servers that:
- Use STDIO transport (not SSE/HTTP)
- Construct `command` or `args` from any string that originated outside your trust boundary (user input, web content, tool output, another agent's output)

Exploitable chains seen in the wild:
- `npx create-mcp-server-stdio` — directly concatenates user input into `exec()` (CVE-2025-54994, patched)
- `GPT Researcher` — STDIO injection, patched after CVE-2025-65720
- `Flowise` MCP adapter — unsafe stdio serialization, CVSS pending (CVE-2026-40933, patched in 3.1.0)
- `LangChain-Chatchat`, `Upsonic`, `LangFlow`, `Agent Zero`, `Fay` — received responsible disclosure, unpatched at time of CSA advisory (April 2026)

**3. The mitigations (in order of robustness)**

```
// Layer 1: Allowlist enforcement (application-level, before process spawn)
// mcpshield pattern — single import validates every stdio launch
import { validateStdioLaunch } from '@mcpshield/core'

// mcpshield validates command + args + env against a declared allowlist
// BEFORE the OS spawns the subprocess
const params = validateStdioLaunch({
  command: 'npx',
  args: ['-y', '@my-org/mcp-server'],
  // Allowed paths, allowed env vars — any deviation throws before exec()
  allowlist: {
    commands: ['/usr/bin/npx', '/usr/local/bin/npx'],
    args: [{ pattern: '^-y$', maxLength: 5 }, { pattern: '^@[a-z0-9-]+/[a-z0-9-]+$', maxLength: 64 }],
    env: ['PATH', 'HOME']
  }
})
await spawnMcpServer(params)
```

```
// Layer 2: Transport migration — eliminate STDIO for anything model-influenced
// Switch to SSE/HTTP transport for agent-accessible MCP servers
const serverConfig = {
  transport: 'sse',           // not 'stdio'
  auth: { type: 'bearer', token: process.env.MCP_SERVER_TOKEN },
  // SSE transport does not accept command/args — no injection surface
  url: 'https://internal-mcp.example.com/sse'
}
```

```
// Layer 3: Architecture-level — never pass model output into spawn parameters
// Policy: model output → string → must pass through a sanitizer before reaching StdioServerParameters
function sanitizeToolArgs(raw: string): string {
  // Block shell metacharacters, newlines, path traversal
  if (/[;&|`$(){}$<>`\\]|[\r\n]/.test(raw)) {
    throw new Error('Blocked unsafe character in MCP stdio args')
  }
  return raw.trim().slice(0, 256)
}
```

**4. The four-mitigation matrix**

| Mitigation | Effort | Scope | Upstream dependency |
|---|---|---|---|
| mcpshield allowlist | Low | All stdio launches | No — application-level |
| Transport migration (SSE) | Medium | New servers | No — architectural |
| Argument sanitizer | Medium | Per-server | No — code-level |
| SDK upgrade | Ongoing | Vendor-provided | Yes — not fixing this |

**5. The detection signal**

STDIO command injection leaves a forensic trace: a process spawned with unexpected argv. Monitor:
- `execve()` calls where `argv[0]` doesn't match the declared allowlist
- Any MCP server process whose parent PID isn't the expected launcher
- New process creation events from MCP server subprocesses that spawn their own children

## Receipt

> Verified 2026-08-03 — Research synthesis from: OX Security advisory (April 15, 2026), CSA research note (CVE-2026-30623 family), NVD entries CVE-2026-40933, CVE-2025-54994, mcpshield GitHub (csinexus/mcpshield, MIT), LiteLLM security advisory. 40+ CVEs confirmed across Python/TS/Java/Rust SDKs. mcpshield is the only production-grade mitigation available for unpatched stdio servers.

## See also

- [S-978 · The Tool-Catalog Poisoning Stack](/stacks/s978-the-tool-catalog-poisoning-stack-when-your-mcp-server-returns-poisoned-responses-at-runtime.md) — tool output as injection vector (complementary: this entry is command-level, S-978 is response-level)
- [S-375 · Agentic Prompt Injection: Defense-in-Depth](/stacks/s375-agentic-prompt-injection-defense-in-depth-for-production.md) — the broader injection defense context
- [S-1391 · The MCP Gateway Registry Stack](/stacks/s1391-the-mcp-gateway-registry-stack-when-your-agent-tool-sprawl-becomes-a-security-nightmare.md) — MCP security governance at scale
- [S-1459 · The Trusted-File Escape Stack](/stacks/s1459-the-trusted-file-escape-stack-when-your-agent-stays-inside-but-escapes-via-the-trusted-host-toolchain.md) — escape via host toolchain (different vector, same trust-boundary failure)
