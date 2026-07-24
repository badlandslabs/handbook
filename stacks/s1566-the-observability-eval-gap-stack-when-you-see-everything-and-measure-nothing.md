# S-1566 · The Observability-Eval Gap Stack — When You See Everything and Measure Nothing

You instrumented your agent with full trace collection. OpenTelemetry, Langfuse, Phoenix — you see every tool call, every LLM response, every token. You are proud of the observability. Then a regression ships to production and you find out about it the same way you always do: a user emails. Your observability stack generates beautiful spans; your eval stack is a spreadsheet from last quarter.

## Forces

- **Observability without evaluation is theater.** Teams instrument everything — 89% report having observability in place — but only 52% run offline evaluations and just 37% have online production evals. The gap between "seeing what happened" and "knowing if it was good" is 37+ percentage points.
- **Production traces are the highest-signal data you have, and most teams throw them away.** Every production failure hands you a test case you could not have invented: a real edge case, a real input distribution, a real definition of "broken" for your system. Yet most teams' eval datasets are synthetic.
- **The CI/CD gate is the only enforcement point that matters.** Without evals wired into the release pipeline, every code or prompt change ships blind. Observability tells you something broke after the fact; eval gates stop the break from shipping.
- **Golden datasets rot.** Handcrafted test sets go stale as your agent evolves. The only test sets that stay current are the ones grown from production — yet the machinery to do this automatically rarely exists.

## The move

Build the closed loop from production failure to regression gate:

1. **Capture full execution traces on failure.** Record not just the final output but the complete trajectory: every tool call, every intermediate LLM response, every branching decision. The failure mode for agents is almost never in the final output — it is in step 3 cascading into step 7.

2. **Convert each production failure into a named test case.** Tag it with what broke (tool error, hallucinated call, context drift, cost blowout), the input that triggered it, and the expected behavior. This becomes a row in your golden dataset.

3. **Wire the golden dataset into CI as a mandatory gate.** Every PR runs the regression suite against the new agent version. The gate fails if any previously-seen failure pattern recurs. This is the enforcement mechanism observability alone cannot provide.

4. **Add a sampled online eval layer in production.** Not every request — sample 5-10% of live traffic and run it through LLM-as-judge scoring. This catches regressions in real input distributions your offline dataset never covered.

5. **Track drift over time, not just per-release.** Eval scores are a time series. A 2-point drop in a key metric over a week is more actionable than a pass/fail on a Tuesday afternoon.

## Evidence

- **Industry survey (AgenticWire, Jun 2026):** 89% of organizations have observability for AI agents, but only 52% run offline evaluations and 37% have online production evals — a 37+ percentage point gap between seeing and measuring. Quality is the top production blocker at 32% of teams.
  — [AgenticWire: Agent Eval as Infrastructure (Jun 2026)](https://www.agenticwire.news/article/agent-eval-infrastructure-2026)

- **Amazon engineering (AWS ML Blog, 2026):** Deploying thousands of agents since 2025, Amazon's evaluation library generates metrics automatically from trace files — including default metrics for tool selection accuracy, reasoning coherence, and memory retrieval efficiency. Key lesson: "Traditional LLM evaluation methods treat agent systems as black boxes, evaluating only final outcomes and failing to identify why agents fail."
  — [AWS ML Blog: Evaluating AI Agents at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Research (Zylos Research, May 2026):** UC Berkeley examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be gamed to near-perfect scores without solving a single real task. One team gamed 890 tasks with a single character change. SWE-bench Verified had confirmed evaluation-set leakage in OpenAI's training pipeline.
  — [Zylos Research: AI Agent Evaluation and Benchmarking Beyond Task Completion (May 2026)](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)

- **Practitioner experience (r/LocalLLaMA, 2025):** "I work at a company that develops AI agents for information retrieval. Most specific use cases don't have public benchmarks. Creating a good evaluation dataset is extremely costly. The stochastic nature of LLMs makes it very hard to affirm how well they behave."
  — [r/LocalLLaMA: The Eval Problem for AI Agents](https://www.reddit.com/r/LocalLLaMA/comments/1qltqfx/the_eval_problem_for_ai_agents/)

## Gotchas

- **Logging everything is not the same as evaluating anything.** Teams with full trace observability often have zero automated evaluation. The instrumentation investment is real, but the eval payoff is zero without a scoring layer on top.
- **LLM-as-judge needs its own validation.** Using Claude or GPT-4 to score your agent's outputs is powerful and scalable, but you must first confirm the judge correlates with human judgment on a labeled subset. A judge that confidently agrees with wrong answers is worse than no judge.
- **Golden datasets require curation ownership.** Without a designated owner, production failure → test case conversions happen once and never get updated. The dataset atrophies and the CI gate becomes meaningless noise.
- **The benchmark survival ratio is brutal.** Agents scoring 90%+ on SWE-bench retain roughly 35% of that performance in production. If your eval dataset is benchmark-derived, your gate is measuring the wrong thing.
