# S-701 · Agent Cost Model Is Not Chat Cost Model — The Full-Stack Invoice

[Your LLM provider dashboard shows $0.80 in inference spend. Your actual bill is $1.10. The gap isn't a rounding error — it's the hidden cost of the rest of your agent: the tool calls, the external APIs, the retries, the monitoring. And that assumes no loops. When agents loop, the gap isn't $0.30 — it can be $47,000 in eleven days.]

## Forces

- **Agents multiply LLM calls per task.** A single chat turn is one request. A support-ticket agent makes 5 LLM calls (classify → analyze → draft → refine → summarize) plus 3 tool invocations plus 4 external API calls — all for one task. The "cost per conversation" model from chat breaks completely.
- **Non-LLM costs are invisible in provider dashboards.** Tool call fees (MCP servers, REST APIs), vector DB queries, reranker calls, email APIs, and search APIs all add real cost that never appears in your OpenAI or Anthropic bill. Teams discover this when the invoice arrives.
- **Agents introduce failure modes that are exponentially expensive.** Infinite loops, retry storms, and cascade failures don't just produce bad output — they produce massive token volume. A LangChain agent loop cost one team $47,000 in eleven days on a pipeline budgeted under $200/month.
- **Cost-per-task is the right unit, but almost nobody tracks it.** Per-token pricing is visible. Per-task pricing (including all downstream costs) requires instrumentation across every layer. Most teams can't answer "what did this task actually cost us."

## The Move

Track total cost per task, not just LLM spend. Instrument every layer:

- **Decompose per-task cost by layer.** For a support-ticket agent: LLM calls ($0.80 / 73%), tool calls ($0.17 / 15%), external APIs ($0.13 / 12%) = $1.10 per task. The LLM is the headline but not the whole story.
- **Set per-task budget caps, not just monthly caps.** A monthly budget doesn't catch a runaway loop until it's too late. A per-task cap ($5 max/task) combined with a hard kill at N iterations stops runaway costs at the unit level.
- **Count LLM calls per task as a first-class metric.** Track the distribution. A task that consistently uses 5+ LLM calls is a cost amplification risk — every additional call multiplies your exposure to retries, token bloat, and cascading failures.
- **Budget for retries explicitly.** Build in retry budgets (e.g., max 2 retries per tool call) with explicit cost accounting. Without this, a flaky API call can double or triple your tool-layer costs silently.
- **Distinguish tool-call cost from LLM cost in instrumentation.** MCP tool calls, vector DB queries, and external API calls have their own pricing tiers. Tag and track each. In API-heavy workflows, tool costs can equal or exceed LLM costs.

## Evidence

- **Blog post (AgentMeter, 2026):** Support-ticket resolution agent cost breakdown — 5 LLM calls ($0.80), 3 tool calls ($0.17), 4 external APIs ($0.13) = $1.10 total per task. Non-LLM costs = 27% of total. — [https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost](https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost)
- **Blog post (No-Code Finder / cited case, 2025):** A team ran two LangChain agents that entered infinite conversation loop — no human or monitoring system caught it for 11 days. Final inference bill: $47,000 on a pipeline budgeted under $200/month. Root cause: deploying autonomous agents with a cost model built for chat. — [https://www.nocodefinder.com/blog-posts/ai-agent-pricing](https://www.nocodefinder.com/blog-posts/ai-agent-pricing)
- **Article (DevOps Gheware, 2026):** LangGraph vs CrewAI vs AutoGen comparison notes 65% of teams hit a wall within 12 months of production deployment — cost surprises are a significant contributor to rewrites. — [https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Monthly budget caps don't protect against per-task runaway.** By the time a monthly alert fires, the loop has already generated thousands of dollars. Cap at the task level.
- **Retry logic without cost caps amplifies failures.** A 3-retry loop on a $0.05 API call sounds harmless until you have 10,000 tasks and 30,000 retries.
- **External API costs are often in different billing systems.** Your LLM spend is visible. Your Pinecone, Serper, and SendGrid spend are scattered. Aggregate them.
- **Cost-per-task varies wildly by use case.** A simple classification task might be $0.01. A multi-step research agent with web search and document retrieval can easily hit $5-10 per task. Know your distribution.
