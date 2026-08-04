# S-2125 · The Tool Surface Stack — When What You Give Your Agent Determines What It Can Destroy

You deployed an agent with twelve tools. It used eleven of them in the first week — including one you forgot you gave it. The agent deleted a production database, sent 340 unauthorized refunds totaling $1.2M, and did both while following your instructions exactly. The problem was not the agent. The problem was the tool surface: what you exposed, what you failed to scope, and what you assumed the agent would not actually use. Every tool you give an agent is a capability it can invoke autonomously. The stack is how you manage that surface.

## Forces

- **Every tool is a blast radius** — the Kiro incident at Amazon is the canonical case: an agent given write access to a production environment decided "delete and recreate" was the optimal bug fix, causing 13 hours of downtime and triggering a cascade of follow-on incidents (120,000 lost orders, 6.3 million lost orders on a separate outage) weeks later. No prompt injection. No hack. Just a tool the agent was authorized to use.
- **Compound accuracy eats tools alive** — a single agent at 95% per-step accuracy drops to ~60% end-to-end accuracy at step 10. Add one more tool and the agent has one more decision to make per step. Each tool call is a potential failure point, and the failure modes are not evenly distributed.
- **89% have observability, 11% are in production** — LangChain's State of Agent Engineering survey (n=1,340) found 89% of teams have agent observability but only 11% have agents in production. The gap is not monitoring. It is tool surface management.
- **MCP solved the integration problem and amplified the exposure problem** — MCP (Model Context Protocol) went from ~100K monthly SDK downloads in November 2024 to 97M+ by December 2025, with 10,000+ published servers. It standardized how agents connect to tools. Standardization at that scale means every misconfigured MCP server is a production incident waiting to happen.

## The Move

**Design your tool surface like a product, not a feature list.** The core insight from practitioners who have shipped agents to production: every tool an agent can call should be treated like a shipped API product — with contracts, limits, error handling, and blast radius containment.

### Minimum Viable Tool Surface

- **Start with three tools maximum.** Context7 (fetching current library documentation to prevent hallucinations), Sequential Thinking (enforcing step-by-step reasoning), and one domain tool. Add more only when you have a specific, verified failure that more tools fix.
- **Scope each tool to its minimum necessary permission.** Not "filesystem read/write" — "read only files in /tmp/agent-workdir." Not "send emails" — "send confirmation emails only, with template locked to pre-approved copy."
- **Treat tool responses like API contracts.** MCP tools expose structured schemas. Every tool response should be parseable, typed, and idempotent where possible. If the agent calls a tool and gets a partial response, the orchestrator needs to know — not the agent guessing.
- **Instrument every tool invocation.** You cannot manage what you cannot see. Log tool name, arguments, response status, latency, and whether the agent used the result. The 89% who have observability still cannot answer "which tool caused the failure" in a 12-step chain.
- **Design for graceful degradation, not fallback.** If a tool fails (3–15% of the time for external APIs), the agent should not retry indefinitely or hallucinate a response. Build a deterministic fallback that records the failure, captures state, and escalates.

### Browser Automation: The Special Case

Browser automation is the most common first tool teams expose to agents. Three approaches exist, each with different risk profiles:

1. **DIY Playwright/Puppeteer** — full control, maximum maintenance burden. Selectors break weekly, anti-bot walls escalate, session management with 2FA is not in the box.
2. **Wrappers (browser-use, AgentQL)** — higher abstraction, easier to get started. browser-use has 107K+ GitHub stars and is the dominant pattern for this approach. Risk: the wrapper hides the underlying fragility until production.
3. **Browser MCP server (Playwright MCP, RoverMCP)** — the agent calls browser operations as structured tools via Model Context Protocol. Playwright MCP provides structured accessibility snapshots so no vision model is required. RoverMCP exposes 46 tools covering stealth, sessions, and fallbacks.

**Recommendation:** Use a browser MCP server. The protocol gives you auditability and structured responses. The wrapper gives you convenience that masks failure modes until they hit production.

### The Tool Audit Loop

Before every deployment: enumerate every tool, every permission, every system the tool can touch. Ask: "If the agent calls this tool in the worst way, what is the maximum blast radius?" If that radius is unacceptable, you have the wrong tool surface — not the wrong agent.

## Evidence

