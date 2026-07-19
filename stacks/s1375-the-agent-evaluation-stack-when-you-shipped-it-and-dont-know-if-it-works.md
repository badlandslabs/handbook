# S-1375 · The Agent Evaluation Stack: When You Shipped It and Don't Know If It Works

You have a working agent in production. The LLM is fast enough, the tools are connected, and the happy path works. But you have no idea what breaks in the other 80% of cases. Every time someone reports a failure, you add a guardrail, re-run a few manual tests, and ship it again. This is not QA — it is guesswork with extra steps.

## Forces

- **Agents are non-deterministic while evals are designed for determinism.** A model can succeed or fail on the same input depending on temperature, context ordering, and latent tool state — making a single run meaningless.
- **Correct final outputs mask broken reasoning.** An agent can reach the right answer via hallucinated steps, missed tools, or wrong assumptions. Outcome grading alone misses this.
- **Benchmarks lie in production.** SWE-bench Verified scores do not translate to "this agent handles 70% of real engineering tasks" — the task distribution is completely different.
- **LLM judges echo the agent's blind spots.** The model evaluating your agent shares the same training data and failure modes as the model being evaluated.
- **Eval changes are downstream traps.** Any change to prompts, tools, or orchestration can shift scores — teams often don't realize a regression until it hits production.
- **Standard unit tests don't apply.** Agents are dynamic, context-dependent, and stateful. Asserting `function(a) == b` is useless for a system that reasons, calls tools, and mutates external state.

## The move

Grading agent quality requires layered evaluation across outcome, trajectory, and behavior — and accepting that no single metric tells the whole story.

**Layer 1 — Define success by task type first.** Before measuring, answer: what does a successful outcome look for this agent? A customer-support agent succeeds if the user's issue is resolved with a refund or workaround. A coding agent succeeds if the PR passes CI and the tests pass. A research agent succeeds if the summary is accurate and citations are real. Different agent types require fundamentally different success criteria. (Ashutosh Tripathi, Principal ML Engineer, Data Science Duniya, Dec 2025 — https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide/)

**Layer 2 — Grade outcome before trajectory.** Anthropic's evaluation framework separates the **task** (problem + success criteria), the **trial** (one stochastic attempt), the **agent harness** (the scaffold running the loop), and the **grader** (the scoring logic). Grade the task outcome first — did the agent achieve the goal? — then examine the transcript to understand *why*. A pass/fail on the outcome is the primary signal; the trace is diagnostic. (Anthropic Engineering Blog, Jan 2026 — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

**Layer 3 — Use pass@k and pass^k, not pass@1.** Because agents are non-deterministic, a single run is insufficient. `pass@k` measures the probability that at least one of k trials succeeds (useful for agents where retries are acceptable). `pass^k` measures the probability that all k trials succeed (useful for customer-facing agents where consistency is the product). With a 75% per-trial success rate and 3 trials, pass^3 drops to ~42% — a model that looks capable is actually unreliable. (Anthropic Engineering Blog, Jan 2026)

**Layer 4 — Combine deterministic checks with LLM judges.** Deterministic checks catch hard failures: did the tool receive the right arguments? Did the output conform to the schema? Was the correct API called? LLM judges evaluate qualitative dimensions: is the tone appropriate? Is the explanation clear? Is the reasoning coherent? Braintrust's framework calls these **scorers** — code functions for deterministic checks, LLM-as-judge for qualitative ones. Neither alone is sufficient. (Braintrust Blog, Jan 2025 — https://www.braintrust.dev/blog/evaluating-agents)

**Layer 5 — Sample human review periodically to calibrate.** The eval framework from aunhumano (Sep 2025) recommends starting with end-to-end evals that output a simple yes/no success value, then periodically doing blind human review of agent traces to catch issues that automated scorers miss. Braintrust echoes this: human review of transcripts is irreplaceable for identifying subtle failure modes like hallucinated citations or tool calls that never actually executed. (aunhumano, Sep 2025 — https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)

