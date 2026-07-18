# S-1287 · The Evaluation Illusion — When Your Agent Passes Tests and Still Fails in Production

Your agent scored 94% on your eval dataset. It passed CI. Your benchmarks look great. Then production data hits — real users, edge cases, Unicode names, null values, concurrent requests — and the failure rate doubles. You were measuring the wrong thing. The agent was fine. The evaluation was the problem.

## Forces

- **The happy-path trap.** Agent demos showcase correct behavior on canonical inputs. Eval datasets are usually built from the same canonical inputs, creating a self-referential loop where your test only measures whether the agent handles what it was already shown.
- **Output correctness ≠ trajectory correctness.** An agent can reach the right final answer via the wrong path — too many tool calls, a policy violation midway, a hallucination that was lucky enough to pass. Final-answer scoring misses this.
- **Stochasticity hides flakiness.** The same agent with the same input can produce different tool-call sequences on different runs. A single eval run gives a point estimate, not a distribution.
- **Offline evals don't see production distribution.** Production traffic is shaped by real user behavior — adversarial inputs, unexpected sequences, constraint violations — that your held-out dataset never captured.
- **LLM-as-judge has structural biases.** Judge models favor longer answers, are susceptible to position bias, and can be gamed by prompt framing — making "metric green, user red" a documented failure mode.

## The move

Measure three distinct layers, not one. Combine offline benchmarks with production feedback loops. Treat eval as a living system, not a one-time gate.

**Layer 1 — Final-answer evaluation (necessary but not sufficient):**
- Score the agent's final output against ground-truth expected results using labeled test cases
- Use golden datasets: curated (input, expected_output) pairs built from real production traces or expert annotation
- Run the same scenario 3–5 times to surface non-determinism — a pass rate of 100% on a single run is not the same as 100% on five runs
- Gate CI on minimum pass-rate thresholds, but never deploy purely on final-answer scores

**Layer 2 — Trajectory evaluation (the layer most teams skip):**
- Score the full execution path: tool calls made, arguments passed, retries triggered, intermediate steps taken, total cost and latency
- Catch: wrong tool called, correct tool called with wrong arguments, unnecessary loops, policy violations, excessive token spend
- Specific metrics: tool-call accuracy, step efficiency (ideal steps vs. actual steps), recovery rate after errors, cost-per-task
- Key insight: a correct answer reached in 20 steps with two policy violations is a failing trajectory — layer 1 would pass it
- Use structured trace analysis: log every LLM call, tool invocation, and state transition so trajectories can be replayed and audited

**Layer 3 — Per-turn production labeling (the layer that closes the loop):**
- Classify each production turn for meaning: jailbreak attempts, prompt leaks, policy violations, user frustration signals, off-topic drifts
- Use a combination of rule-based classifiers (keyword/pattern matching for known failure modes) and LLM classifiers (for novel patterns), with human review on a sample to calibrate
- Keep per-turn latency under 90ms to enable real-time intervention; batch labeling is acceptable if intervention isn't required
- Feed per-turn labels back into the eval dataset: when monitoring detects an anomaly, extract the interaction, anonymize PII, and add it to regression tests automatically

**Production → Eval feedback loop:**
- Instrument the agent to capture traces in production (every decision, tool call, output)
- Periodically mine production traces for new failure patterns and add anonymized examples to the eval dataset
- Run regression suite on every prompt or model change before shipping — the same dataset that powered the original eval gates the update
- Track operating envelopes (cost, latency, token budgets) alongside quality scores; a "passing" eval that costs 10× more than the previous version is a regression

**Framework choices (2026 landscape):**
- **DeepEval** (Confident AI, open-source): Eval-as-code approach; metrics live in git, integrates with pytest; strongest for engineering teams that want audit trails and CI/CD gates
- **LangSmith** (LangChain): Native trace capture for LangChain/LangGraph stacks; observability + eval in one platform; strongest when the agent is already built on LangGraph
- **Braintrust**: SaaS-first with experiment comparison UI; enables non-engineers to review and label outputs; strongest for cross-team evaluation where PMs or domain experts judge quality
- **τ-bench** (Sierra Research): Research-grade benchmark for tool-agent-user interaction; domain-specific (airline, retail); used by teams that need rigorous simulation before production
- **AWS Agent Evaluation** (awslabs): Open-source (Apache 2.0, 369 stars); supports Amazon Bedrock, Q Business, SageMaker; strongest for AWS-native deployments

## Evidence

- **arXiv survey (2025):** "Evaluating these agents remains a complex and underdeveloped area." arXiv:2507.21504 categorizes agent evaluation along two dimensions: objectives (behavior, capabilities, reliability, safety) and process (interaction modes, datasets, metric computation). Found that trajectory-level and per-turn evaluation are systematically underrepresented in practice. — https://arxiv.org/abs/2507.21504

- **HN "Ask HN: How are you testing AI agents before shipping to production?" (2026):** Practitioners reported the "Constraint Decay" failure — agents ace demos on canonical inputs but fail on edge cases (null values, Unicode names like O'Brien or 北京, empty fields, concurrent requests). Gartner cited: over 40% of AI agent projects will fail by 2027, with inadequate evaluation as the primary cause. Real incident: a prompt injection in a customer support agent processed a $47,000 fraudulent refund. — https://news.ycombinator.com/item?id=47325105

- **Confident AI blog (Apr 2026):** Detailed three-layer framework: final-answer (correctness of last message), trajectory (correctness of the full execution path including tool calls and retries), and per-turn (meaning of each production turn). Notes that LLM-as-judge fails on "metric green, user red" — a judge model can rate an answer highly while users rate it poorly. Proposes continuous feedback loops from production monitoring into the eval dataset. — https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide

- **MorphLLM comparison (Jun 2026):** Benchmarks compared: SWE-Bench (2,294 issues in agent task set), τ-bench (tool-agent-user simulation), OSWorld (real desktop environments, 369 tasks), GAIA (general AI assistants). Notes that most agent teams don't run the right benchmark for their task shape — coding agents on GAIA score poorly but excel on SWE-Bench. — https://www.morphllm.com/ai-agent-evaluation

- **Data-Gate production guide (2026):** Lists five core failure modes unique to agent evaluation: non-determinism (same input → different outputs), multi-step cascading errors, context sensitivity, constraint decay on edge cases, and tool interaction failures (API timeouts, rate limits, schema mismatches). — https://data-gate.ch/ai-agent-evaluation-testing-2026/

## Gotchas

- **A 100% final-answer score with no trajectory analysis is a false signal.** The agent may be taking the wrong path every time and accidentally landing on the right answer. Always pair final-answer scoring with path inspection.
- **Eval datasets rot.** Production data distribution shifts; yesterday's edge cases become today's common cases. If you haven't updated your eval dataset in 90+ days, it's measuring a past version of your problem, not the current one.
- **LLM-as-judge amplifies known biases.** Judges prefer verbose answers, are susceptible to prompt injection via in-context examples, and correlate with model size — smaller judges are less reliable. Always spot-check judge scores against human rubrics on a 5–10% sample.
- **Synthetic eval cases miss real adversarial inputs.** Teams that build test cases from scratch (without mining production traces) systematically under-represent the adversarial distribution — prompt injections, jailbreaks, ambiguous inputs, constraint violations.
- **Cost and latency belong in the eval, not beside it.** A "passing" agent that costs 10× more or takes 5× longer than the previous version has regressed. Track operating envelopes in the same traces used for quality measurement.
