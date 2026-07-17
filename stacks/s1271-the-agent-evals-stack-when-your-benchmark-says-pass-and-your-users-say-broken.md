# S-1271 · The Agent Evals Stack — When Your Benchmark Says Pass and Your Users Say Broken

When your agent scores 87% on your test suite but costs 50x your budget per task and silently fails 30% of production sessions — this is the eval gap, and it's the reason most agent teams ship broken systems with high confidence.

## Forces

- **The benchmark crisis** — UC Berkeley researchers examined eight of the most prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be exploited to achieve near-perfect scores without solving the underlying task. Static task-completion scores became theater.
- **Output-only scoring misses regressions** — 20–40% of agent regressions go undetected by final-answer-only evaluation. The agent that reaches the right answer in 8 flailing steps is not the same as the one that gets there in 3.
- **The 37% lab-to-production gap** — benchmarks use clean inputs, predictable tool responses, and controlled environments. Production agents face ambiguous requests, flaky APIs, rate limits, and adversarial inputs. Same agent, different world.
- **Eval is afterthought** — most teams spend weeks on prompts and model selection but days (or hours) on evaluation. When the benchmark is wrong, every optimization based on it is also wrong.
- **Calibration drift** — LLM-as-judge models are updated over time, causing evaluation scores to shift even when the evaluated agent hasn't changed.

## The move

Evaluate the trajectory, not just the output. Build a multi-dimensional eval stack that treats task success, process quality, cost efficiency, and safety as first-class metrics.

**Trace the full execution path, not just the final answer:**
- Score whether the agent used the right tool at the right step, not just whether it reached the goal
- Track step efficiency — same answer in 3 steps and $0.05 scores differently from 8 steps and $0.40
- Log tool-call precision, recall, and F1 against a reference multiset (agent-eval-harness, tkarim45/agent-eval-harness)

**Combine automated scoring with human judgment — not one or the other:**
- Automated scoring (LLM-as-judge, deterministic checks, trace analysis) gives repeatability and scale
- Human judgment captures tone, trust, and contextual appropriateness that automation misses
- Use LLMs to triage simple cases; route complex, nuanced, or high-stakes cases to domain experts (Label Studio, October 2025)
- Validate judges against sample annotated data; adapt via DSPy, LLM-Rubric, or a small correction model (HN discussion on production AI agents principles)

**Treat operational constraints as evaluation targets from day one:**
- Latency, cost per task, token efficiency, tool reliability — not afterthoughts, first-class metrics
- Two agents with the same accuracy can differ 50x in cost per task; score both dimensions
- Track PII leakage, permission boundary violations, and policy compliance alongside accuracy

**Build regression baselines that survive model updates:**
- Store eval results as deterministic baselines alongside code; re-run on every commit
- A regression suite without baselines is a fire alarm with no volume knob — you can't tell if things got better or worse, only that they're different

**Use Agent-as-a-Judge, not just LLM-as-a-Judge:**
- Agent-as-a-Judge (a dedicated agent evaluating trajectories) dramatically outperforms standard LLM-as-a-judge that only sees final outputs
- It checks intermediate stages (did code compile? did the agent follow each sub-requirement? how many attempts or tool calls were used?)
- Reported parity with human evaluators on code tasks at a fraction of the cost (arXiv, 2025)

## Evidence

- **Research survey:** UC Berkeley researchers found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) were exploitable — near-perfect scores achievable without task resolution — demonstrating that static benchmarks have fundamentally decoupled from actual capability (Zylos Research, 2026-05-13) — https://zylos.ai/research/2026-05-13-ai-agent-evaluation-benchmarking/

- **Engineering post:** InfoQ analysis of production agent deployments found the 37% lab-to-production gap driven by benchmark cleanliness vs production variability, and recommends hybrid evaluation (automated + human) as non-negotiable, with operational constraints as first-class targets (Amit Kumar Padhy, InfoQ, 2026-03-16) — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned

- **HN discussion:** Thread on "Principles for production AI agents" surfaced that LLM-as-judge requires validation against annotated data and adaptation via DSPy or LLM-Rubric; one commenter noted "evals are a core part of any up-to-date LLM team — if some team was just winging it without robust eval practices they're not to be trusted" (Hacker News, 2025) — https://news.ycombinator.com/item?id=44712315

- **Open-source tool:** The agent-eval-harness (tkarim45, MIT) measures task success, tool-call precision/recall/F1, step efficiency, and cost per task for Claude-based agents — scoring the same answer differently based on trajectory quality — https://github.com/tkarim45/agent-eval-harness

- **Research paper:** Agent-as-a-Judge evaluation framework showed parity with human evaluators on code tasks while preserving the cost-effectiveness of LLM-based evaluation; judge agents evaluate sub-requirements at intermediate stages, not just final output (arXiv, 2025) — https://arxiv.org/html/2508.02994v1

## Gotchas

- **Benchmarks optimize for benchmarks** — teams that score well on MMLU or HumanEval routinely fail on real production tasks. Use benchmarks as a floor, not a ceiling.
- **LLM-as-judge has known biases** — position bias (prefers first or last answer), verbosity bias (rewards longer responses), self-preference bias (prefers responses similar to the judge's own outputs), and calibration drift as the judge model updates. Validate against human-annotated ground truth before trusting scores.
- **Synthetic users don't cover the tail** — persona simulation catches common failure modes but adversarial users, edge cases, and unusual domain-specific inputs require real production traffic or expert human evaluation.
- **Cost tracking is often missing** — eval frameworks focus on accuracy but ignore that 50x cost variance for equivalent accuracy makes the cheaper agent the better choice. Add cost-per-task to every eval run.
