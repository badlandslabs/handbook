# S-1419 · The Agent Tool Interface Stack: When Your Agent Calls the Right Tool and Gets the Wrong Answer

Your agent has the right tool for the job. It calls it. The tool works perfectly. The agent confidently acts on bad data anyway — a buried error code, a raw nested JSON blob, a field renamed between API versions. The tool worked. The interface failed. Most agent bugs don't live in the reasoning loop — they live at the tool boundary.

## Forces

- **The tool surface is where LLMs are most fragile.** A model can reason perfectly and still make bad decisions because the tool's output format was ambiguous, the schema was loose, or the error response looked like valid data.
- **MCP has won the protocol layer, but the server ecosystem is chaotic.** 500+ MCP servers exist, but quality is wildly inconsistent. Stars ≠ maintenance. A server with 10k stars and no commits in 8 months is worse than a boring one that gets weekly updates.
- **Security exposure scales with tool access.** Every tool you give an agent — file system, code execution, database write — is a blast radius. Prompt injection in a chatbot makes a bad sentence. Prompt injection in an agent with tool access can exfiltrate data or trigger payments.
- **Sandboxing code execution is non-negotiable in production.** Unprotected code execution (even at user-level permissions) enabled 30+ RCE vulnerabilities across Cursor, Windsurf, Copilot, and Cline in a single 2025 disclosure nicknamed "IDEsaster."

## The Move

### 1. Design tool interfaces schema-first, not API-first

The `input_schema` and tool `description` are the only thing the model uses to decide *what* to call and *what* to pass. Loose schemas produce wrong calls; generic descriptions produce wrong tool selection.

```
# Bad: vague description, unconstrained schema
{"name": "search", "description": "search the web", "input_schema": {"type": "object"}}

# Good: semantic description, constrained schema
{
  "name": "search_web",
  "description": "Use for factual queries about current events, prices, weather, or anything requiring live web data. NOT for code questions or opinion. Returns top 5 snippets.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Specific factual question, ≤150 chars. Ambiguous queries get zero results."},
      "recency_days": {"type": "integer", "default": 30, "description": "Max age of results. Set 365+ for historical facts."}
    },
    "required": ["query"]
  }
}
```

Normalize all tool outputs to a consistent format: `{success: bool, data: ..., error: string, metadata: {took_ms: number}}`. Never return raw API responses. Never let an error look like valid data.

### 2. Default to MCP for tool connectivity

Model Context Protocol (MCP) has become the dominant standard for connecting agents to tools. Use it over custom tool wrappers.

Prioritize official Anthropic servers for production:

| Server | Use when | Key tools |
|--------|----------|-----------|
| **Filesystem** | Agent needs to read/write project files | read_file, write_file, list_directory |
| **GitHub** | Code review, PR triage, issue management | create_issue, review_pr, list_commits |
| **Brave Search** | Live web queries, fact-checking | search_web, fetch_url |
| **PostgreSQL** | Read-only data queries, schema introspection | execute_query, run_sql |
| **Puppeteer** | Browser automation, screenshot capture | take_screenshot, click_element, fill_form |

For community servers: check commit recency, open-issue ratio, and whether a read-only mode exists. The MCP-Finder 2026 ranking scores on maintenance (days since commit, issue ratio), tool surface coverage, documentation quality, stability, and safety. Stars are irrelevant.

### 3. Use Playwright over Puppeteer for browser automation

For agents that need to interact with web UIs (scraping, form submission, screenshot capture), Playwright is the standard choice in production. Puppeteer is 15–20% faster on raw speed benchmarks, but agents aren't benchmark runners — they need reliability and comprehension.

Playwright advantages for agents:
- **Multi-browser by default** (Chromium, Firefox, WebKit) — agents encounter site-specific rendering issues
- **Better auto-waiting** — reduces flaky "element not found" failures from timing
- **Structured selectors** (role, label, text) — models can generate more reliable locators than XPath strings
- **Trace viewer** — critical for debugging what the agent's browser actually saw

