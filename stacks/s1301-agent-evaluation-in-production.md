# S-1301 · Agent Evaluation in Production

The moment your agent touches real users, your demo evals stop telling you anything useful — and you have no idea what you don't know.

## Forces

- Standard LLM benchmarks (MMLU, GSM8K) test isolated responses, not multi-step agent trajectories — they predict nothing about whether your agent calls the right tool at the right time
- Endpoint scoring (final answer right/wrong) misses the failure mode that burns budget in production: right answer, reckless path — wrong tool first, lucky recovery, ignored constraints
- Agents can loop on unexpected tool responses for hours, burning hundreds of dollars, without the model being "broken"
- Without repeatable evals, no one will route real traffic through the agent — 68% of agent projects stall at the evaluation stage (Qcode, 2026)
- Evaluators introduce non-determinism themselves — an LLM-as-judge can hallucinate scores if not calibrated against human ratings

## The Move

**Eval the trajectory, not the output.** Traditional unit-test thinking assumes `input → function → output`. Agents do `input → perceive → select tool → execute → interpret → adapt → repeat`. You need to score every node in that chain.

**Build the harness in five layers (bottom-up):**

1. **Deterministic checks first** — unit-test-style assertions: was the right tool called, with the right arguments, in the right order? These are fast, reproducible, and catch 40-60% of regressions without touching an LLM.
2. **Step-level rubrics** — for each tool call or decision point, write a 2-4 point rubric (0=wrong, 1=partial, 2=correct). Aggregate to a trajectory score.
3. **LLM-as-judge for open-ended quality** — grade persona adherence, instruction following, tone, and multi-turn coherence with a separate LLM call. Give it an "unknown" escape hatch to avoid hallucinated scores. Calibrate against 20-50 human-rated examples before trusting it.
4. **Human review on 10% sample** — spot-check one in ten runs. Use this to correct evaluator drift, not to score everything.
5. **Production monitoring** — live scoring on every real session via an observability harness. Flag trajectories that exceed cost, latency, or step-count thresholds.

**Run statistics, not singletons.** Run 10-100 trials per task depending on variance. Track `pass@1` (first-shot accuracy, measures capability) and `pass@10` (consistency under retries, measures reliability). One number tells you if the agent *can* do it; the other tells you if it *will*.

**Build your golden dataset from production failures.** Every time an agent does something wrong in front of a real user, you have a test case you could not have invented: an authentic edge case, a real input distribution, and a concrete definition of "broken" for your system. The loop: production failure → trace → test case → golden dataset → CI release gate. (Arthur.ai, June 2026)

**Minimum viable eval suite:** 50-200 real (not synthetic) examples, per-step rubrics, 10+ runs per example, statistical regression tracking, and a held-out set you never tune against.

**Instrument before you judge.** Full tracing is a prerequisite — you cannot score what you cannot see. Log complete transcripts (tool calls, model calls, retrieval, handoffs, cost, latency, errors) through LangSmith, Langfuse, Helicone, or Arize Phoenix. Langfuse is open-source and self-hostable. If debugging requires more than two clicks to see the full trace, you won't do it.

**Put evals in CI.** A regression test that only runs manually is a regression test that won't run. Gate deploys on trajectory score thresholds. Replay captured traces against new model versions without re-hitting production.

## Evidence

- **AWS ML Blog (Amazon):** Thousands of agents deployed across Amazon since 2025. Their finding: traditional LLM evals treat agent systems as black boxes and only evaluate final outcomes — they fail to pinpoint root causes of failures across tool selection accuracy, multi-step reasoning coherence, and memory retrieval efficiency. Proposes four evaluation axes: task completion, tool use, safety/compliance, cost. — [URL](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **James M (practitioner blog, June 2026):** "Endpoint evals miss the failure mode that hurts in production — an agent can reach the right answer through a reckless path." Recommends trajectory rubrics, replay harnesses, minimum 50-200 real examples, 10+ runs per example, statistical regression tracking, held-out sets. — [URL](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)
- **Cekura (April 2026):** Golden datasets from production failures form the highest-value test sets. Layered grading: deterministic checks first, LLM-as-judge once you have 100 trials to calibrate, human review on 10% sample. Recommends `pass@1` for capability, `pass@10` for reliability. — [URL](https://www.cekura.ai/blogs/ai-agent-evals)
- **MCPlato (May 2026):** 9 tool harnesses ranked — LangSmith, Langfuse, Helicone, Arize Phoenix, Braintrust, RAGAS, DeepEval, AgentOps, PromptLayer. Every production eval harness must answer: What happened? Was it good? Did we regress? What is the root cause? Is it safe? — [URL](https://mcplato.com/en/blog/top-ai-agent-evaluation-observability-harnesses-2026)

## Gotchas

- **Evals that don't match production distribution** — synthetic examples generated from prompts look nothing like real user inputs. Your eval score will be meaningless. Start with real traces.
- **LLM-as-judge without calibration** — an uncalibrated judge introduces as much noise as it removes. Pair it with 20-50 human-rated samples and measure agreement before trusting it.
- **Scoring only the final answer** — this passes agents that reach correct answers via reckless paths, and fails agents that try the right approach but get unlucky. Score each step.
- **No step-count or cost ceiling** — an agent looping for 14 minutes looks fine if it eventually produces a correct output. Set hard limits on steps, latency, and cost per task.
- **Tuning against your held-out set** — if you iterate on your eval until it passes, you've overfit your evals to your test data. Keep a held-out set that never gets used during development.
