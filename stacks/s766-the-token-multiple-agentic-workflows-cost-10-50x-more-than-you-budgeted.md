# S-766 · The Token Multiple: Why Agentic Workflows Cost 10–50× More Than You Budgeted

When a simple RAG chatbot runs €5/month and its agentic replacement bills €250, something structural changed — not just in model usage, but in the shape of cost itself. Teams that skip cost modeling at design time get a shock at the end of the first month.

## Forces

- Agents iterate — each step is a new LLM call, multiplying the token count by the loop depth
- Multi-agent systems compound: Agent A calls Agent B, which calls a tool, which calls a verifier — each hop is another inference event
- Simple cost estimates only count API fees, ignoring infrastructure, tool integrations, and the maintenance time that grows with complexity
- Teams prototype with single-turn prompts, then are surprised when a 5-step agentic loop costs 50× more at scale
- The "we'll optimize later" approach fails because the cost drivers are architectural, not tunable flags

## The move

Model cost as a first-class architectural concern before choosing your agent design:

- **Count LLM calls per task end-to-end**, not just per turn. A 5-step loop with a critic agent is 7+ calls, not 1
- **Budget token multiples**: one agentic task = 10–50× the tokens of an equivalent single-shot call
- **Route cheap tasks cheap**: classify intent at the gate and route simple requests (lookup, formatting) to smaller/faster models; reserve expensive reasoning for complex decomposition
- **Set per-task token budgets and hard cost caps** — treat token budget like a sprint burndown chart, owned by both PM and SRE
- **Instrument every step**: without per-step cost visibility, you cannot find where 80% of spend is leaking
- **Prefer depth over breadth for multi-agent**: a hierarchy with clear handoff beats a flat swarm for cost predictability

## Evidence

- **Blog post:** A 6-month production study found a capable multi-task agent (research, content, email, scheduling) cost €30–80/month for ~100–200 tasks/day — but teams consistently underestimated because they only counted API fees, not infrastructure (€0–15) and tool integrations (€0–25). Setup took 4–8 hours; ongoing maintenance 1–2 hours/week. — [The Operator Collective](https://theoperatorcollective.org/blog/ai-agent-cost-breakdown), February 2025
- **Technical analysis:** The median agentic workflow costs 10–50× more per task than a well-optimized version. By 2026, AI agent cost has climbed to boardroom-level concern. One analysis found the token multiple between a simple RAG chatbot and a complex agentic system can reach 50–500× at end of month. Cost drivers: LLM inference (input + output tokens per step), tool execution (external API calls per step), memory retrieval (vector DB queries), and orchestration overhead. — [Dr. Vinayaka Jyothi](https://vinayakajyothi.com/blog/2026-05-11-agentic-ai-cost-optimization), May 2026
- **HN discussion:** One developer noted: "If you are not saving your context for decision making and your context window is large, your costs will be enormous." — [Hacker News comment](https://news.ycombinator.com/item?id=47114201), June 2025
- **Production postmortem:** An insurance company's agentic RAG system was retrieving the right documents 90% of the time but producing wrong answers 62% of the time on complex queries — costing ~$4,200/month in API calls for a system that wasn't working. The fix was architectural (multi-hop retrieval), not model-tweaking. — [DEV Community](https://dev.to/jahanzaibai/agentic-rag-the-complete-production-guide-nobody-else-wrote-386o), April 2025

## Gotchas

- **Counting API calls instead of LLM calls**: An agent calling a tool is still an LLM deciding to call it — that reasoning step costs tokens
- **Assuming the model is the cost driver**: For production agents with 10+ steps, infrastructure and tool integrations can exceed the LLM bill
- **Designing first, cost-modeling never**: By the time you see the bill, the architecture is baked in — retrofitting cost controls into a deeply nested agent graph is painful
- **Ignoring the hidden time cost**: Teams budget infrastructure but forget 1–2 hours/week of ongoing maintenance is part of the true cost of ownership
