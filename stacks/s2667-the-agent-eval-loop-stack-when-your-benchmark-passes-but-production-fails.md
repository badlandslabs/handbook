# S-2667 · The Agent Eval Loop Stack — When Your Benchmark Passes But Production Fails

Your agent scores 87% on SWE-bench. You ship it. Three weeks in, a user submits a Unicode edge case — O'Brien, null fields, concurrent requests — and the agent silently switches to a fallback model with no alerting. It keeps serving responses. They are wrong. The benchmark told you the agent was capable. It did not tell you which inputs would trigger the failure.

This is the agent eval gap: benchmark scores measure what an agent *can* do, not what it *will* do under production conditions. Closing that gap requires a layered eval architecture — end-to-end output checks, trajectory-level trace analysis, and continuous production monitoring — run together as a loop, not as a one-time gate.

## Forces

- **Benchmarks measure potential, not production.** A model that scores 80% on SWE-bench Verified does not tell you whether your coding agent will handle null values, Unicode names, or concurrent requests — the inputs that make up 80% of real traffic.
- **Outcome and trajectory are complementary and incomplete alone.** Outcome metrics (did the agent complete the task?) are cheap and fast. Trajectory metrics (how did it get there?) expose process failures — wrong tool selection, looping, unnecessary steps — but are expensive to collect and harder to grade.
- **Production inputs outnumber test suites by orders of magnitude.** No static test set can anticipate the diversity of live traffic. Teams that rely only on pre-deployment tests catch known failure modes; production monitoring catches the unknown ones.
- **LLM-as-judge is powerful and biased.** It scales evaluation to thousands of runs, but a single judge carries inherent biases and disagrees with human judgment ~31% of the time. Calibration is not optional.
- **Cost and quality are co-equal metrics.** Token costs compound silently. An agent that loops for 40 steps on a $2 task can bill $200. Evaluation stacks that ignore cost tracking miss the most common production failure mode.
- **Evaluation without CI integration is a checkpoint, not a practice.** A test suite that runs once before shipping degrades to theater. Evals that gate every deploy catch regressions the moment they appear.

## The move

Build a three-layer eval architecture and run it continuously as a feedback loop.

**Layer 1 — End-to-end output evals (black box)**
- Define success criteria per task as a simple yes/no: did the agent complete the user's goal?
- Run these on every CI push using a pytest-style framework (DeepEval, etc.)
- Start here. A binary end-to-end eval is far better than no eval at all.
- Instrument once with a tracing decorator (`@observe` or framework integration). Every agent run emits a trace automatically.

**Layer 2 — Trajectory-level trace analysis**
- Score the full execution path, not just the final output: tool precision, backtracking rate, recovery quality, step efficiency, error rate.
- Use deterministic checks for quantifiable metrics (exact match, tool call correctness, schema validation) — cheaper and more reliable than LLM judgment for precise tasks.
- Reserve LLM-as-judge for quality dimensions that require generalization: coherence, tone, reasoning quality, citation accuracy.
- Calibrate your judge: validate that it correlates with human judgment on a sample before running at scale. Multi-agent debate systems (multiple LLMs evaluating together) reduce judge disagreement from 31% to 3%.
- Track trajectory metrics per agent per week. Flag any agent showing >3% quality decline for investigation.

**Layer 3 — Continuous production monitoring**
- Run a sampled eval stream against live traffic, not just pre-deployment test suites.
- Sample 10% of production outputs for human review by default; 25% for client-facing workflows.
- Use a structured rubric with 8 quality dimensions scored 1–5. Track inter-rater reliability — if two evaluators score the same output wildly differently, the rubric needs work.
- Log every agent action with full trace context (tool calls, observations, token counts, cost). This is your audit trail for post-mortems.
- Pair quality monitoring with cost guardrails: hard spend limits per agent, token counters per model, alerting on anomalous spend spikes.

## Evidence