**Layer 6 — Use rolling benchmarks to avoid contamination.** Static benchmarks like SWE-bench are prone to training data leakage — models trained after task creation may have seen solutions in git history. The r/LocalLLaMA discussion proposes dynamic/rolling benchmarks: evaluate agents only on freshly published, never-before-seen code to prevent leaderboard hacking and get genuine capability signals. (r/LocalLLaMA discussion, remyxai, 2025 — https://www.reddit.com/r/LocalLLaMA/comments/1nmvw7a/)

**Layer 7 — Treat benchmarks as floor tests, not certificates.** BenchmarkingAgents.com (2026) notes that a 70% SWE-bench Verified score does not mean 70% of real engineering work is covered — the benchmark task distribution (12 Python repos, specific issue types) doesn't match a real engineering team's backlog. High scores are necessary but not sufficient. Use benchmarks to establish a minimum bar, then build domain-specific evals on top. (https://benchmarkingagents.com/agent-benchmarks)

**Layer 8 — Build evals from production logs, not assumptions.** The najeed/ai-agent-eval-harness framework (2025) includes an `import-drift` tool that converts production error logs into regression test cases. This grounds evals in real failure modes rather than hypothetical ones. AWS Labs' agent-evaluation framework similarly uses production-trajectory-based evaluation for Bedrock agents. (https://github.com/najeed/ai-agent-eval-harness, https://awslabs.github.io/agent-evaluation/)

## Evidence

- **Engineering blog (primary):** Anthropic published the most comprehensive treatment of agent eval structure (Jan 2026), establishing the task/trial/harness/grader taxonomy and pass@k vs pass^k metrics. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **HN discussion:** The HN thread "Evaluating Agents" (42 points, Sep 2025) surfaced the community consensus that human trace review is irreplaceable and that simple end-to-end pass/fail evals are the right starting point before adding sophistication. — https://news.ycombinator.com/item?id=45121547
- **HN discussion:** The HN thread "Why eval startups fail (2025)" (110 points) revealed that eval tool vendors struggle because eval design is domain-specific and cannot be commoditized — teams need custom scorers grounded in their actual product, not generic benchmarks. — https://news.ycombinator.com/item?id=48637868
- **GitHub repo:** AWS Labs' agent-evaluation framework (369 stars) provides an open-source harness specifically for Bedrock agents, with CI/CD integration for running eval suites on every change. — https://awslabs.github.io/agent-evaluation/
- **GitHub repo:** The ai-agent-eval-harness from najeed provides a multi-agent ops evaluation framework with spec-to-eval (converts Markdown PRDs into executable scenarios) and mutation testing for adversarial cases. — https://github.com/najeed/ai-agent-eval-harness
- **Blog:** Braintrust's guide (Jan 2025) maps practical scorer patterns — deterministic checks for tool calls, LLM judges for tone and coherence, cost/latency metrics for production health. — https://www.braintrust.dev/blog/evaluating-agents

## Gotchas

- **LLM-as-judge creates an echo chamber.** The same model evaluating your agent shares the blind spots of the model being evaluated. Calibrate judges against human-reviewed samples, not just against other LLM judgments.
- **One run is not a data point.** Non-determinism means a single success proves nothing. Always run k trials and report pass@k, not pass@1. A 90% pass@1 can mean 90% pass^k (exceptional) or 31% pass^3 (unreliable — 0.9^3 ≈ 0.73, so pass^3 ≈ 73%, actually not as bad as it sounds, but the principle stands).
- **Eval design is domain-specific.** Generic benchmarks miss your product's actual failure modes. The eval startups that failed did so because they offered generic tools; teams that succeed build custom evaluators grounded in real production traces.
- **Production log → eval case is the highest-leverage workflow.** Converting actual failures from production into regression test cases closes the feedback loop faster than any benchmark.
- **Soft failure thresholds belong in CI/CD.** Non-deterministic agents will occasionally fail even good implementations. A hard pass/fail in CI creates alert fatigue. Set soft thresholds — regression if pass@k drops by >5% — and surface the diffs for human review.
