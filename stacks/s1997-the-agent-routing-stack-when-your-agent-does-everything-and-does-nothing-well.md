# S-1997 · The Agent Routing Stack — When Your Agent Does Everything and Does Nothing Well

*When a single agent is asked to handle code reviews, customer replies, and data analysis, and it produces mediocre output for all three — because the same model, prompt, and tools are the wrong fit for each. You need routing: a control layer that inspects the incoming task and dispatches it to the right agent, model, or workflow path.*

## Forces

- **One agent is the wrong unit of work.** A generalist agent handles every task type, but no model is equally strong at code, creative writing, and structured data extraction. A single system prompt that tries to cover everything dilutes all of them.
- **Routing overhead is real.** Adding a router adds latency (~0.5–2s for LLM-based classification), a new failure point, and complexity that can exceed the cost savings from routing to cheaper models.
- **Routing without a quality signal is guessing.** Teams route on request type but forget to verify the downstream output actually met quality bar — which defeats the purpose entirely. False negatives mean double-charging; false positives mean shipping bad output.
- **The HN consensus is clear.** After a year of production deployments, the strongest signal from real teams is: the most successful agents use simple, composable patterns — routing among them. Complex orchestration frameworks consistently underperform because the routing logic itself becomes unmaintainable.

## The Move

Classify the incoming request, then dispatch it to the most cost-effective agent or model that can reliably complete it.

**Three routing mechanisms, in order of complexity:**

1. **Direct routing** — deterministic rules on request attributes (schema, topic tag, user tier). Zero extra LLM calls. Use when request structure is predictable and you have known task-type labels. Examples: "field=support → support agent", "schema=json → structured extraction model".
2. **LLM-based classification** — a lightweight model (or the same model with a classification prompt) inspects the request and returns a routing decision. Use when intent is ambiguous and the classification prompt is simpler than a single unified agent prompt. Typical latency: 0.5–2s. Return structured output (JSON with `route` field) for deterministic downstream parsing.
3. **Cascading (tiered escalation)** — route to a cheap model first; if it fails a quality gate (structured output validation, unit test, relevance check), escalate to a more capable model. Works best when you have a cheap signal for "did this actually solve the task." This is why JSON extraction and tool-use workflows love cascading.

**What to route on:**
- Task type (code, summarization, creative, data extraction, Q&A)
- Request complexity (simple lookup vs. multi-step reasoning)
- User tier (internal power user → full-featured agent, external → constrained agent)
- Output format requirement (structured JSON, prose, code)

**What NOT to route on:**
- Sentiment, vague "quality" scores with no downstream validation
- Route decisions that require the same model complexity as just doing the task

**Guardrails:**
- Route decisions must be logged and auditable — every routing call is a potential failure point
- Set a maximum escalation depth (e.g., 2 tiers) to prevent infinite loops
- Monitor misrouting rate; above 8%, the router needs retuning

## Evidence

- **Engineering post:** Anthropic's "Building Effective Agents" (Dec 2024) — the canonical source on the routing pattern. Found that teams achieving the best results used simple composable patterns rather than complex frameworks. "Over the past year, we've worked with dozens of teams building LLM agents across industries. Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **Benchmark study:** RouteLLM (open-source, LMSYS/UC Berkeley) — demonstrated 85% cost reduction while maintaining 95% of GPT-4 performance on MT Bench. Their best causal LLM router achieves 95% GPT-4 performance on MMLU while routing GPT-4 for only 54% of requests. — [URL](https://arxiv.org/abs/2405.01057)
- **Technical tutorial:** Dylan Castillo's Pydantic AI implementation of parallelization and orchestrator-worker patterns — shows concrete code for implementing routing at the workflow level, with parallel execution of routed subtasks. Published July 2025. — [URL](https://dylancastillo.co/til/parallelization-orchestrator-workers-pydantic-ai.html)
- **Industry analysis:** Thinking.inc's "AI Agent Orchestration Patterns (2026 Guide)" — reports production routing characteristics: 0.5–2s routing latency, 30–60% cost savings vs. uniform model dispatch, and 3–8% baseline misrouting rate. Notes that "most failures originate in orchestration design rather than individual agent capability." — [URL](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns)
- **HN production discussion:** "Ask HN: How are teams productionizing AI agents today?" — community discussion (2026) shifted from "can we build agents?" to "can we keep them running?" Surfacing infrastructure needs around routing, observability, and graceful failure. — [URL](https://news.ycombinator.com/item?id=47349510)

## Gotchas

- **The router is your new blast radius.** A bad routing decision affects every downstream call. Test it like production code: unit tests on classification, A/B on routing rules, monitoring on misroute rate.
- **Don't route on what you can't validate.** Snorkel AI's 2025 "Self-Critique Paradox" study found that adding a self-critique loop on tasks where baseline accuracy is already ~98% drops it to ~57%, because the critic hallucinates flaws. If the baseline is strong, the routing overhead isn't paying off — just execute directly.
- **Intent-based routing is harder than it sounds.** Classifying "technical question" vs. "casual question" is straightforward. Classifying "this technical question is actually a social engineering probe" is not. Start with structural routing (schema, tags, user tier) before investing in semantic classification.
- **Routing latency compounds.** A 1s LLM-based router + a 2s downstream call = 3s before the user sees anything. For user-facing workflows, direct/structural routing avoids the latency tax entirely.