### 4. Sandbox all code execution with isolation layers

If your agent can write and run code (Python, Node, bash), you **must** isolate execution. Options by isolation strength:

| Technology | Latency | Isolation | Use case |
|-----------|---------|-----------|----------|
| Docker | Medium | Process + filesystem | General-purpose, easy setup |
| gVisor | Low | Syscall filtering | Production, GCP workloads |
| Firecracker (E2B, Northflank) | Fast | MicroVM per sandbox | Multi-tenant, enterprise |
| Modal | Very fast | Container + network policy | Serverless-style execution |
| Kata Containers | Slowest | Hardware VM | Highest-security untrusted code |

Key constraints to apply regardless of technology:
- **Network egress allowlist** — block outbound connections except to intended services
- **CPU/memory limits** — prevent resource exhaustion
- **Execution timeouts** — hard cap (30–60s), not graceful degradation
- **Filesystem scope** — restrict read/write to a working directory, never `/` or `$HOME`
- **Secrets never reach the sandbox** — pass credentials via environment variables scoped per-session, revoke after

E2B reports 7M+ monthly sandbox starts and 1B+ total started sandboxes as of 2026, with 94% of Fortune 100 companies as customers. Modal and Northflank are common alternatives.

### 5. Treat tool errors as first-class citizens

Implement retry with exponential backoff at the tool call layer — not in the agent's reasoning loop:

```python
last_error = None
for attempt in range(max_retries):
    delay_ms = min(1000 * (2 ** attempt), 10_000)
    await sleep(delay_ms)
    try:
        result = await Promise.race([
            tool.execute(input),
            sleep(tool.timeout or 30_000).then(() => { throw new TimeoutError() })
        ])
        return { success: true, output: result }
    except ValidationError, NonRetryableError:
        break  # Don't retry schema errors
    except error:
        last_error = error
# After exhausting retries: return structured failure
return { success: false, error: last_error.message, exhaustedRetries: true }
```

