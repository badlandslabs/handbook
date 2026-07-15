# S-1156 · The Trajectory Eval Stack — When Your Agent Passed the Benchmark and Broke in Production

[Your agent scores 87% on your eval. Your users say it's broken. The benchmark measured whether the agent got the right answer. It didn't measure whether the agent got it through a reckless path, burning $4 in API calls, calling the wrong tool twice, and ignoring a constraint that happened not to bite this time. This is the eval gap that costs teams months of reactive firefighting.]

## Forces

- **Benchmarks measure answers. Production measures behavior.** A benchmark tests a snapshot. An agent runs a loop — tool calls, state changes, conditional branches — and the failure modes live in the trajectory, not the endpoint. The lab-to-production gap averages 37%.
- **Most agent failures look like software bugs, not LLM mistakes.** A practitioner running a production eval suite found that the majority of failures came from broken URLs in tool calls, agents calling localhost in cloud environments, missing API keys, and external dependency failures — none of which a benchmark would catch.
- **Cost per task can vary 50x across models or prompts for identical accuracy.** Scoring only the output misses the economic dimension entirely.
- **Single-number scores hide regression.** An agent can score slightly higher on final output while using 3x more steps, calling wrong tools more often, and ignoring guardrails that didn't trigger this time.

## The Move

Build a trajectory-first eval stack that measures *how* the agent runs, not just *what* it outputs. Three layers, each answerable independently:

**Layer 1 — Component checks (fast, deterministic):** Validate that each tool, API connection, and environment dependency works in isolation before the agent ever runs. Treat these like unit tests — they run on every commit and catch broken URLs, missing keys, network failures, and schema drift.

**Layer 2 — Trajectory scoring (medium cost):** Score the entire execution trace: which tools were called, in what order, with what arguments, and whether each step satisfied policy. Assign per-step rubrics. Track tool call precision/recall — did it call the right tool at the right time? Did it recover correctly from a failure? Run 10+ trials per test case to handle variance.

**Layer 3 — End-to-end outcome (high cost, selective):** Measure final task completion against ground truth. Use for regression gates and release criteria, not iteration. Pair with LLM-as-judge for nuanced quality scoring, but validate the judge itself against a small human-annotated sample first.

Key metrics to track at each layer:

- **Task success rate** — did it complete the goal?
- **Step efficiency** — how many tool calls per successful task?
- **Tool call precision** — right tool, right arguments?
- **Cost per task** — including retries and wasted calls
- **Constraint violations** — did it breach any guardrails along the way?
- **Recovery quality** — if it failed a step, did it recover gracefully?

Minimum viable setup: 50–200 real production examples, per-step rubrics, statistical tracking across runs, and a held-out set you never tune against. The 70/40 rule from enterprise eval teams: 70% coverage of agent behaviors, 40% of development time on evaluations.

## Evidence

- **HN post (colinfly):** Running a production eval suite against an AI agent, most failures surfaced as system-level problems — broken URLs dropped scores to 22, agents calling localhost in cloud environments got stuck at 46, missing API keys caused silent failures. "Evaluating agents isn't just about scoring outputs. It's about validating the entire system: tools, environment, data access, and how the agent interacts with all of it." — [HN #47416033](https://news.ycombinator.com/item?id=47416033)

- **Practitioner blog (jamesm.blog, June 2026):** Endpoint evals certify answers, not behavior. An agent asked to refund orders under $50 can reach the right total through a reckless path — wrong tool first, lucky recovery, policy ignored. Trajectory scoring catches this. Recommended minimum: 50–200 real examples, per-step rubrics, 10+ runs per example, replay harnesses for regression. — [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)

- **Anthropic Engineering (Jan 2026):** Detailed guide on agent evals distinguishing task (single test with defined inputs and success criteria) from trial (each attempt), from eval (measurement instrument). Stresses that agent capabilities — autonomy, tool use, state modification — make them harder to evaluate than static models, and that eval value compounds over the agent lifecycle. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Enterprise eval report (Galileo, 2025):** Survey of 500+ AI practitioners found 72% believe comprehensive testing drives reliability, but only 15% achieve elite eval coverage — a 57-percentage-point belief-execution gap. Established the 70/40 rule: 70% coverage of agent behaviors and 40% of dev time on evals. — [Galileo AI](https://galileo.ai/blog/ai-agent-metrics)

## Gotchas

- **Tuning your eval against your held-out set leaks signal.** If you iterate on your prompt to pass the eval, you've contaminated the measurement. Treat held-out sets like test sets in ML: touch them only at release gates.
- **LLM-as-judge needs its own eval.** An LLM judge can be wrong, biased toward verbose outputs, or fooled by confident hallucination. Validate judges against human-annotated samples before trusting their scores on production data.
- **Cost variance is invisible without instrumentation.** Log token counts and API call counts per trajectory. A "better" model that costs 50x more per task is not better in production — it's a budget leak.
- **Most eval failures in early agent deployments are infrastructure, not intelligence.** Fix broken tools and environment issues first. A tool call that 404s is not a reasoning failure, and patching the prompt won't fix it.
