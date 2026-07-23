# S-1545 · The Agent Evaluation Stack — When Your Benchmarks Lie and Your Team Is Flying Blind

Your agent passes every internal test. Your benchmarks look great. Your users are filing bugs daily. The agent completes tasks through broken paths, hits right answers via wrong reasoning, and silently degrades when the model version rolls over. This is the evaluation gap: the distance between what you can measure and what actually matters.

## Forces

- **Agents are trajectories, not outputs.** A unit test catches a wrong return value. It cannot catch an agent that loops 40 times before converging, uses the wrong tool 6 steps in, or reaches the correct answer through a plan that would fail on a slightly different input.
- **Benchmarks measure proxies, not production.** SWE-Bench Verified at 70–78% (May 2026) tells you something about coding agents. It tells you nothing about whether your customer support agent will handle a unicode name, a null field, or a concurrent request without hallucinating.
- **Evals go stale faster than code.** Models change. Providers update. The same prompt that scored 94% on your golden set last month now scores 87% with no code change. You need a system that catches this drift, not just a scorecard you ran once.
- **The right answer via the wrong path is still a failure.** An agent that books a flight by accidentally reading the wrong date from a calendar and then finding a coincidentally correct flight is worse than useless — it looks like it works until it doesn't.

## The Move

Build a layered evaluation system with four tiers, each catching what the tier below misses.

**Tier 1 — End-to-end success evals (the starting point, not the ceiling).**
Define a binary: did the agent achieve the user's goal? Write these first, before anything else. Start with 10–20 real user interactions sampled from production logs. Add a simple pass/fail output. This alone identifies 80% of your obvious failures. Source: aunhumano ("On evaluating agents," Sep 2025) — "You must create evals for your agents, stop relying solely on manual testing. Define a success criteria (did the agent meet the user's goal?) and make the evals output a simple yes/no value." https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/

**Tier 2 — Trajectory analysis (catches broken paths to right answers).**
Log every tool call, every intermediate decision, every state change. The metric is not just "did it succeed?" but "did it succeed efficiently, correctly, and without flukes?" Count steps, measure tool-call accuracy (did it call the right tool?), and flag trajectories that succeed only through error cancellation. Source: Maxim AI evaluation guide — "A travel planning agent might book flights before hotels or vice versa, both achieving the user's goal. Evaluating only the final outcome misses crucial insights about efficiency, user experience, and potential failure modes." https://www.getmaxim.ai/articles/evaluating-ai-agents-metrics-and-best-practices

**Tier 3 — Multi-dimensional benchmark tracking (catches capability drift).**
Track scores across the five benchmark axes that actually predict production performance: reasoning, tool use, planning, error recovery, and grounding. No single number captures this — you need a profile. On GAIA: top agents score 78–82% at Level 1, 60–68% at Level 2, and only 35–45% at Level 3 (multi-step real-world tasks requiring web browsing, API calls, and file manipulation). The Level 3 gap is where most current agents still fail. Source: Presenc AI "AI Agent Capability Benchmarks 2026" (May 2026) — "GAIA reveals level-3 gap: top agents 78-82% (L1), 60-68% (L2), 35-45% (L3)." https://presenc.ai/research/ai-agent-capability-benchmarks-2026

**Tier 4 — LLM-as-judge with guardrails (catches quality drift between evals).**
Use a stronger model to evaluate outputs from the production model. The debate is real: some practitioners report LLMs are unreliable judges, especially for subjective quality. Others report success with structured prompts and scoring rubrics. The consensus: use it for catching regressions and trajectory anomalies, not as ground truth. Validate LLM-as-judge scores against human-rated samples before trusting them at scale. Source: HN discussion on "Principles for production AI agents" — commenter roadside_picnic: "Did we just give up on evals? My experience building production AI tools has been that evaluations are vital... LLM judges failed in internal experiments." Counterpoint from commenter Uehreka: "It is far from obvious that LLMs are intrinsically bad critics" — evidence mixed. https://news.ycombinator.com/item?id=44712315

**Continuous eval pipeline (prevents staleness).**
Re-run the eval suite on every model version change and on a weekly schedule. Track scores over time. Alert on regressions > 5%. The 2025 Cleanlab survey found 70% of regulated enterprises rebuild their AI agent stack every 3 months or faster — eval drift is a direct consequence of stack churn without regression coverage. Source: Cleanlab "AI Agents in Production 2025" — "70% of regulated enterprises rebuild their AI agent stack every 3 months or faster." https://cleanlab.ai/ai-agents-in-production-2025

## Evidence

- **Survey (n=1,837 engineering/AI leaders):** Only 95 teams had agents live in production. Among those, fewer than 1 in 3 were satisfied with observability and guardrail solutions. 63% prioritized visibility as their top improvement goal. — [Cleanlab: AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **HN Ask thread + blog post:** A practitioner's account of trying to evaluate an agent in production using a benchmark-style approach — failed in ways they didn't expect, because the scaffold, not the model, was the problem. Multiple HN commenters confirmed this pattern. — [HN: What broke when I tried to evaluate an AI agent in production](https://news.ycombinator.com/item?id=47416033)
- **Benchmark landscape:** 26 benchmarks tracked across terminal, browsing, tool-use, and computer-use. Best verified agentic score (BrowseComp): GPT-5.6 Sol Ultra at 92.2% (May 2026). Best open-weight: Holo3-35B-A3B at 82.6%. BFCL (tool calling) remains the category with the most model variance — still the most unreliable predictor of production tool-call accuracy. — [Presenc AI: AI Agent Capability Benchmarks 2026](https://presenc.ai/research/ai-agent-capability-benchmarks-2026)
- **Guide:** Three failure modes unit tests cannot catch in multi-step agents: step repetition (looping without progress), incorrect tool selection (right goal, wrong means), and silent degradation (context window fills without error). — [RockB: AI Agent Testing Guide 2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)

## Gotchas

- **Evals are not tests.** A test asserts a property about code. An eval measures an emergent property of a model-plus-scaffold system — it changes when either changes, which makes attribution hard and staleness inevitable.
- **Golden datasets rot.** Real user inputs drift with product changes, seasonal behavior, and new edge cases. A golden set created in January is 40% stale by March for a high-traffic agent.
- **Passing your eval suite is necessary but not sufficient.** The eval suite covers what you've thought to test. The failure mode you haven't caught is the one that doesn't appear in your logs until a user encounters it.
- **Step count is a noise metric without context.** An agent that takes 40 steps to complete a task is not inherently worse than one that takes 8 — what matters is whether the extra steps were necessary. Measure path efficiency relative to a baseline of the minimal correct trajectory.
- **Benchmark parity ≠ production parity.** A model that scores 78% on SWE-Bench will not perform 78% as well on your internal codebase. The benchmark covers common patterns; your codebase has idiosyncratic ones that the benchmark never saw.
