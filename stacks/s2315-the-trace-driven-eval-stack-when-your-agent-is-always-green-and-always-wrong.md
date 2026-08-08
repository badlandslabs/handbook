# S-2315 · The Trace-Driven Eval Stack — When Your Agent Is Always Green and Always Wrong

Your eval suite passes 97%. Your users are filing bugs. The disconnect is structural: your tests check whether the agent returned *something*, not whether it returned the *right thing* — and for agents, "something" looks a lot like success even when the outcome is wrong. This is the eval gap: the architectural distance between passing tests and a system you can actually trust.

## Forces

- **Pass/fail is a lie for agents.** A task-completion task can pass (agent said "done") while the agent hallucinated a database table name, called the wrong API, or reasoned itself into a confident wrong answer. The output looks fine; the outcome is broken.
- **Trajectory matters as much as outcome.** An agent that lands on the right answer via lucky hallucination is more dangerous than one that gets it wrong through sound reasoning — it trains you to trust it. The eval must inspect the reasoning path, not just the final output.
- **Agents are stochastic.** The same prompt can produce a correct answer and an incorrect one on back-to-back calls. A single pass/fail is statistically meaningless without reruns.
- **Quality dimensions multiply.** Factual accuracy, tool selection, argument correctness, tone, safety, cost, latency — each is a separate metric that needs its own scorer. Most teams collapse to one number and lose fidelity.
- **Human review doesn't scale.** Spot-checking 5% of traces catches loud failures but misses the long tail of plausible-looking failures that erode trust over time.

## The Move

Treat evals as a production pipeline, not a testing afterthought. The pattern that teams converge on: **traces as test cases, scorers as assertions, CI as gatekeeper, production signals as feedback.**

- **Define scenario datasets before you write prompts.** The most common mistake: prompt-first, eval-second. Instead, enumerate concrete user scenarios (happy path, edge cases, known failure modes) into a golden dataset, then use those to drive prompt development. This prevents "the prompt got good at our test cases but nobody knows what the test cases are."
- **Layer two scorer types.** Code-based scorers for deterministic checks: did the agent call the right tool? Were the arguments schema-valid? Was the output format correct? LLM-as-judge for nuanced qualities: was the response factual, helpful, on-brand? The judge model should be different from the agent model to avoid self-serving bias.
- **Evaluate end-to-end outcomes AND component-level steps.** An agent can reach the correct final answer through the wrong reasoning (tool misuse, ignored constraints). Score both the outcome (did it solve the user's problem?) and the trajectory (did it use the right tools, with right arguments, in the right order?). Confident AI calls this trajectory metrics vs. outcome metrics.
- **Rerun critical scenarios multiple times.** Agents are non-deterministic. A single run can false-pass on flaky failures or false-fail on lucky edge cases. Statistical confidence requires N runs; treat eval results as distributions, not booleans.
- **Track operating envelopes in the same trace.** Cost and latency are part of quality. A 99%-accurate agent that costs $4 per query and takes 45 seconds per task isn't production-ready. Store token counts, step counts, total cost, and wall-clock time alongside quality scores in your trace store.
- **Calibrate LLM judges against human rubrics.** Sample traces reviewed by humans build rubrics that keep judges honest. A common failure: the judge rates everything 8/10 because it has no ground truth anchor. Human calibration surfaces cases where "metric green, user red" — the eval passes but real users complain.
- **Feed production traces back into test cases.** When users hit a failure mode that your eval didn't catch, add that scenario to the dataset immediately. This closes the loop between production signal and regression prevention. Braintrust calls this the eval flywheel.

## Evidence

- **Engineering post (Datadog):** Only ~25% of teams running LLM applications run any form of online evaluation for response quality. Datadog's Nov 2025 Agent Observability feature lets teams define domain-specific quality standards as natural-language scorers and apply them automatically to production traces, revealing that "operational metrics (latency, cost, error rate) show how a system behaves, but not whether its responses are correct or on-brand." — [Datadog Blog, Nov 25 2025](https://www.datadoghq.com/blog/custom-llm-evaluations)

- **Show HN + debate (GitHub/HN):** The `agent-skills-eval` tool (79 points, 37 comments) sparked a substantive debate on whether agent skills actually change behavior. A skeptic demonstrated Opus ignoring a 720-byte CLAUDE.md instruction in favor of shell habits, costing a SQL query lookup. The counterpoint: skills are probabilistic attention shapers, not deterministic rules — they increase the right behavior's likelihood, but don't guarantee it. This means evals for skills need to measure behavioral *probability shifts*, not binary compliance. — [HN Thread #48046023](https://news.ycombinator.com/item?id=48046023), [GitHub Repo](https://github.com/darkrishabh/agent-skills-eval)

- **Benchmark paper (ICML):** MemoryArena (2026), a new ICML benchmark, revealed that agents achieving near-saturated performance on existing long-context memory benchmarks (LoCoMo, LongMemEval) performed poorly on *interdependent multi-session agentic tasks* — tasks where agents must learn from earlier actions and use that memory to guide later decisions. This exposes a fundamental gap: most agent memory benchmarks test recall, not *memory-guided action*. Teams building memory systems need evals that test whether stored memory actually changes downstream behavior, not just whether it can be retrieved. — [MemoryArena Paper](https://arxiv.org/html/2602.16313v1), [memoryarena.github.io](https://memoryarena.github.io/)

- **Company post (Braintrust):** Braintrust's eval framework codifies the three-part pattern: data + task + scorers. Their "velocity paradox" — where fast iteration without evals creates 10x more rework — is backed by Notion's reported experience. Key principle: production traces become test cases, and evals run ahead of deploys to create a regression gate. — [Braintrust Blog](https://www.braintrust.dev/articles/how-to-eval)

- **Company post (Confident AI):** Identifies four agent eval failure modes that standard approaches miss: false task completion (agent reports "done" but nothing changed), intent drift across turns, traces that look fine to a judge while blowing cost/latency, and reasoning thrash (busywork in the log without real action). Their recommended stack: DeepEval for instrumentation and metrics, with CI gates on critical scenarios. — [Confident AI Blog, Apr 13 2026](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Don't evaluate only at the final turn.** Multi-step agents can drift mid-pipeline. Score each tool call, argument, and handoff — a wrong tool called in step 3 of 7 can still look like a successful final output.
- **LLM-as-judge has a self-serving bias problem.** Using the same model as agent and judge correlates scores upward. Use a different model family or a specifically-instructed judge with rubric grounding.
- **A single golden dataset goes stale fast.** User distribution shifts. New failure modes emerge. Without a pipeline to add production failure cases back into the test suite, your eval coverage shrinks over time even as your eval pass rate climbs.
- **Cost and latency live outside your quality dashboard.** Teams that track quality separately from infrastructure metrics miss the interaction: a prompt change that improves accuracy but doubles token count might not be a real improvement.
