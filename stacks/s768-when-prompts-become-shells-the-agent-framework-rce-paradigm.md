# S-768 · When Prompts Become Shells: The Agent Framework RCE Paradigm

Prompt injection was a content problem. A malicious email could make your agent say something embarrassing. A poisoned document could override your agent's instructions. Harmful, embarrassing — but bounded. The worst case was a bad output. That model broke on May 7, 2026, when Microsoft's Defender Security Research Team disclosed two critical vulnerabilities in Semantic Kernel — CVE-2026-25592 (CVSS 10.0) and CVE-2026-26030 — demonstrating that a single crafted prompt is sufficient to achieve host-level remote code execution on any machine running a vulnerable Semantic Kernel agent. No browser exploit. No memory corruption. No zero-day. The LLM behaved exactly as designed; the vulnerability was in how the framework interpreted the output.

This is not an evolution of prompt injection. It is a new threat category: **prompt-as-attack-surface, framework-as-attack-vector, tool-output-as-code-execution-trigger**. The defenses practitioners built for content-level prompt injection — input classifiers, output filters, instruction separation — do not stop this class of attack. The agents you deployed in Q1 2026 using Semantic Kernel are now the entry point.

## Forces

- **The AI attack surface is now the host attack surface.** Once an LLM is connected to tools, every token in context becomes a potential command. When framework internals are exposed as callable functions, a prompt that manipulates those internals achieves execution on the host — not inside the sandbox.
- **Framework popularity amplifies single vulnerabilities.** Semantic Kernel has 27,000+ GitHub stars and powers agents across Microsoft's own tooling, Azure AI services, and enterprise deployments. A CVSS 10.0 in a popular framework is not a niche risk — it is an endemic one. Any unpatched instance is exploitable by any input the agent processes.
- **Existing prompt injection defenses target content, not execution.** Instruction-following classifiers, output classifiers, and input sanitization all operate at the text layer. They cannot distinguish between a maliciously crafted instruction that a model processes correctly and a framework exploit that triggers after the model generates its output.
- **"The model behaved correctly" is not a safety guarantee.** The Microsoft disclosure's core insight: the vulnerability is not in the AI. The LLM generates text that a developer would never write — but the model is behaving as designed, following its instructions. The framework misinterprets that output and calls unsafe functions.
- **Patch velocity matters more than model safety.** The patched versions (semantic-kernel Python 1.39.4, .NET 1.71.0) close the specific exploits. But the architectural pattern — exposing framework internals as callable kernel functions — remains common across frameworks. New attack surfaces will emerge as the ecosystem matures.
- **AI agent frameworks now ship CVSS 10.0 CVEs.** The security community's prior mental model — that AI vulnerabilities are CVSS 4–6 content issues — was broken by this disclosure. Frameworks are software. Software has vulnerabilities. Agentic AI has made those vulnerabilities directly reachable from any input.

## The Vulnerabilities

### CVE-2026-25592 — .NET Sandbox Escape (CVSS 10.0)

The Semantic Kernel .NET SDK exposed a host-side file download method (`UrlToContentPlugin`) as a callable kernel function. An attacker who could inject text into the agent's context — via email, document, retrieved webpage, or database field — could craft a prompt instructing the agent to invoke this function with an attacker-controlled URL. The framework executed the download on the host. In Microsoft's demonstration, a single prompt launched `calc.exe` on the target machine.

The attack chain: **indirect prompt injection** (attacker controls a document the agent retrieves) → **model generates instruction** ("call UrlToContent with URL X") → **framework interprets output and calls the native function** → **host compromise**.

The root cause is architectural, not accidental: Semantic Kernel's design exposed framework-level I/O operations as natural-language-callable functions without sandboxing the parameter surface.

### CVE-2026-26030 — InMemoryVectorStore Filter Injection (CVSS unconfirmed)

The Semantic Kernel Python SDK's `InMemoryVectorStore` component accepted filter expressions that were evaluated via Python's `eval()` — a code evaluation vulnerability. An attacker who could set filter values (via any of the standard injection vectors) could execute arbitrary Python on the host. The attack surface here is specifically retrieval-augmented agents that use Semantic Kernel's built-in vector store with user-controlled filter inputs.

## Why Existing Security Entries Don't Cover This

[S-763 MCP Tool Description Poisoning](../stacks/s763-mcp-tool-description-poisoning-the-attack-your-trusted-tools-deliver.md) covers supply-chain poisoning of tool descriptions — a build-time and dependency-time attack. [F-194 AgentJacking](../forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) covers indirect prompt injection via MCP server responses exploiting implicit trust. [F-04 Guardrails](../forward-deployed/f04-guardrails.md) covers the content-layer defense stack — input classifiers, output filters, and execution controls.

None of these cover the paradigm shift this disclosure represents: **prompt injection that triggers a framework-level RCE via legitimate API misuse**. The distinction matters:

| Attack Class | Target | Existing Coverage |
|---|---|---|
| Prompt injection (content) | Model output / instructions | F-04, F-194 |
| Tool description poisoning | Build-time / tool metadata | S-763 |
| Indirect injection via MCP response | Tool response trust assumption | F-194 |
| **Framework RCE via function exposure** | **Host execution via framework API** | **None** |

The first three are content security problems. This one is a host security problem. Content defenses cannot block it.

## Pattern: Framework RCE Surface Reduction

The architectural response has three layers — and they must all be present. Missing any one creates a residual attack surface.

