# S-1497 · The Eval-Driven Development Stack — When Your Agent Passed the Demo but Fails Production

Your agent aced every test case you wrote. You shipped it. Two weeks later a user hits a edge case, the agent loops forever calling the wrong tool, and your observability dashboard shows nothing because you never instrumented it. The demo was not the product. The eval suite was not the evaluation.

## Forces

- **An agent that returns the right answer through the wrong trajectory has failed quietly.** Scoring only the final reply is blind to the tool-call sequence, argument construction, and reasoning steps that produced it.
- **Agents are stochastic and multi-step — traditional LLM benchmarks don't apply.** MMLU and HELM evaluate a model as a function. Agents are systems that call tools, maintain state, and adapt behavior based on feedback. The evaluation surface is fundamentally different.
- **Lab-to-production gap is large and underreported.** Benchmarks run in clean, controlled environments. Production agents face ambiguous user queries, flaky APIs, rate limits, and unexpected data formats. Teams report 20–40% of regressions are missed by output-only scoring.
- **The compounding cost of multi-step failure.** Every reasoning step has an API cost. A looping agent with 75% per-trial reliability has only a 42% chance of passing three consecutive trials under a pass³ criterion — and it racks up three times the cost getting there.
- **Quality is the top production barrier, but most teams don't have a systematic eval practice.** LangChain's 2026 survey found only 52.4% of teams run offline evaluations on test sets; only 37.3% run online evaluations. The majority are flying blind.

## The move

Layer the eval stack across three dimensions: component-level checks, end-to-end task completion, and production telemetry. Build evals before the agent is capable — eval-driven development — not after.

**Define success at the task level, not the model level.**
- A **task** (test case) has defined inputs and success criteria. A **trial** is each attempt. Run multiple trials because agents are stochastic. A **grader** scores some aspect of performance. A **transcript** is the full agent trace — every tool call, argument, and intermediate output.
- Score both **task success** (did it accomplish the goal?) and **trajectory quality** (did it get there the right way?). An agent that calls the wrong tool five times before succeeding has not passed.

**Build a two-tier grader system.**
- **Code-based graders** for deterministic checks: did the agent call the right tools? Were the arguments schema-valid? Did it hit a tool-call budget or loop threshold? These catch regressions that LLM-as-judge misses.
- **LLM-as-judge graders** for nuanced qualities: response tone, reasoning coherence, whether the agent asked for clarification vs. guessing. These require human rubric calibration — sample traces to confirm the judge isn't saying "pass" when users say "broken."

**Run evals in CI/CD before every deploy, not as an afterthought.**
- Every production trace that surfaces an edge case becomes a test case immediately. Eval suites grow from production failures, not just from anticipated scenarios.
- Offline eval on test sets catches regressions; online eval on live traffic catches distribution shift — new failure modes that test sets didn't anticipate.

**Track operating envelopes alongside quality.**
- Cost per successful task, latency percentiles, token budgets, and tool-call counts belong in the same trace as quality scores. A passing eval that costs 50x more than budget is a failure.
- Monitor human-intervention rate: how often does a human need to override or correct the agent? This is the most direct signal of trust.

**Eval-driven development: define the eval before the capability.**
- Build evals that start at low pass rates, then iterate until the agent meets them. This makes capability gaps visible early and gives concrete targets for prompt changes, tool redesigns, or model swaps.
- When a new model drops, run the full eval suite. A capability eval that jumps from 30% to 75% tells you exactly which bets paid off.

## Evidence

- **Anthropic engineering post (Jan 2026):** "Owning and iterating on evaluations should be as routine as maintaining unit tests. Defining eval tasks is one of the best ways to stress-test whether the product requirements are concrete enough to start building." Teams practicing eval-driven development catch underspecified requirements before they become production failures. — [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **LangChain State of Agent Engineering (survey, 1,340 practitioners, Nov–Dec 2025):** Only 52.4% of teams run offline evaluations on test sets; only 37.3% run online evaluations. Quality is the #1 production barrier (32% cite it), while cost concerns dropped from prior year. — [LangChain: State of Agent Engineering 2026](https://www.langchain.com/state-of-agent-engineering) via [The Agent Report summary](https://the-agent-report.com/2026/05/state-of-agent-engineering-2026-langchain-datadog/)
- **Braintrust production patterns (Notion, Stripe, Zapier reference):** Production traces become test cases with one click; every edge case spotted in production gets added to the eval suite immediately. The eval-first architecture means experiments are directly tied to deployment — changes that pass offline evals ship to production with confidence. — [Braintrust: How to evaluate LLMs and AI agents in production](https://www.braintrust.dev/articles/how-to-eval)
- **Mastra.ai practitioner guide (Jun 2026):** "An agent with 75% per-trial reliability has only a 42% chance of passing all three trials under pass³." Breakpoints: single-turn accuracy ≠ multi-turn reliability. — [Mastra: AI Agent Evaluation](https://mastra.ai/articles/ai-agent-evaluation)
- **TECHSY production guide (2026):** "Agents fail silently and non-deterministically. An agent that returns the right answer through the wrong trajectory hasn't passed — it's failed quietly." Key metrics: task success rate, cost per successful task, latency percentiles, tool-call accuracy, faithfulness, human-intervention rate, drift, and safety-gate pass rate. — [TECHSY: Evaluate AI Agents in Production](https://techsy.io/en/blog/evaluate-ai-agents-in-production)
- **Microsoft SWE-Bench mutation study (2026):** Existing benchmarks overestimate agent capabilities by >50% over baseline for some models on public benchmarks, ~10–16% on internal benchmarks. Benchmark mutation techniques — converting formal GitHub issues into realistic user-style queries — reveal the true capability gap. — [arXiv: Saving SWE-Bench](https://arxiv.org/html/2510.08996)

## Gotchas

- **Goldens (golden datasets) catch regressions, not coverage gaps.** Running the same curated test cases repeatedly tells you if you broke something; it doesn't tell you what you missed. Supplement with adversarial cases, production-logged edge cases, and trajectory-level checks.
- **LLM-as-judge graders need human calibration.** The judge model can rate a trace "pass" while real users rate it "broken." Sample traces and cross-validate against human judgment before trusting judge scores broadly.
- **Multi-trial pass criteria compound fast.** A 75% per-trial pass rate sounds good until you realize that three required consecutive passes drops to 42%. Calibrate pass³ thresholds against actual production risk — high-stakes domains need higher per-trial thresholds.
- **Offline evals don't catch distribution shift.** The test set is frozen. Production traffic evolves. Online evaluation on live traffic — even a sample — is the only way to catch the new failure modes that didn't exist when you shipped.
