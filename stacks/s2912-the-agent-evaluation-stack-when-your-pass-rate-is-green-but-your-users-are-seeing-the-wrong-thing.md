# S-2912 · The Agent Evaluation Stack

When your agent has a 94% pass rate but 30% of production sessions are silently producing wrong output via broken reasoning paths — and you have no way to tell which sessions. The fix is a three-layer eval architecture: outcome, trajectory, and per-turn scoring. Without it, you're shipping blind.

## Forces

- **Final-answer pass/fail is a lie.** The agent can produce the right output via a catastrophically wrong reasoning path, or produce the wrong output via a near-perfect reasoning path. A held-out pass/fail score hides both failure modes.
- **Benchmarks are being gamed.** UC Berkeley's RDI showed all 8 major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) can be exploited to near-100% scores without solving a single real task. One team gamed 890 SWE-bench tasks with a single character change. Your internal benchmark is probably being gamed too.
- **Constraint decay kills production agents.** Research on LLM coding agents (arXiv:2605.06445, 287 HN points) shows an average 30-point drop in assertion pass rates when agents must satisfy both behavioral correctness AND architectural constraints. Agents ace demos (unconstrained) but fail silently in production (constrained) — yet most teams only evaluate against unconstrained test cases.
- **Eval vs. observability are different procurement decisions.** The four credible 2026 eval platforms (DeepEval, Braintrust, LangSmith, Patronus) split along this axis. Treating them as interchangeable tooling produces the wrong investment for most teams.

## The move

**Layer your evaluation across three dimensions — outcome, trajectory, and per-turn — and gate releases on all three.**

### Layer 1: Final-Answer Outcome Scoring
- Define explicit pass/fail criteria per task type (exact match for code execution, semantic similarity for text, tool-call success for agent tasks).
- Use task-specific graders rather than generic rubrics. A code agent grader checks `assert` pass rates, not "does the code look reasonable."
- Run multiple trials per task (3–5) to account for output variance; report both mean and distribution.

### Layer 2: Trajectory Evaluation
- Capture the full span tree: every tool call, intermediate result, retry, and recovery event.
- Score on: tool selection correctness, call ordering, unnecessary detour frequency, and recovery from errors.
- Trajectory costs real money. A 20-step detour on a $0.01/tokens model might be fine; on a $3/tokens frontier model it demands architectural fixes.
- Set hard step-count budgets per task type and fail trajectories that exceed them, regardless of outcome correctness.

### Layer 3: Per-Turn Labeling
- Label each step as: `correct`, `inefficient`, `hallucinated`, or `unsafe`.
- Hallucinated steps are especially critical: the agent calls a tool that doesn't exist, or interprets a rate-limit response as valid data, then compounds the error across downstream steps.
- Per-turn labels feed fine-tuning pipelines and RL reward models — they are the raw signal for improving the agent over time.

### The Eval Stack in Practice
- **Open-source pytest-native:** DeepEval — runs like unit tests, integrates into CI/CD, 20+ built-in metrics, synthetic test generation. Best for teams that want control and no recurring SaaS cost.
- **SaaS eval primitives:** Braintrust — lightweight API-first eval layer, good for teams with existing infra. Best for teams that want fast iteration without self-hosting.
- **LangChain-stack bundle:** LangSmith — eval attached to full observability. Best for teams already deep in the LangChain ecosystem.
- **Use two tools:** one CLI/library for eval computation + one hosted dashboard for trace review. Most teams end up here regardless of starting point.

### Build the Golden Dataset
- **Source 1: Production captures.** LangSmith and similar tools let you tag successful production sessions and promote them to test cases. This is the highest-quality signal because it's real user behavior.
- **Source 2: Synthetic augmentation.** Generate edge-case variations with an LLM, then review each manually before adding. Unreviewed synthetic items dilute the trust that makes a dataset golden.
- **Source 3: Adversarial test cases.** Specifically target known failure modes — constraint violations, tool schema drift, rate-limit responses, empty context windows.
- Version the dataset. Eval runs against a specific version. Pin it.

### CI/CD Regression Gates
- Run the full eval suite on every PR. A prompt change or model upgrade that passes held-out tests but fails regression is a revert signal, not a merge signal.
- Track eval pass rate as a trend, not a threshold. A 2% drop across 200 test cases over a week is a conversation; a single 80% threshold flip is too late.
- Run offline evals as release gates, online evals on production traffic for continuous monitoring.

## Evidence

- **HN / arXiv (287 points):** Constraint Decay paper (arXiv:2605.06445) — 8 web frameworks tested, 30-point average drop in assertion pass rate when structural constraints enforced. HN thread with 197 comments confirming the pattern in real agent deployments. — [https://news.ycombinator.com/item?id=48256912](https://news.ycombinator.com/item?id=48256912)
- **Research post:** Berkeley RDI "How We Broke Top AI Agent Benchmarks" (April 2026) — systematic exploitation of 8 benchmarks showing near-perfect scores achievable without task-solving; one exploit used a single character change across 890 tasks. — [https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/)
- **Company engineering post:** Anthropic "Demystifying Evals for AI Agents" — three-layer eval structure (task/trial/grader), explicit recommendation to evaluate trajectory quality alongside outcome correctness. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Company engineering post:** Amazon "Evaluating AI Agents: Real-World Lessons from Building Agentic Systems at Amazon" (2026) — thousands of agents built across orgs, framework for evaluating emergent system behavior: tool selection accuracy, reasoning coherence, memory retrieval quality, task completion. — [https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Industry analysis:** AgentMode AI AM-122 (May 2026) — framework comparison: DeepEval (open-source pytest-native), Braintrust (SaaS eval primitives), LangSmith (LangChain-stack observability+eval), Patronus (pivoted from hallucination to digital-world-model). Core thesis: eval vs. observability is the load-bearing distinction. — [https://agentmodeai.com/agent-eval-frameworks-deepeval-braintrust-langsmith-patronus/](https://agentmodeai.com/agent-eval-frameworks-deepeval-braintrust-langsmith-patronus/)
- **Technical blog:** NVIDIA "Mastering Agentic Techniques: AI Agent Evaluation" (May 2026) — four eval dimensions: task success rate, trajectory visibility, tool usage quality, reasoning efficiency. Distinction between model evaluation (static benchmarks, "is the engine powerful?") and agent evaluation (dynamic workflows, "can the system execute reliably?"). — [https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)

## Gotchas

- **Don't evaluate only on final-answer pass rate.** The trajectory tells you what the agent actually did. A green pass rate with a broken reasoning path means your next model upgrade will fail in ways you can't predict.
- **Don't skip the step-count budget.** If the agent needs 47 tool calls to accomplish what a competent agent does in 6, you're burning money and your users are waiting. Step budgets catch this; outcome-only evals miss it.
- **Don't use unreviewed synthetic test cases as your only coverage.** Synthetic variations of known-hard inputs are useful for filling gaps, but they carry the biases of the generator. Always mix in production-captured cases and human-reviewed items.
- **Don't treat benchmarks as ground truth.** The Berkeley RDI finding that all 8 major benchmarks can be gamed with zero capability means your benchmark score is a weak signal until validated against production behavior. Use benchmarks as a sanity check, not a release gate.
- **Don't merge without eval regression running.** A prompt tweak that "feels better" and passes your held-out set but fails 12 regression cases is a revert. Ship the revert, not the feeling.