Map error codes to semantic messages. A `500` from an API is not the same as a `429` (rate limit — retry after backoff) or a `401` (credentials — don't retry). The agent needs to know which to retry vs. escalate.

### 6. Scope tools to least-privilege

Give agents the minimum toolset for their task. Read-only database tool by default; write access only when the task explicitly requires mutation. Separate "investigate" tools (read-only: search, query, fetch) from "act" tools (write, delete, send, deploy) and require explicit opt-in for the latter.

## Evidence

- **HN discussion (Ask HN, 2024):** "What AI Agents are in production?" — practitioners reported browser automation (Intuned, YC S22), database query agents, code review bots, and customer support agents as top production use cases. Key theme: production agents are narrower than demos, not broader. — [https://news.ycombinator.com/item?id=42485738](https://news.ycombinator.com/item?id=42485738)
- **AI Agents Blog (March 2026):** "Tool Use Patterns: Building Reliable Agent-Tool Interfaces" — documents that most agent failures originate at tool boundaries (ambiguous schema → wrong tool selection, loose input schema → malformed arguments, unstructured output → model guessing). Core pattern: schema-first design and normalized output wrapping. — [https://aiagentsblog.com/blog/agent-tool-use-patterns/](https://aiagentsblog.com/blog/agent-tool-use-patterns/)
- **Anthropic Engineering (June 2025):** "Building Effective AI Agents" — defines augmented LLMs as "LLM + tools + memory + data" and recommends starting with direct API calls over frameworks. Notes that tools should be self-describing (name, description, input_schema) and that agents benefit from having the right tool at the right time, not from tool quantity. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **MCP-Finder Best MCP Servers 2026 (May 2026):** Ranks 500+ MCP servers on maintenance, tool surface, documentation, stability, and safety. Key finding: official Anthropic servers (PostgreSQL, Filesystem, GitHub, Brave Search, Puppeteer) score highest on reliability; community servers frequently lack active maintenance. Stars ≠ quality. — [https://github.com/mcp-finder/best-mcp-servers-2026](https://github.com/mcp-finder/best-mcp-servers-2026)
- **DEV Community / Steven Gonsalvez (2025):** "Browser Tools for AI Agents: Playwright vs Puppeteer" — Playwright wins for agents on reliability and auto-waiting, not raw speed. Agents playing a "reliability and comprehension game," not a benchmark game. — [https://dev.to/stevengonsalvez/browser-tools-for-ai-agents-part-1-playwright-puppeteer-and-why-your-agent-picked-playwright-k71](https://dev.to/stevengonsalvez/browser-tools-for-ai-agents-part-1-playwright-puppeteer-and-why-your-agent-picked-playwright-k71)
- **Amux AI Agent Sandboxing Guide (2026):** Documents CVE-2026-25592 & CVE-2026-26030 — Microsoft disclosed RCE vulnerabilities in Semantic Kernel and popular AI-powered IDEs (Cursor, Windsurf, Copilot, Cline) due to unprotected code execution. "IDEsaster" disclosure found 30+ vulnerabilities from agents executing at user-level permissions. — [https://amux.io/guides/ai-agent-sandboxing/](https://amux.io/guides/ai-agent-sandboxing/)
- **Zylos Research (Jan 2026):** "AI Agent Code Execution and Sandboxing" — OWASP Top 10 for LLM Applications identifies prompt injection in 73%+ of production AI deployments. Sandbox technologies (Firecracker, gVisor, Kata Containers) each offer different isolation/latency tradeoffs. — [https://zylos.ai/en/research/2026-01-24-ai-agent-code-execution-sandboxing/](https://zylos.ai/en/research/2026-01-24-ai-agent-code-execution-sandboxing/)
- **Akto Security (July 2026):** "Prompt Injection Defense for AI Agents & MCP Tools" — contrast between chatbot and agent attack surface: prompt injection in a chatbot produces text; in an agent with tools it can trigger payments, send emails, or exfiltrate data. Defense strategies include input validation, output filtering, least-privilege tool scoping, and anomaly detection. — [https://www.akto.io/blog/prompt-injection-defense-ai-agents-mcp-tools](https://www.akto.io/blog/prompt-injection-defense-ai-agents-mcp-tools)
- **E2B / Microsoft AI Agent Runbooks:** E2B reports 7M+ monthly sandbox downloads, 1B+ total sandboxes started, 94% Fortune 100 usage. Microsoft AI Agent Runbooks (March 2026) provides structured runbooks for production agent deployment on Azure, including tool security patterns. — [https://e2b.dev/](https://e2b.dev/) | [https://github.com/microsoft/ai-agent-runbooks](https://github.com/microsoft/ai-agent-runbooks)

## Gotchas

- **Raw API responses are never tool outputs.** Every tool should wrap its response in a normalized envelope (`{success, data, error, metadata}`). Unstructured responses let the model pick plausible-looking values from nested JSON.
- **Tool descriptions compete with each other.** If two tools have overlapping descriptions, the model will pick the wrong one. Keep descriptions mutually exclusive in capability.
- **Community MCP servers go stale fast.** A server that was actively maintained 3 months ago may have breaking API changes in its dependency. Pin versions and re-validate after dependency updates.
- **Sandbox egress is the data exfiltration vector.** An agent with code execution AND network access can send your codebase, secrets, or customer data anywhere. Egress allowlisting is not optional.
- **Timeouts must be explicit and enforced.** LLMs don't naturally reason about time. Set hard timeouts on every tool call and treat a timeout as a failure to be retried or escalated, not as "still working."
- **Read vs. write tools need separate privilege levels.** Giving an agent a read tool that happens to also support writes (or vice versa) is a privilege escalation waiting for a prompt injection.
