# S-1604 · The Three-Layer Eval Stack — Measuring Agents, Not Just Answers

Your agent scored 94% on your eval suite. Two weeks later it silently started approving refunds without authorization, because the eval only checked whether the final answer was "correct" — not whether it called the right tools in the right order. This is the stack for actually knowing whether your agent is working.

## Forces

- **Endpoint scoring misses the failure mode that hurts in production.** An agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints that didn't bite this time. On a small eval set, this looks fine. In production it becomes a security incident or a cost blowout.
- **Traditional testing assumes determinism.** Same input, same output, exact-match assertions. Agents are probabilistic — the same input run twice can produce different reasoning paths, tool call orders, or phrasings. Your test harness needs to account for this.
- **Benchmarks tell you if a model can. Evals tell you if your agent does.** SWE-bench and MMLU are for choosing a base model once. Production evals run continuously against your specific tasks, policies, and data — and they measure the whole system (prompts, tools, retrieval, routing), not just the model.
- **One eval run is not evaluation.** Teams that validate thoroughly before launch and then stop monitoring see quality degradation within 30–60 days. Evaluation is an operational practice, not a pre-launch gate.

## The Move

Build a three-layer eval stack: **outcome metrics**, **trajectory metrics**, and **component metrics**. Run them in a continuous loop, not as a one-time gate.

**Layer 1 — Outcome metrics (does it work?)**
- Task completion rate, answer correctness, policy compliance
- Use deterministic checks where ground truth exists (exact match, AST validation, schema validation)
- Use LLM-as-judge for quality dimensions that require interpretation (tone, helpfulness, coherence)
- Calibrate the judge against human-labeled examples before trusting it

**Layer 2 — Trajectory metrics (how did it work?)**
- Capture the full execution trace: which tools were called, in what order, with what arguments, and whether each step satisfied policy
- Score trajectory dimensions independently: tool selection, argument extraction, result utilization, error recovery, plan coherence, task completion
- Set per-dimension thresholds for CI gates, not a single aggregate score — an agent that fails on tool selection should fail the gate even if the final answer is correct

**Layer 3 — Component metrics (what broke?)**
- Pinpoint which part of the system regressed: prompt drift, model degradation, retrieval quality, tool reliability, routing errors
- Log inputs and outputs at every step so failures can be traced back to root cause
- Track cost per task and latency per step as operational health signals

**The eval flywheel**
```
production trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring → new traces
```
Build eval datasets from real failure cases and production traces, not synthetic examples. Notion reported 10x improvement in issues triaged per day after moving from JSONL files and manual scoring to automated evaluation.

## Evidence

- **Engineering blog:** NVIDIA's agent evaluation guide draws a sharp line between model benchmarks (capability of foundation model in isolation) and agent evals (end-to-end system behavior in dynamic workflows). They recommend evaluating trajectories, tool calls, and outcomes — not just model scores. — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **Engineering blog:** Braintrust's production eval guide describes the data + task + scorers pattern and documents how Notion went from 3 to 30 issues triaged/fixed per day by replacing manual scoring with automated evaluation. Core insight: evaluate both end-to-end outcomes and individual steps, and run production traces back into the test suite. — [braintrust.dev/articles/how-to-eval](https://www.braintrust.dev/articles/how-to-eval)
- **Practitioner blog:** Slava Dubrov's eval framework post describes the three-layer stack (outcome, trajectory, component) and the trace-to-test-suite loop. Key technique: use deterministic checks for tool order, arguments, loops, and invariants; reserve LLM judges only where the check depends on interpretation; shape judges with Schema-Guided Reasoning (SGR) and calibrate against human labels before trusting scores. — [slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)

## Gotchas

- **LLM-as-judge needs its own eval.** Judge alignment with human labels is not guaranteed — especially on edge cases. Keep a small, versioned gold slice of human-labeled examples. When judge and human disagree, fix the rubric, not the model. Re-calibrate periodically as tasks evolve.
- **Aggregate scores hide regressions.** An agent that drops 20 points on tool selection but gains 2 points on answer quality looks neutral on an aggregate. Set per-dimension thresholds in CI so dimension-level regressions fail the gate.
- **Eval data rots.** Tasks change, policies update, edge cases emerge. A dataset that was representative six months ago may now be measuring the wrong things. Version your eval datasets and refresh them from production traces quarterly at minimum.
- **Running evals once is not evaluation.** Treat evals as operational infrastructure, not a pre-launch checkbox. Continuous evaluation (post-deploy monitoring feeding back into the eval suite) reduces production incidents by catching regressions before users see them.
