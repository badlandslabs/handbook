# S-1353 · The Tool Granularity Stack

When you reach for this: Your agent has 40 tools but keeps failing in ways that are hard to reproduce. The logs say it ran the right tool — but the result was wrong, missing, or the agent claimed it worked when it didn't.

## Forces

- **More tools ≠ more capability** — each new tool is another failure point. A 10-step workflow with tools at 95% accuracy per step lands at ~60% end-to-end success. Adding tools compounds the chain.
- **Tool description quality dominates tool count** — agents decide whether and how to use a tool almost entirely from its description. A vague description causes misuse more often than having no tool at all.
- **Action hallucination is invisible without output validation** — the agent says it called the right API. It didn't. There's no error, just wrong data downstream.
- **Security and capability are in tension** — giving an agent filesystem access, code execution, or API credentials unlocks real workflows but also unlocks catastrophic failure modes that unit tests won't catch.
- **Fleet operations dominate production tool usage** — in real production deployments, the majority of MCP tool calls are mundane infrastructure commands: list instances, check health, query a database. Teams over-index on "impressive" tools and under-index on the 5-8 boring ones that cover 80% of real usage.

## The move

**Shrink the tool surface. Validate every output. Sandbox everything that can harm.**

### Surface reduction

- Start with 5-7 tools maximum. If you can't fit the description of what a tool does and when to reach for it into two sentences, split the tool or cut it.
- Group related capabilities into a single tool rather than exposing sub-actions separately. A `search_github()` that returns filtered results beats `list_repos()`, `get_repo()`, `list_issues()`, `get_issue()` as four separate calls.
- Audit tools quarterly. Remove or combine the ones that are never called or whose call volume is noise.

### Description-first design

- Write tool descriptions as decision criteria: "Use this when the user wants to know X or do Y" — not just "Gets data from database."
- Include the shape of the output. The agent needs to know what it gets back to use the result.
- Flag edge cases in the description: "Returns empty list if no results — never returns null."

### Output validation as a first-class concern

- Every tool call returns a result. That result must be validated against a schema before the agent acts on it.
- The agent's self-report of tool execution ("I called the API successfully") is not evidence. The returned data is evidence.
- Implement result diffing for tools that modify state: confirm the pre-state, post-state, and that the delta matches the intent.

### Security layering for dangerous tools

- **Code execution**: Mandatory sandboxing via gVisor, Firecracker microVMs, or WASM. Never run agent-generated code on the host. Enforce syscall allowlists, memory caps, and network policy.
- **API integrations**: Scope credentials to the minimum required scope. Never give an agent a "god-mode" API key.
- **File operations**: Restrict to a designated workspace directory. Deny access to credential paths, home directories, system files.
- **Browser automation**: Prefer DOM-text-based interaction over screenshot-and-click. Text-based is faster, more deterministic, and easier to validate.
- **Human-in-the-loop gates**: Pause before destructive operations (sends email, deletes records, approves purchases). Configure thresholds. Log the pause and the human's response.

### Tool taxonomy for production agents

The tools that actually ship in production cluster around a small set of categories:

| Category | What it does | Risk level |
|---|---|---|
| Web search / fetch | Retrieve current information | Low |
| Browser automation | Interact with web UI | Medium |
| File operations | Read/write within workspace | Medium |
| Code execution | Run generated code in sandbox | High |
| API integrations | Call external services (GitHub, Slack, CRM) | High (credential risk) |
| Database queries | Read/write structured data | High (data risk) |
| Infrastructure commands | Cloud fleet management | Critical |

## Evidence

- **MCP ecosystem analysis (OpenClaw, 2026):** Over 13,230 public MCP servers exist, covering developer tools, databases, CRMs, communication platforms, and cloud infrastructure. Fleet management commands (list instances, check health) account for the majority of MCP tool calls in production — not exotic integrations. The protocol hit 97M+ monthly SDK downloads in under a year of launch, with support from Anthropic, OpenAI, Google, and Microsoft. — [OpenClaw MCP Guide](https://openclaw.direct/mcp-guide/model-context-protocol-examples)

- **Browser workflow agents (Ghostd Show HN, 2025):** A production agent that executes full workflows in a real browser using text-described steps rather than screenshot-based click coordinates. Demo workflow: scan email inbox → open job listings → extract details → build Google Sheet. The creator notes: "Once you're taking screenshots, guessing what to click, moving the mouse, and repeating, it gets slow and brittle fast." Text-based browser control was faster and more reliable in production. — [Show HN: AI agent that runs real browser workflows](https://news.ycombinator.com/item?id=47322046)

- **Sandboxed code execution analysis (Chaitanya Prabuddha, 2026):** "Running AI-generated code without appropriate controls is not a prototype shortcut. It is an active security incident waiting to happen." Direct attacks via code generation include: filesystem access (`rm -rf /`), process spawning (install cron jobs), network exfiltration. Production-grade execution requires gVisor or equivalent with syscall allowlists, resource caps, and explicit network policy. — [Sandboxed Code Execution for AI Agents](https://www.chaitanyaprabuddha.com/blog/sandboxed-code-execution-ai-agents)

## Gotchas

- **The agent's confidence about a tool call is not correlated with correctness.** An agent at 95% accuracy will confidently hallucinate tool outputs. Build validation, not trust.
- **Sandboxing adds latency and complexity.** gVisor adds userspace-kernel overhead for syscall-heavy workloads. Policy enforcement requires more infra than a simple local runner. Budget for this — it's not optional, but it has real cost.
- **Adding a tool adds two failure modes: calling it when you shouldn't, and using the result incorrectly.** Every new tool is a new branch in your failure tree. Measure whether the tool's value exceeds its operational cost.
- **The description field is the most important field on a tool definition.** If the model can't decide when to call it from the description alone, the tool will be misused or ignored. Write it like a function signature with judgment.
