# S-1501 · The Evaluation Gap Stack: When Your Agent Passed the Demo but Fails Production

Your agent nailed the demo. Your team signed off. Then production users started encountering a cascade of failures that no test caught — the wrong tool called 12% more often, a policy violation went undetected, a sub-task silently dropped mid-chain. Standard CI passed. The users noticed. This is the evaluation gap: the difference between testing what the agent can do and measuring whether it actually does it correctly in the wild.

## Forces

- **Offline evals are a snapshot, not a signal.** An offline suite captures the distribution of inputs you had when you wrote it. Production is a live distribution that shifts daily. Suits go stale the moment they ship — and teams lack the infrastructure to notice.
- **Trajectory failures are invisible to final-output evaluation.** A correct answer reached through two policy-violating intermediate calls scores fine if you only check the last message. The path is the risk.
- **Model updates and prompt changes silently degrade behavior.** Unlike traditional software, there are no compile errors — just degrading performance that users suffer through until someone notices or reports it.
- **Production per-turn evaluation requires a different infrastructure than CI.** Most eval frameworks (DeepEval, Promptfoo, LangSmith) score in batch/CI. None of the major tools classify per-turn failures in production at low enough latency to act on. This 90ms production layer is the actual failure surface.
- **88% of agent projects never reach production.** The average cost of a failed agent project is $340K. Four times better outcomes correlate with teams that build evaluation infrastructure first — not as an afterthought.

## The move

The move is a layered eval strategy: offline suites for regression gates + production trajectory monitoring for live failure detection + a human-in-the-loop annotation pipeline to close the loop. Three layers, each catching what the others miss.

- **Layer 1 — Offline eval suite in CI:** Run agents against fixed datasets before every deploy. Score on task completion rate, answer correctness, and tool-call accuracy. Use DeepEval (open-source, pytest-native) for code-first teams, Promptfoo (CLI, free) for lightweight suites, or Braintrust for dataset + CI gate combos. Catch regressions on known cases.
- **Layer 2 — Trajectory scoring, not just output scoring:** Score the full reasoning/action chain, not just the final message. A correct answer reached through a policy-violating intermediate call should fail. Use LLM-as-judge for scoring intermediate steps, or tag critical checkpoints (e.g., "before calling delete API," "before sending email") and score each checkpoint independently.
- **Layer 3 — Production monitoring with online evaluation:** Instrument the live agent to score a sample of production traces. Score at the turn level: was the right tool selected? Did the tool call succeed? Did the response stay within policy? Route failures to a human annotation queue for root-cause analysis. This closes the staleness problem — your eval suite now tracks what production actually looks like.
- **Layer 4 — Eval-as-data pipeline:** Treat every production failure as a new test case. Annotate it, add it to the offline suite, and regression-test it on the next deploy. This creates an eval suite that grows with production experience rather than decaying.
- **Separate quality from safety gates:** Quality gates (task completion, correctness) and safety gates (policy compliance, PII handling, permission boundaries) operate at different thresholds. Safety failures should halt promotion; quality regressions should require human review. Don't conflate them.
- **Measure what drives cost, not just accuracy:** Token usage per query, p95 response latency, and cost per task are first-class eval targets. An agent that's 95% accurate at 3x the expected cost is a production failure.

## Evidence

- **Survey (Cleanlab, August 2025):** Out of 1,837 engineering and AI leaders surveyed, only 95 had AI agents live in production. Among those, fewer than 1 in 3 were satisfied with their observability and guardrail solutions. 63% plan to improve evaluation and monitoring in the next year. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025/)
- **Analysis (Digital Applied, March 2026):** 88% of AI agent projects never reach production. The average cost of a failed agent project is $340K. Teams with formal evaluation frameworks report 4x better outcomes. The core finding: "The failure is almost entirely in the surrounding systems — the scoping, the data infrastructure, the security architecture, and the integration approach." — [digitalapplied.com/blog/88-percent-ai-agents-never-reach-production-failure-framework](https://www.digitalapplied.com/blog/88-percent-ai-agents-never-reach-production-failure-framework)
- **YC State of AI Agents 2026 (reported via MorphLLM):** A super-majority of YC agent builders report that evaluations under-deliver because keeping offline suites current becomes an impossible task. — [morphllm.com/ai-agent-evaluation-frameworks](https://www.morphllm.com/ai-agent-evaluation-frameworks)
- **Microsoft CI/CD Reference (Azure Foundry, 2026):** Production agent pipelines should gate promotion on evaluation scores across four dimensions: quality (task completion rate, hallucination rate), safety (policy compliance, tool usage validation), performance (token usage per query, p95 latency), and cost. Promotion happens at the immutable agent version level. — [techcommunity.microsoft.com/blog/educatordeveloperblog/cicd-for-ai-agents-on-microsoft-foundry/4522218](https://techcommunity.microsoft.com/blog/educatordeveloperblog/cicd-for-ai-agents-on-microsoft-foundry/4522218)

## Gotchas

- **Final-output evaluation misses the most dangerous failures.** If you only check whether the final answer is correct, you miss policy-violating intermediate actions, unnecessary tool calls, and hallucinated reasoning steps. Score trajectories.
- **Offline suites go stale within weeks.** Production traffic changes daily. An eval suite that isn't fed new production failures becomes a false confidence signal. Build the annotation pipeline first, then the CI gate.
- **Eval quality gates that are too strict halt all shipping.** Teams that set 100% correctness thresholds end up circumventing the gates entirely. Set tiered thresholds: safety failures = hard halt; quality regressions = human review; performance regressions = alert.
- **LLM-as-judge is convenient but biased.** Models favor verbose responses and are susceptible to position effects and self-preference. Calibrate judge prompts, run human spot-checks on judge outputs, and never use an LLM judge to evaluate safety-critical decisions without human review.
- **Silent degradation is the default failure mode.** Unlike traditional software, agents don't throw exceptions when they degrade. Set automated alerts on trajectory-level metrics (tool call accuracy, policy violation rate, task completion rate) in production — not just on the final output quality score.
