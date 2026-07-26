# S-1695 · The Trace-Derived Golden Dataset Stack

You have a working agent. You have a benchmark. You have a score. What you don't have is any signal that your next prompt change won't break the thing that was working. The gap isn't model quality — it's that your test set doesn't represent what your agent actually fails on.

## Forces

- Traditional test suites assume deterministic output: same input → same output. Agents violate this on every turn
- The most representative test cases are the ones you can't invent — they come from real inputs your team never anticipated
- Synthetic evaluation data passes demos but breaks in production, because it wasn't generated from the actual failure distribution
- Single-score metrics (task success rate) mask the trajectory — an agent can reach the right answer through the wrong path
- ~40% of agent deployments fail post-launch not because the model is weak, but because evaluation methodology was skipped (Audit.co / enterprise research, 2025)

## The move

Build golden datasets from production traces, not from synthetic generation or SME hand-labeling.

**The core loop:** Production failure → trace capture → test case extraction → golden dataset → CI/CD gate → next deployment.

The key insight from Arthur.ai's regression testing pattern: every production failure is a test case you couldn't have invented. It hands you an authentic edge case, the real input distribution, and a concrete definition of broken.

**Three-layer evaluation architecture:**

- **End-to-end** — Did the task complete? Binary pass/fail on the final outcome. Used for release gates.
- **Trajectory-level** — Was the path efficient and sound? Did the agent use the right tools in the right order? Was reasoning coherent? This is where silent failures hide — an agent can report correct numbers while reading last year's report.
- **Component-level** — Which specific tool, retriever, or sub-agent broke? Isolate the failure point before it propagates.

**Metric layering by purpose:**

- **Deterministic checks** for exact things: tool name, parameter schema conformance, output schema
- **LLM-as-a-judge** for anything requiring judgment: tone, faithfulness to retrieved context, whether a reasoning step follows from prior observations
- **Programmatic/rule-based** for domain constraints, compliance checks, safety criteria

**Grading approach (Databricks / Confident AI patterns):**

- LLM-judge scoring with explicit rubrics (1–5 scale on defined dimensions)
- Reference answer verification for factual questions
- State-snapshot comparison (pre/post database state) for agents modifying external systems
- Agent-as-a-judge: use a capable LLM agent to evaluate another agent's full trajectory, enabling rubric-based assessment of process quality rather than just output quality

**Synthetic data as a supplement, not a foundation:**

- Generate edge cases and diversity augmentation via synthetic methods — this accelerates iteration and skips weeks of SME labeling (Databricks reported cutting eval dataset creation from months to minutes)
- But seed synthetic generation from real production distributions, not from scratch
- Validate synthetic sets against real traces before using them as gates

**CI/CD integration pattern (Google Cloud, Galileo Labs):**

- Run full evaluation suite on every pull request that touches the agent's prompt, tools, or model version
- Set threshold scores per metric — deployments blocked below threshold
- A prompt change that improves one query type can degrade others; automated regression gates catch this before users do

## Evidence

- **Engineering blog — Google Cloud:** Recommends operationalizing evaluation as an automated, continuous process integrated into CI/CD, where eval runs automatically with every proposed change. Emphasizes trajectory analysis over final-output-only scoring because silent failures — correct answers via wrong reasoning — are the hardest failure mode to catch. — [cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Engineering blog — Databricks:** Synthetic data generation API for agent evaluation — customers report generating evaluation datasets in minutes rather than waiting weeks to months for SME labeling. Key constraint: synthetic data must be grounded in proprietary data and actual use cases to avoid the demo-to-production gap. — [databricks.com/blog/streamline-ai-agent-evaluation-with-new-synthetic-data-capabilities](https://www.databricks.com/blog/streamline-ai-agent-evaluation-with-new-synthetic-data-capabilities)
- **Primary source — Arthur.ai:** Production failures are the highest-value regression test inputs. The loop is: trace → test case → golden dataset → CI/CD gate. Specific challenges: non-determinism (same input can pass/fail across runs), multi-step trajectories (failures hide in intermediate tool calls), and massive input space (production distribution exceeds any synthetic set). — [arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Framework — Confident AI (DeepEval):** Open-source framework (17K+ stars) using trace-based evaluation. Agents are instrumented once with `@observe`; every run emits a trace with per-component spans (LLM calls, tools, retrievers). Metrics attach at end-to-end or component level. GEval provides LLM-as-a-judge with explicit rubric definitions. — [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **Research — ClawsBench:** Benchmark for productivity agents using state-snapshot evaluation — pre/post database comparison scores task success. Critiques existing benchmarks for using simplified environments that miss realistic stateful, multi-service failure modes. State-based evaluation catches cases where an agent produces correct output through a flawed process. — [arxiv.org/html/2604.05172](https://arxiv.org/html/2604.05172)
- **InfoQ article:** "Agents are systems, not models — evaluate them as integrated systems with planning, tool-calling, state maintenance, and multi-turn adaptation." BLEU/ROUGE and single-turn accuracy don't capture how agents fail in practice. Hybrid evaluation (LLM-as-a-judge + trace analysis + human review) is described as non-negotiable for production. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **Eval saturation:** A suite at 100% task success tracks regressions but gives no signal for improvement. You need trajectory-level metrics to know where to invest next.
- **Non-determinism means pass/fail isn't binary:** Run eval cases multiple times with temperature variations and track pass-rate distribution, not just pass/fail.
- **Synthetic data overfit:** Agents trained or evaluated on synthetic data perform well in demos but degrade on real-world inputs. Validate synthetic sets against a held-out production trace sample before treating them as authoritative.
- **Component-level isolation is often skipped:** Teams evaluate end-to-end and declare victory. When a regression occurs, they can't tell whether the retriever, the tool caller, the planner, or the LLM itself degraded — and they spend days debugging what a span-level trace would have shown in minutes.
- **Golden datasets go stale:** Production input distributions shift. A golden dataset built from Q1 failures will drift from Q3 failure modes. Re-derive from production traces on a scheduled cadence (monthly or per-release, whichever is more frequent).
