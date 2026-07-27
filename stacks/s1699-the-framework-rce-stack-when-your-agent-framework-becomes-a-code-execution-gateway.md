# S-1699 · The Framework-RCE Stack — When Your Agent Framework Becomes a Code Execution Gateway

On May 7, 2026, Microsoft published research confirming what security researchers had warned about since the agentic AI wave began: **prompt injection is no longer a content problem. It is a code execution primitive.** Two critical CVEs in Semantic Kernel — the framework powering Microsoft 365 Copilot and Azure agent stacks — demonstrated that an attacker need not exploit a memory corruption bug or deploy a malicious binary. A single crafted document, vector store entry, or chat history entry, retrieved by the agent and passed through the framework's plugin layer, is sufficient to run arbitrary code on the host machine.

The attack surface is the framework itself: every layer that bridges model output to code execution — vector stores, file plugins, Python plugins, kernel functions — is now an attack surface. This is the **Framework-RCE Stack**.

## Forces

- **Agent frameworks are designed to bridge model output to code execution.** Semantic Kernel, LangChain, and their peers are built on the premise that model-generated function calls are trustworthy enough to route to real code. That assumption holds for developer-written prompts. It collapses when attacker-controlled content reaches the same function call path.
- **Indirect prompt injection puts attacker content inside trusted retrieval.** The attacker's document lives in a vector database, a file share, or a chat history — all contexts the agent considers trustworthy. The agent retrieves it, the LLM processes it, the framework acts on it. No jailbreak required. No direct API access needed.
- **The vulnerability lives in the framework, not the model.** CVE-2026-26030 (CVSS 9.9) exploits the `InMemoryVectorStore` filter functionality in Semantic Kernel Python SDK < 1.39.4 — attacker-controlled vector field values are passed to `eval()`. CVE-2026-25592 (CVSS 9.8) exploits the `SessionsPythonPlugin` in Semantic Kernel .NET SDK < 1.71.0 — path traversal in `DownloadFileAsync`/`UploadFileAsync` writes arbitrary files to the host. Neither is a model behavior. Both are framework design decisions.
- **The patch is insufficient without architectural rethinking.** Updating to patched versions removes the specific CVEs, but every plugin that passes model-controlled strings into `eval()`, `exec()`, `open()`, `__import__()`, or dynamic SQL is one update away from the same class of vulnerability. The question is not "are you patched?" — it is "which of your plugins treat model output as trusted code?"

## The move

### The exploit chain (both CVEs)

**CVE-2026-26030 (Python, InMemoryVectorStore):**
1. Attacker stores a malicious document containing a crafted value in a vector store field.
2. Agent retrieves the document as part of its context (RAG, tool result, memory fetch).
3. LLM processes the document, extracts the field value, and includes it in a semantic search filter against `InMemoryVectorStore`.
4. The filter expression — containing the attacker's payload — is passed directly to `eval()` without sanitization.
5. Code executes on the host.

```python
# Vulnerable pattern (pre-fix):
# The InMemoryVectorStore filter parameter flows to eval()
filter_expr = f"item['{key}'] == {value}"  # attacker controls value
# Patched: use parameterized filters, never eval() on user input

# Corrected approach:
from semantic_kernel.data import VectorStoreFilter

# Use structured filter API instead of string eval
filter_obj = VectorStoreFilter.equal(key, sanitized_value)
results = store.search(filter=filter_obj)
```

**CVE-2026-25592 (.NET, SessionsPythonPlugin path traversal):**
1. Attacker injects a path traversal payload (`../../startup/evil.dll`) into a function argument the agent will pass to `DownloadFileAsync`.
2. Agent, following its instructions, calls `DownloadFileAsync` with the attacker-controlled path.
3. Without path validation, the plugin writes the file outside the intended sandbox directory.
4. Depending on the write location, the attacker achieves arbitrary file write → potentially RCE.

```csharp
// Vulnerable pattern (pre-fix):
var path = userControlledPath; // attacker controls this
await plugin.DownloadFileAsync(path, destination);

// Patched: enforce allowed directories
var safePath = Path.GetFullPath(path);
if (!safePath.StartsWith(allowedDirectory)) {
    throw new SecurityException("Path traversal blocked");
}
await plugin.DownloadFileAsync(safePath, destination);
```

### The five-layer defense stack

**Layer 1 — Treat all plugin I/O as untrusted.** Every parameter that flows from a retrieval source (vector store, file, memory, MCP server response) to a plugin function is untrusted input. Apply the same validation you'd apply to direct user input: type checking, allowlist validation, length limits, no raw string interpolation into dangerous operations.

**Layer 2 — Deny dangerous plugin primitives in production.** `eval()`, `exec()`, `compile()`, dynamic `__import__()`, raw `open()` with user-controlled paths, `subprocess` with shell=True — none of these should be reachable from plugin function parameters. Audit your framework's installed plugins and disable or wrap any that expose these primitives.

**Layer 3 — Sandbox the plugin host.** Run plugin execution in an isolated process or container with minimal OS-level privileges. CVE-2026-25592 is a path traversal — it requires a write location that enables further exploitation. If the plugin process can't write to startup directories, cron paths, or SSH authorized_keys, the attacker needs a second vulnerability to convert file write to code execution.

**Layer 4 — Enforce capability-scoped function registration.** Only register the minimum set of functions each agent role needs. Don't give a document-retrieval agent access to `DownloadFileAsync`. Don't give a coding agent access to `subprocess`. Capability scope limits the blast radius of a successful injection.

**Layer 5 — Continuous plugin attack surface monitoring.** Track which plugins are registered in each agent, which parameters they accept, and which primitive operations those parameters reach. Treat the plugin registry as a security-critical configuration. Alert on new plugin registrations or parameter changes.

### The architectural principle

The core insight from both CVEs: **the boundary between model-controlled content and code execution is the new trust perimeter** — and most frameworks were not designed with it as one. The fix is not a version update. It is a shift from "the model is trusted, so model output is trusted" to "model output is untrusted input until it has passed through explicit validation gates."

## Receipt

> Verified 2026-07-26 — CVE-2026-26030 (CVSS 9.9) and CVE-2026-25592 (CVSS 9.8) confirmed via NVD (nist.gov), Microsoft Security Blog (May 7, 2026), and SentinelOne vulnerability database. Semantic Kernel Python SDK patched in v1.39.4; .NET SDK patched in v1.71.0. Exploit chain confirmed: both CVEs require only indirect prompt injection (malicious document/vector store entry) — no direct system access required. The eval() vulnerability in InMemoryVectorStore is a direct code injection path; the path traversal in SessionsPythonPlugin is an arbitrary file write path that can escalate to RCE depending on write destination. The underlying architectural pattern — model output flowing to code execution primitives without validation — affects the entire agent framework ecosystem beyond just Semantic Kernel.

## See also

- [S-1209 · The MCP Security Surface Stack](stacks/s1209-the-mcp-security-surface-stack-when-your-agent-becomes-a-trusted-backend-you-never-hardened.md) — MCP grants agents trusted-backend status; complementary attack surface
- [S-1108 · The Execution Sandbox Stack](stacks/s1108-the-execution-sandbox-stack-when-your-agent-writes-code-and-the-host-trusts-all-of-it.md) — sandbox design for agent-authored code execution
- [S-1000 · Structural Agent Governance Stack](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance layers that persist beyond prompt-level controls
- [S-1691 · The OpenAPI-Bridge Attack Surface](stacks/s1691-the-openapi-bridge-attack-surface-when-your-mcp-server-converts-openapi-specs-into-tool-call-parameters.md) — MCP servers exposing internal API attack surface
