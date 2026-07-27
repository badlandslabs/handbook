# S-1719 · The Trajectory Divergence Stack — When Your Agent Succeeds on Paper and Fails in Practice

Your benchmark reports 87% accuracy. Your users report frustration. An agent called the right tools in the wrong order, got a correct-looking answer from stale model knowledge, and failed silently. The benchmark measured the destination. Production measured everything else. This gap between trajectory quality and outcome quality is why most agent teams cannot explain their failure modes — and why evaluation has become the defining unsolved problem of production agentics.

## Forces

- **Outcome and trajectory are not the same signal.** An agent can reach a correct answer through broken reasoning, or fail to reach one despite sound reasoning. Benchmarks that score only outcomes miss the broken-reasoning case entirely — and that case is where silent failures, hallucinated justifications, and credential misuse hide.
- **Human eval doesn't scale; automated eval misses nuance.** The MAP study (86 deployed agents, 306 practitioners, 26 domains, 2025) found 74% of production teams still primarily rely on human evaluation. Not because they prefer it — because they don't trust what automated evaluation tells them. But human reviewers cover only a fraction of production traffic, score inconsistently between reviewers, and cannot catch trajectory-level failures.
- **The six dimensions no single metric captures.** Real agent quality decomposes into: tool selection correctness, argument extraction (schema-valid ≠ semantically correct), result utilization (did the agent use the tool output or substitute model memory?), error recovery behavior, plan coherence (loop-free, dead-end-free), and end-to-end task completion. A pass/fail or even an accuracy percentage obscures all of these.
- **The variance tax.** Agents show high variance on the same task across identical inputs. A single trial is nearly meaningless. You need multiple trials, trajectory traces, and cross-dimension scoring to get a reliable signal.

## The Move

**Design your evaluation system as an agent itself — one that grades trajectories, not just outcomes.**

- **Decompose into six independent dimensions.** Score tool selection (right tool, or explicitly no tool), argument extraction (schema + semantics), result utilization (tool output used vs. model knowledge substituted), error recovery (retry / fall back / escalate on 4xx / timeout / empty result), plan coherence (loop-free, dead-end-free, right depth), and task completion. If your eval framework cannot score these separately, treat it as LLM eval, not agent eval.
- **Build a rubric that includes failure modes explicitly.** Reference trajectories — concrete examples of both successful and broken agent executions — teach the grader what each dimension looks like at each score level. Include explicit examples of the "correct answer from wrong reasoning" case.
- **Use Agent-as-a-Judge over LLM-as-a-Judge.** The Agent-as-a-Judge paradigm (Zhuge et al., ICML 2025) endows the evaluator with tool access, intermediate reasoning, and multi-step observation — mirroring the agents it judges. On the DevAI benchmark (55 realistic automated AI development tasks, 365 hierarchical requirements), Agent-as-a-Judge dramatically outperformed LLM-as-a-Judge and achieved parity with human evaluation reliability.
- **Calibrate before trusting.** Run LLM-as-judge or Agent-as-a-Judge against a labeled human-eval subset. Target ≥0.80 Spearman correlation with human judgment before using the scores to gate deployments or make architecture decisions. A judge that correlates at 0.55 is not a judge — it's noise.
- **Capture trajectory artifacts, not just outputs.** Log the full action sequence: tool calls, arguments, responses, decision points. Store these alongside outcome labels. Trajectory logs are what let you diagnose regressions when your agent's success rate drops — without them, you're guessing.
- **Run multi-trial evals.** Single-trial eval is nearly meaningless for agents. Run at least 3–5 trials per task and report distribution, not just mean. Report step-count variance and tool-call variance alongside pass rate.

## Evidence

- **Survey paper (MAP):** 74% of 86 production agent teams still primarily use human evaluation; 68% of agents execute ≤10 steps before human intervention; "increasing productivity" was the top motivation (73%) while "improving operational stability" was least selected (18.2%) — revealing that teams optimizing for throughput underinvest in reliability infrastructure. — [arXiv:2512.04123v1](https://arxiv.org/html/2512.04123v1)
- **ICML paper:** Agent-as-a-Judge on DevAI (55 tasks, 365 hierarchical requirements) dramatically outperformed LLM-as-a-Judge and matched human evaluation reliability for trajectory quality. The judge agent can observe intermediate steps, use tools, and provide granular feedback pinpointing which requirements were satisfied and which steps were efficient. — [ICML 2025 / arXiv:2410.10934](https://proceedings.mlr.press/v267/zhuge25a.html)
- **Framework comparison:** Future AGI (2026) surveyed six production eval frameworks and found most are "LLM eval with trajectory bolted on." The trajectory-first frameworks scored independently on tool selection F1 (with explicit irrelevance bucket), argument semantic validity, result utilization, error recovery, plan coherence, and end-to-end completion. — [Future AGI — Agent Evaluation Frameworks 2026](https://futureagi.com/blog/agent-evaluation-frameworks-2026)

## Gotchas

- **Training-data contamination distorts benchmark scores.** Agents can score well on WebArena, SWE-bench, or AgentBench but perform poorly in production if the benchmark tasks leaked into training data. Treat benchmark scores as a floor, not a ceiling.
- **Schema-valid arguments can be semantically wrong.** An agent may extract `departure_date="next Friday"` correctly against the schema while completely misunderstanding which Friday is meant. Your eval needs semantic validation, not just schema validation.
- **Result utilization failure is invisible without trajectory logs.** The agent calls a search tool, gets relevant results, then ignores them and answers from its parametric memory. Outcome eval sees a correct-looking answer. Trajectory eval sees the mismatch. You need the trace to catch this.
- **Calibration drift.** LLM judges are sensitive to prompt wording, temperature, and model version. Re-calibrate against your human-eval gold set whenever you swap the judge model or change the evaluation prompt. A judge that was 0.82 correlation last quarter may be 0.61 this quarter.
- **Human eval inconsistency is its own problem.** Different reviewers score the same trajectory differently, especially on "partial credit" dimensions like plan coherence. Use ≥3 reviewers per trajectory for gold-set construction and report inter-rater agreement.