- **Company engineering post (Atypical Tech):** Amazon Kiro agent mandated at 80% weekly usage across Stores division via internal SVP memo (Nov 24, 2025). Three weeks later, Kiro autonomously decided to "delete and recreate" a production Cost Explorer environment — authorized by its tool access, suboptimal by any engineering standard. 13-hour outage. Follow-on incidents in March 2026: 120,000 lost orders, 6.3 million lost orders, 6 hours of amazon.com downtime. — [URL](https://atypicaltech.dev/blog/amazon-kiro-when-your-ai-deletes-production/)
- **GitHub repo / engineering analysis (Paddo.dev):** Financial Times-sourced reconstruction of the Kiro incident timeline. Root cause framing: "Amazon says it was human error. That framing is the problem." The agent had the tools. The authorization was correct. The decision was catastrophically wrong. — [URL](https://paddo.dev/blog/kiro-delete-and-recreate/)
- **Practitioner field report (Agentbrisk):** E-commerce refund agent in Q3 2025: authorized to issue refunds up to $500 without human review. Users discovered that rephrasing requests to match the agent's training distribution yielded refunds on non-qualifying orders. Total exposure: ~$1.2M across 340 transactions before detection. Root cause: refund eligibility logic reposed in natural-language inference rather than structured policy enforcement. — [URL](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents/)
- **Survey data (LangChain / Kore.ai 2026):** 71% of organizations use AI agents; only 11% have agents in production. 89% have agent observability; only 52% run outcome evaluations. The monitoring gap exists because the tool surface is unmanageable, not because teams are not watching. — [URL](https://www.paperclipped.de/en/blog/ai-agent-production-issues)
- **GitHub repo (browser-use):** 107,832 stars, 11,847 forks, MIT license. Enables AI agents to control web browsers via natural language instructions. Core capabilities: form filling, data extraction, QA automation. Most-starred browser automation tool for AI agents. — [URL](https://github.com/browser-use/browser-use)
- **GitHub repo (modelcontextprotocol/servers):** 89,161 stars. MCP steering group reference implementations. SDKs in 10 languages. Demonstrates MCP's role as the tool integration standard: structured tool schemas, typed responses, audit-friendly invocation logs. — [URL](https://github.com/modelcontextprotocol/servers)
- **Engineering blog (Tian Pan / tianpan.co):** The compound accuracy math: 0.95^10 = 59.9% end-to-end success. Historical parallel to Lusser's Law in aerospace: each subsystem at 99% accuracy yields 90.4% at 10 subsystems — a known engineering problem that agent teams are rediscovering. — [URL](https://tianpan.co/blog/2026-04-20-compound-accuracy-multi-step-agent-pipelines)
- **Engineering blog (Raviole Labs):** Honest comparison of browser automation approaches for AI agents. DIY Playwright breaks on selector rot, anti-bot escalation, and session management. Wrappers mask fragility. Browser MCP servers (RoverMCP as example) expose structured tools the agent calls like any other tool — auditable, typed, with session and stealth management. — [URL](https://raviolelabs.com/blog/browser-mcp-vs-playwright-puppeteer)
- **Company engineering post (Dynatrace Perform 2026):** Dynatrace CTO Bernd Greifeneder demonstrated the compound failure math live: 95% per-step accuracy collapses to ~60% by step 10. Agentic AI monitoring market: $550M (2025) to projected $2.05B (2030). Observability is becoming the control plane — the layer that grounds agent decisions in deterministic data and enforces governance boundaries. — [URL](https://www.paperclipped.de/en/blog/agentic-ai-observability-control-plane)

## Gotchas

- **Adding a tool to fix a failure adds two new failure modes** — each new tool is a new decision the agent makes, a new error path, and a new blast radius. The reflex to add tools is the reflex that created the Kiro incident.
- **Observability without outcome evaluation is theater** — 89% of teams have observability, but only 52% evaluate outcomes. You can watch your agent fail in real time and still not know if it was right. Instrument tool invocations AND define what "success" means at the task level.
- **The tool schema is not the tool** — defining `send_email(to, body)` with a structured MCP schema does not mean the agent cannot call it 10,000 times in a loop, send emails to the wrong recipients by misreading context, or hallucinate a body that bypasses your template. The contract constrains the format, not the logic.
- **MCP's convenience is its danger** — MCP made it trivially easy to expose 50+ tools to an agent. The "essential trinity" of Context7, Sequential Thinking, and one domain tool covers 95% of use cases. The remaining 47 tools are where blast radius lives.
- **Sandboxing is not scope limiting** — putting an agent in a Docker container does not limit its tool surface. It limits what it can do to the host. If the container has network access, the agent can still call external APIs, send emails, or exfiltrate data. The permission boundary is the tool, not the environment.
