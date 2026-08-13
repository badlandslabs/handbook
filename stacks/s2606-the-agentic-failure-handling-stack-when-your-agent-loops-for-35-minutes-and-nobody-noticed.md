# S-2606 · The Agentic Failure Handling Stack — When Your Agent Loops for 35 Minutes and Nobody Noticed

Your agent starts a task at 2 AM. At 2:35 AM it is still running — not progressing, not erroring, just looping. No exception was raised. No alert fired. The database is now in an inconsistent state from three intermediate actions it took before entering the loop. A traditional web service would have crashed with a stack trace. An agent fails silently, expansively, and often irreversibly.

## Forces

- Agents introduce a **hybrid failure mode** — not purely software (deterministic, catchable) and not purely probabilistic (random, acceptable). Failures are structured but unpredictable in their specifics.
- Traditional error handling (try/catch, HTTP error codes) **catches the wrong thing** — it catches tool failures but not reasoning failures, where the agent chose the wrong path.
- Standard metrics (ROUGE, BERTScore, accuracy) **miss 4 of 7 production failure modes entirely** and detect the other 3 only after multiple evaluation cycles of lag.
- The failure distribution in multi-agent systems is roughly: ~42% specification failures (wrong goals), ~37% coordination breakdowns (agent-to-agent), ~21% verification gaps (no output check).
- Agents can accumulate context until the model halts, spawn redundant subprocesses, or take irreversible actions — **before a human can intervene**.

## The move

Build a layered failure architecture that combines conventional fault tolerance with agent-specific recovery patterns:

- **State checkpointing** — save agent state (context window snapshot, tool call history, intermediate decisions) at defined milestones. On failure, restore from the last checkpoint rather than replaying the entire session.
- **Step and loop budgets** — enforce hard limits on agent steps per task and total loop iterations. When the budget is exhausted, halt and escalate. Budgets are the only reliable guard against silent infinite loops.
- **Trajectory-based evaluation** — measure not just the final output but the quality of the full decision sequence. A held-out pass/fail can be green while the trajectory was a mess and three turns drifted off policy.
- **pass^k probability tracking** — measure the probability an agent succeeds on all k independent trials of the same task (p^k). An agent with 80% single-trial accuracy has only 17% probability of succeeding across 8 repeated runs. Production systems running the same task type repeatedly need this metric, not single-trial success rate.
- **Human-in-the-loop escalation gates** — before any action classified as irreversible (financial transactions, data deletions, external API writes with side effects), require explicit human confirmation. Agents that auto-escalate on uncertainty reduce irreversible damage.
- **Continuous production traffic evaluation** — don't evaluate on episodic benchmarks. Run evaluation on live production traffic alongside the agent, catching drift and degradation as it happens rather than in the next scheduled test run.

## Evidence

- **arXiv taxonomy study:** Analysis of 13,602 closed issues and merged PRs across 40 open-source agentic AI repos identified that 83.8% of practitioners reported the failure taxonomy matched what they encountered in practice. Found that agent failures are structured and predictable, exhibiting a hybrid failure profile — not random, but not deterministic either. — [Characterizing Faults in Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes](https://arxiv.org/html/2603.06847v1) (Shah et al., arXiv:2603.06847v1, March 2026, JACM)

- **Production failure distribution:** Multi-agent production deployments studied by Galileo in 2025 found specification failures account for ~42% of failures, coordination breakdowns ~37%, and verification gaps ~21%. 40%+ of Gartner-graded agentic AI projects will be cancelled by end of 2027 without proper controls. — [AI Agent Self-Healing and Failure Recovery](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery) (Zylos Research, 2026-05-06)

- **Eval framework gap:** Standard benchmarks (HELM, MT-Bench, AgentBench, BIG-bench) designed for controlled single-session settings fail to detect 4 of 7 production failure modes entirely. Their state-based evaluation misses cascading decision errors, tool failure propagation, and non-deterministic output drift that only emerge under continuous production operation. — [Evaluating Agentic AI in the Wild](https://arxiv.org/abs/2605.01604) (Pandey, arXiv:2605.01604, May 2026)

- **Benchmark crisis:** Static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. Six metrics carry most of the weight: task completion/success rate, tool-call accuracy, step/loop count, policy adherence (off-policy rate), cost per session, and answer faithfulness. — [AI Agent Evaluation: Metrics, Frameworks, and Production Failures](https://www.morphllm.com/ai-agent-evaluation) (MorphLLM, 2026)

## Gotchas

- **Catching tool errors is not failure handling** — wrapping an API call in a try/catch catches the symptom, not the reasoning failure that chose the wrong tool or arguments in the first place. Both layers are needed.
- **A green benchmark does not mean a reliable production agent** — lab benchmarks test isolated capability, not system behavior under real conditions. 88% of AI proofs-of-concept never reach production (IDC, 2025).
- **Checkpoint frequency is a trade-off** — too frequent and you add latency; too sparse and recovery replays too much work. Milestone-based checkpoints (after each major tool call or decision branch) are a common middle ground.
- **Budget limits prevent loops but don't diagnose them** — a step budget halts a looping agent but provides no signal about *why* it looped. Combine budgets with logging that captures the decision history at each step so post-mortems can reconstruct the reasoning path.