- **Anthropic engineering guide (Jan 2026):** Four eval dimensions — task correctness, tool reliability, reasoning quality, business/user impact. Recommends trajectory metrics over outcome-only. Distinguishes task (single test case) from trial (each attempt). Proposes grading rubrics per agent type. Notes that checking transcripts manually catches failures benchmarks miss. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **KDD 2025 survey (Mohammadi et al., SAP Labs):** Two-dimensional taxonomy for agent evaluation: evaluation objectives (behavior, capabilities, reliability, safety) × evaluation process (interaction modes, data, metrics, tooling, contexts). Notes offline/online eval distinction and that online production monitoring catches failure modes static datasets miss. — [arxiv.org/html/2507.21504v1](https://arxiv.org/html/2507.21504v1)
- **HN Ask HN thread on monitoring agents in production (2025):** Practitioners report cascade failures as the dominant failure mode — tool call #1 fails, agent keeps going, damage compounds. Common solutions: AgentShield for execution tracing and risk detection, Lava gateway proxy with spend keys for hard cost limits, OpenTelemetry instrumentation. Thread was prompted by DataTalks database wipe by Claude Code and a Replit agent deleting data during code freeze. — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **aunhumano blog on evaluating agents (Sep 2025):** Practical recommendation: start with end-to-end evals using a binary success criteria. Trace analysis is essential for debugging. Benchmark scores alone are insufficient — the recommendation is to always look at actual agent traces to identify issues. — [aunhumano.com/index.php/2025/09/03/on-evaluating-agents/](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)
- **MMNTM research on agent eval maturity (Dec 2025):** Five-level maturity model: Level 0 (no evals) → Level 5 (continuous production monitoring with automated rollback). Reports Gartner projection that 40% of agent projects will be cancelled by 2027, primarily due to inadequate evaluation infrastructure. Notes that ablation testing (removing an agent from the pipeline and measuring impact) is a key practice for identifying unnecessary overhead. — [mmntm.net/articles/building-agent-evals](https://www.mmntm.net/articles/building-agent-evals)
- **QASkills trajectory evaluation guide (2026):** Six trajectory metrics: tool precision, backtracking rate, recovery quality, length efficiency, token efficiency, error rate. Emphasizes that outcome-only scoring hides process failures — two agents can both succeed but one use 3 tools vs 15 with retries. — [qaskills.sh/blog/agent-trajectory-evaluation-guide-2026](https://qaskills.sh/blog/agent-trajectory-evaluation-guide-2026)
- **arXiv survey on LLM-as-judge (2025):** Multi-agent evaluation (multiple LLMs debating to reach consensus) reduces judge disagreement with human judgment from 31% (single judge) to 3%. Single LLM judges carry inherent biases toward certain writing styles and content types. — [arxiv.org/abs/2508.02994](https://arxiv.org/abs/2508.02994)
- **Google Cloud Vertex AI (Jan 2025):** Offers six trajectory evaluation metrics: exact match, tool call accuracy, trajectory length efficiency, hallucination rate, safety score, and task completion rate. Positions trajectory evaluation as the standard for agentic system assessment. — [cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service](https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service)

## Gotchas

- **Outcome metrics can be gamed.** A model can achieve a high success rate by lucky coincidence — selecting the right tool for the wrong reason, or stumbling to the right answer through a flawed process. Always pair outcome scores with trajectory analysis.
- **LLM judges need calibration before scale.** Without validation against human-labeled samples, LLM-as-judge introduces systematic bias. Run calibration on a small labeled set first; only scale after confirming correlation.
- **Production monitoring without alerting is passive.** Sampling 10% of production outputs is necessary but insufficient. The 90% you don't review can still fail. Build automated quality flags on the full traffic stream and use sampling for depth, not breadth.
- **Cost tracking is often missing from eval frameworks.** Most eval tutorials focus on quality. In practice, an eval that passes but costs 100× expected is a production failure. Treat cost-per-task as a first-class eval metric.
- **Static benchmarks go stale.** Models update. Evals that were accurate six months ago may no longer reflect current behavior. Treat your eval suite as a living artifact that requires regular maintenance and re-baselining.
