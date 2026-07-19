# S-1334 · The Minimal Tool Stack — When the Real Design Decision Is What to Withhold

When your agent is failing, the instinct is to give it more tools. More APIs, more access, more capabilities. The failure rate goes up instead of down. The real design decision is not what to give your agent — it is what to withhold, because the gap between a demo agent and a production agent is almost entirely subtractive: fewer, harder-to-misuse tools, not more.

## Forces

- **More tools = more failure surface.** Each tool is a failure point multiplied by the agent's loop count. An agent with 12 tools calling them 15 times has 180 opportunities for tool-chain failure, each of which can corrupt context for the next step.
- **The demo-to-production gap is not about model quality.** Browser agents score 35–60% success in public demos. The same models hit 88–96% in production with proper engineering — entirely on tool design, not capability. (Devsatva, 2026 — https://devsatva.com/blog/ai-browser-agents-computer-use-production-2026)
- **Credential isolation makes sandboxed execution a security boundary, not just a feature.** OpenAI's Agents SDK (April 2026) separates the control harness (where API keys live) from the compute layer (where model-generated code runs) across 8 sandbox providers. This is architecturally the same as running untrusted code in a separate process. (https://byteiota.com/openai-agents-sdk-sandbox-production-code-execution)
- **Tool definition bloat is a context-window crisis.** Anthropic's advanced tool use release (Nov 2025) found that MCP tool definitions with schemas consume 100K+ tokens in large tool libraries. Their Tool Search Tool reduced this by 85% by letting models discover and filter tools dynamically rather than loading all definitions upfront. (https://www.anthropic.com/engineering/advanced-tool-use)

## The Move

The production tool stack is deliberately minimal. Start from zero and add tools only when failure analysis proves a specific gap — not in advance.

**1. Categorize by reversibility.** Give the agent tools in order of how hard it is to undo their effects:
- **Read-only / information tools** (web search, vector DB queries, file read): safe to give broadly, failures are recoverable
- **Side-effect tools** (API writes, database mutations, email send): give only with explicit confirmation loops or human-in-the-loop gates
- **Code execution**: treat as a security boundary — sandbox from credentials, never run agent-generated code in the same process as your API keys

**2. Design each tool for failure.** Every tool gets:
- A clear pass/fail signal the agent can branch on
- No silent failures — tools that return partial data or empty results without error codes are trapdoors
- Bounded output — enforce max tokens or result size so a tool cannot flood the context window

**3. Give the agent a way to verify its own work.** The Anthropic Claude Code best practices call this the single most important design decision: give the agent something that produces a pass/fail signal it can act on. (https://www.anthropic.com/engineering/claude-code-best-practices)
- Without verification: the agent stops when work "looks done" and you become the verification loop
- With verification: test suites, linters, build exit codes, or validation queries let the agent self-correct

**4. Separate credential control from compute execution.** For code execution and browser automation:
- Run agent-generated code in isolated containers (E2B, Modal, Docker, Browserbase, etc.)
- Never pass API keys, secrets, or tokens to the execution environment
- The control plane holds credentials; the compute plane runs untrusted output

**5. Default to web search before browser automation.** Web search is read-only, reversible, and requires no authentication. Browser/computer-use agents are appropriate only when the target system has no API — which is rarer than it appears. The Devsatva case study showed that a browser agent replacing manual data entry paid back in 6.2 weeks, but the team explicitly chose browser over API integration because the legacy portal had no API surface. (https://devsatva.com/blog/ai-browser-agents-computer-use-production-2026)

**6. Constrain the tool set by step budget, not capability.** Anthropic's production guidance: agents should use the simplest solution possible and only increase complexity when required. A 3-tool agent with 8 steps is more reliable than a 12-tool agent with 20 steps, because per-step failure compounds. (https://www.anthropic.com/engineering/building-effective-agents)

## Evidence

- **Engineering blog:** Anthropic's "Building Effective AI Agents" (Dec 2024) studied dozens of production deployments and found the most successful implementations used "simple, composable patterns rather than complex frameworks." The teams that struggled most had over-engineered orchestration with too many tool integrations. — https://www.anthropic.com/engineering/building-effective-agents

- **Consulting case study:** Devsatva documented a browser agent for US insurance claims data entry: 4 FTE × 4 hrs/day reduced to 11-minute autonomous execution at 94% success rate. The production engineering (self-healing selectors, screenshot regression, per-step eval, credential vaulting) was the entire differentiator between demo performance (35–60%) and production performance (88–96%). — https://devsatva.com/blog/ai-browser-agents-computer-use-production-2026

- **SDK release:** OpenAI's Agents SDK (April 2026) shipped sandboxed execution with 8 provider options and explicit credential isolation as the headline feature — explicitly addressing the blocker that prevented autonomous code-execution agents from deploying to production. — https://byteiota.com/openai-agents-sdk-sandbox-production-code-execution

- **Developer forum:** HN discussion "Building Effective AI Agents" (June 2025, 543 points) — top comments emphasized that the "agent" label is often misapplied to systems that would work better as simple workflow chains, and that tool count was a reliable predictor of reliability problems. — https://news.ycombinator.com/item?id=44301809

## Gotchas

- **Giving an agent a tool is not the same as making it usable.** A tool that returns complex JSON or HTML without summarization floods the context window. Tools need output shaping at the interface layer, not just schema definitions.
- **Browser automation is brittle by default.** CSS selectors change on SaaS deploys; XPath is more stable; cached DOM signatures per page state are more robust still. Without self-healing selectors, every third-party UI deploy breaks your agent.
- **The "it works in the demo" trap is structural.** Demos use curated paths through known states. Production agents encounter edge cases, auth token expirations, rate limits, and network failures. Tool design for production means designing for the 20% of states that demos never show.
- **Dynamic tool discovery (MCP Tool Search) changes the calculus.** Anthropic's 85% token reduction from dynamic discovery means you can give agents access to large tool libraries without context bloat — but only if your MCP servers are well-documented and schema-accurate. A tool the agent cannot correctly invoke is worse than no tool at all.
