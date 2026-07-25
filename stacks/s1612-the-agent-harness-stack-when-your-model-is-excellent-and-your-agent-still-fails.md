# S-1612 · The Agent Harness Stack — When Your Model Is Excellent and Your Agent Still Fails

You upgraded to the best model. The prompt is perfect. The eval score is 94%. Production traffic starts and the agent produces garbage 18% of the time — burning tokens, returning corrupted data, and silently looping on failed tool calls until someone checks the logs. The model is not the problem. The infrastructure around it is. This is the stack for building the layer that wraps the model: the harness that turns a capable agent into a reliable system.

## Forces

- **The model is the smallest source of failure.** Prompt refinement has diminishing returns past ~85-90% task completion. Getting from 90% to 97% requires engineering the harness, not tuning the system prompt.
- **Tool call failures are silent by default.** When an external API times out or returns a 500, Python exceptions get caught and empty results get returned. The agent interprets empty as "no results found" and continues on corrupted state. This accounts for 15-20% of production failure rates that look like model quality issues.
- **Context drift compounds exponentially.** At 85% per-step accuracy, a 10-step agent completes successfully only 20% of the time (0.85^10 ≈ 0.20). Most enterprise failures trace to data quality and context management, not architectural defects.
- **The framework is not the harness.** LangChain, LangGraph, CrewAI, and AutoGen define how agents think and call tools. They do not define what "done" means, how costs are tracked, how errors propagate, or what policies govern retry behavior. These are the harness decisions.
- **Most prototypes never reach production.** Only 5% of AI prototypes ship. Enterprise environments collapse agents against corporate networks, data quality issues, and operational volatility that staging never simulates.

## The Move

The harness sits between the agent's reasoning engine and the real world. It handles five jobs that the model never learns to do:

**1. Instrument every tool call with result validation.**
Wrap every tool invocation with schema validation, type checking, and error classification before returning to the agent. Do not let empty responses, malformed JSON, or HTTP error codes propagate as success. The agent cannot distinguish "I searched and found nothing" from "the search API timed out silently."

**2. Add a harness-level retry with exponential backoff and circuit breaking.**
If a tool call fails, the harness—not the agent—decides whether to retry. Use exponential backoff for transient errors (429s, timeouts), hard stop for auth failures, and a circuit breaker that stops the run if a dependency is consistently down. Cap total retries at 3 to avoid runaway cost.

**3. Separate concerns: define "done" in the harness, not in the prompt.**
The agent framework handles tool orchestration. The harness handles termination criteria: maximum steps, maximum cost per task, output schema validation, and quality gate scoring. These are infrastructure policies, not reasoning decisions. When the harness says "this output is invalid," the run stops—not the agent's judgment.

**4. Route model selection by task complexity, not by default.**
Median agent cost ranges from $0.026/task (GPT-5-mini) to $0.241/task (Claude Sonnet 4.5) — a 9.3x price difference for workloads that look identical from outside. Use fast/cheap models for classification, routing, and retrieval; reserve expensive models for reasoning and synthesis. Prompt caching cuts input token costs 80-90%; plan caching cuts cost 50% and latency 27%.

**5. Run a lightweight harness eval alongside every model eval.**
Test the harness independently: inject a 500 from the search API and verify the agent gets a proper error. Simulate empty search results. Send a truncated file read. The model eval can pass while the harness silently swallows 15-20% of failures.

## Evidence

- **Engineering blog:** "Most agent failures after launch are not prompt or model failures; they are infrastructure failures. Teams typically spend 2+ months refining prompts for marginal gains (e.g., 20% → 11% failure rate) when the real root cause is swallowed tool call errors." — *Harness Engineering for AI Agents, 2025* — https://harness-engineering.ai/blog/lessons-learned-from-deploying-ai-agents-in-production

- **HN thread:** The Ask HN "How are you orchestrating multi-agent AI workflows in production?" thread surfaced a consistent pattern: teams building stateless agents hit walls fast when state needs to persist across turns. Solutions ranged from Postgres-backed conversation state to Redis session stores, all implemented at the harness layer, not in the agent framework. — *Hacker News, 2025* — https://news.ycombinator.com/item?id=47660705

- **Industry survey:** 70% of regulated enterprises rebuild their AI agent stack every three months or faster, reflecting how unstable the harness/integration layer remains. 65% of enterprise AI agent failures trace to context drift — data quality and integration issues — not to model capability gaps. — *Cleanlab AI Agents in Production 2025* — https://cleanlab.ai/ai-agents-in-production-2025

- **Cost benchmark:** Across 500 agent runs (5 tasks, April 2026), median per-task cost ranged from $0.026 (GPT-5-mini) to $0.241 (Claude Sonnet 4.5). P95 latency inflated 1.6-3.2x over median — teams designing SLOs on median latency ship systems that time out in production. — *GrowthEngineer.ai Agent Cost Benchmarks* — https://growthengineer.ai/blog/ai-agent-cost-benchmarks

- **Google Cloud blog:** Only 5% of AI prototypes reach production. Enterprise environments introduce "unpredictable blast radius" from unconstrained agentic orchestration. The gap between prototype and production is a harness gap. — *Stephanie Wong, Google Cloud Blog, 2026* — https://cloud.google.com/blog/topics/developers-practitioners/why-ai-apps-fail-in-production

## Gotchas

- **The framework does not enforce cost limits.** Without a harness-level cost governor, an agent that loops on a failed task can burn $2,300 in 15 minutes on a task worth $0.08. Set per-task cost caps in the harness, not in the prompt.
- **Staging does not catch harness failures.** Staging mirrors the model and prompt. It does not simulate 429 rate limits, schema drift in upstream APIs, or session state expiration. Use chaos injection at the harness layer to surface these before production.
- **"Agent framework" and "harness" serve different jobs.** LangChain and CrewAI handle how agents think and delegate. The harness handles what happens when a tool call fails, what the maximum cost per task is, and how outputs are validated. Mixing these responsibilities creates systems where no single layer is accountable for reliability.