### Layer 1 — Capability Audit and Minimization

Before deploying any agent framework, map every function exposed to the LLM's action surface. The attacker's goal in CVE-2026-25592 was a legitimate-sounding framework function — `UrlToContent` — that happened to perform host I/O. If that function was never exposed to the agent's tool registry, the attack chain breaks.

Audit checklist:
- List every kernel plugin, function, or tool registered with the agent
- Classify each by privilege level: read-only, read-write local, read-write network, read-write filesystem, code execution
- Apply least privilege: if a function is not required for the agent's task, remove it
- Pay specific attention to: file I/O, HTTP download/upload, process execution, database write, email send, shell commands

This is not a one-time review. Framework updates can introduce new callable functions. Pin framework versions and audit the delta on every update.

### Layer 2 — Output Interpretation Boundaries

The Microsoft disclosure's root insight is that Semantic Kernel interpreted the LLM's output as a directive to call native functions — with no validation that the generated instruction was intentional. The model said something; the framework acted on it.

Establish an explicit human-in-the-loop boundary for high-stakes operations:

- Any tool call that performs network I/O (HTTP requests, downloads, email send) requires a confirmation step
- Any tool call that writes to the filesystem requires a review or a write-policy
- Any tool call that executes code requires explicit user approval and a sandbox boundary

This is not about distrusting the model — it is about making the framework trustworthy by design. A framework that interprets every LLM output as a function call with no boundary is architecturally unsafe regardless of model quality.

### Layer 3 — Patch Management and Dependency Monitoring

Both CVEs were patched. The actionable risk is unpatched deployments. Agent framework dependencies need the same patch urgency as operating system packages:

- Subscribe to security advisories for every framework in the agent stack: Semantic Kernel, LangChain, LangGraph, CrewAI, AutoGen, Microsoft Copilot SDK, OpenAI SDK
- Treat framework CVEs as equivalent to OS CVEs in severity tiers
- Automate dependency scanning (Dependabot, Snyk, Grype) against the agent runtime's `requirements.txt` / `package.json` / `.csproj`
- Patch within SLA: CVSS 9+ should patch within 72 hours; CVSS 10.0 should patch within 24 hours

### Layer 4 — Retrieval Input Sanitization (for VectorStore-class attacks)

For agents that use Semantic Kernel's InMemoryVectorStore or equivalent with user-controlled filter inputs: validate and sanitize all filter values before they reach the evaluation layer. Do not pass user strings to `eval()` or equivalent. Use parameterized queries, allowlists, or input validation schemas that reject any value containing Python expressions.

## Detection

Standard RCE indicators apply, but with AI-agent context:

- Agent process making outbound connections to unexpected IPs (post-exploitation C2)
- Agent process writing files outside its designated working directory
- Agent process executing subprocesses it did not previously execute
- Unusual function calls in the agent trace — particularly I/O functions triggered by retrieved content
- Semantic Kernel logs showing function invocations with parameters derived from document retrieval (a red flag for the CVE-2026-25592 chain)

Monitor agent traces for the pattern: `retrieve(doc) → generate() → call(UrlToContent | InMemoryVectorStore | exec | shell)` within the same or adjacent turns. A retrieval followed by a tool call with parameters derived from that retrieval is the signature of the attack chain.

## When to Use This Pattern

- You deploy any agent framework in production with network or filesystem access
- Your agent retrieves content from third-party sources (web search, document stores, email)
- Your agent processes user-submitted content that reaches the context window
- You have not audited the callable function surface of your agent framework
- You are running Semantic Kernel versions below 1.39.4 (Python) or 1.71.0 (.NET)

## When Not to Use This Pattern

- Your agent is sandboxed with no filesystem, network, or process access, and cannot be granted any by future configuration changes
- Your agent processes no external content and cannot be extended to do so
- You have already completed a full capability audit, patched all frameworks, and implemented output interpretation boundaries

## Receipt from Reality

- **Microsoft Security Blog** (May 7, 2026): Original disclosure, proof-of-concept demonstrating `calc.exe` launch via single prompt against vulnerable Semantic Kernel .NET SDK. CVE-2026-25592, CVSS 10.0; CVE-2026-26030, InMemoryVectorStore `eval()` injection in Python SDK.
- **BreakMyAgent** (May 14, 2026): Technical walkthrough of both CVEs with affected version ranges and patch status.
- **Red Hat CVE Database** (CVE-2026-26030): Confirms CWE-94 (code injection) classification and workaround guidance.
- **AI Magicx** (April 2026, pre-disclosure): Documented the 340% year-over-year surge in prompt injection attacks as the forcing function — the threat was escalating before the RCE paradigm arrived.

## See Also

- [S-763 · MCP Tool Description Poisoning](../stacks/s763-mcp-tool-description-poisoning-the-attack-your-trusted-tools-deliver.md) — supply-chain attack surface in the MCP ecosystem
- [F-194 · AgentJacking & MCP Tool-Response Poisoning](../forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) — indirect prompt injection via MCP server responses
- [F-04 · Guardrails](../forward-deployed/f04-guardrails.md) — content-layer defense stack
- [F-06 · Agent Sandboxing](../forward-deployed/f06-agent-sandboxing.md) — process and network isolation for agent execution
- [S-201 · MCP Server Security Hardening](../stacks/s201-mcp-server-security-hardening.md) — server-side hardening for the MCP ecosystem
