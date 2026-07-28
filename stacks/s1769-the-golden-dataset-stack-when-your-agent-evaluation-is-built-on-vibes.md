# S-1769 · The Golden-Dataset Stack

When your "eval suite" is an engineer saying "feels about right" after a prompt change — and you have no idea if that 95% pass rate on your last run means anything.

## Forces

- **Agents are non-deterministic.** The same input can produce different trajectories on different runs. A single pass/fail test tells you almost nothing.
- **The black-box trap.** Traditional LLM evals measure only the final answer. For agents, the entire execution path — tool calls, intermediate decisions, recovery behavior — is where failures live.
- **Coverage vs. cost.** A 500-case golden set catches more, but labeling it requires domain experts who cost more than the engineers building the agent.
- **The regression problem.** You ship a prompt change. Output quality drops silently. Users complain three weeks later. By then you don't know what caused it.
- **Eval is an afterthought.** Most teams build evals after the agent is "done." This means the golden dataset reflects what they thought mattered, not what actually broke in production.

## The move

Build a layered evaluation pipeline anchored on a versioned golden dataset, not vibes.

**Step 1 — Harvest from production, not imagination.** Start your golden dataset from real failure cases: queries that confused the agent, wrong tool calls, hallucinations caught by users, tasks that required retries. These are the cases that actually represent your agent's failure modes. Synthetic cases can supplement but should never lead.

**Step 2 — Score at three granularities, not one.** Single output scores miss most failures. Amazon's agent teams evaluate at three layers: *system efficiency* (latency, tokens, tool-call count), *trajectory quality* (did the agent take a reasonable path, not just a correct one), and *node-level precision* (did each tool call make sense given the state). Each layer has different pass thresholds.

**Step 3 — Use LLM-as-judge for nuanced qualities, code for deterministic ones.** Code-based scorers check: exact-match outputs, JSON schema validity, function call signatures, database consistency. LLM-as-judge handles: tone, relevance, whether the agent's reasoning was sound, whether it asked for clarification when it should have. Combining them avoids both the brittleness of pure exact-match and the drift of pure LLM scoring.

**Step 4 — Build a CI regression gate, not a dashboard.** A gate fails the build when score drops below threshold after any change. The key is defining the threshold in terms of business impact, not benchmark percentage. A drop from 89% to 87% might mean nothing — or it might mean 40 more failed compliance checks per day. Know which before setting the bar.

**Step 5 — Version your dataset like code.** A golden dataset without versioning is a moving target. Case IDs, expected trajectories, and scoring rubrics must be immutable once a version is tagged. The diff between dataset versions should be reviewed the same way a code diff is — because the dataset *is* a specification of what your agent should do.

## Evidence

- **AWS ML Blog:** Amazon evaluated thousands of agents across orgs and found traditional black-box LLM evals failed to determine *why* agents fail — only trajectory-level analysis (tracing every tool call, state transition, and decision point) enabled root-cause diagnosis. Single-turn accuracy metrics correlated poorly with real-world task success. — [AWS ML Blog, Feb 2026](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **InfoQ:** Agents require hybrid evaluation combining LLM-as-judge, trace analysis, and human judgment. Single-turn accuracy metrics (BLEU, ROUGE) don't capture multi-turn planning, tool calling, state maintenance, or recovery behavior. Behavior — task success, graceful recovery, consistency under variability — matters more than curated test-set scores. — [InfoQ, Mar 2026](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

- **GitHub (jbelnick/llm-judge-evals):** A production eval harness demonstrates the approach: hand-labeled golden dataset + deterministic fidelity scorers + rubric-anchored LLM judge with code-enforced guardrails = CI regression gate that fails when a model swap silently degrades output quality. The README includes a `make drift` command that deliberately triggers gate failure to prove the system catches regressions. — [jbelnick/llm-judge-evals, Jun 2026](https://github.com/jbelnick/llm-judge-evals)

- **Confident AI (YC W25):** Their open-source DeepEval package runs 600K+ evaluations daily in CI/CD pipelines for enterprises including BCG, AstraZeneca, AXA, and Capgemini. Core pattern: production traces → test cases → automated evals → regression detection. Data + task + scorers is the unit structure. — [HN Launch, 2025](https://news.ycombinator.com/item?id=43116633)

- **Langfuse/LangSmith:** Trajectory evaluation — hard-coding a reference trajectory for a given input and validating the run step-by-step — is the recommended approach for well-defined agent workflows where expected tool-calling sequence is known. Traces can be re-scored against updated rubrics without re-running the agent. — [LangSmith Docs](https://docs.langchain.com/langsmith/trajectory-evals), [Langfuse Guide](https://langfuse.com/resources/engineering/ai-agent-evaluation)

## Gotchas

- **Benchmarks lie.** A 94% score on a curated eval dataset means the agent can pass your test, not that it works in production. Evaluate on cases you actually saw fail.
- **LLM-as-judge drifts.** An LLM judge evaluated by another LLM can form a confidence loop. Guard it with deterministic code checks on structural properties (schema validity, required fields, value ranges) — these can't be gamed by the judge.
- **Golden sets rot.** Without continuous curation from production failures, the dataset becomes a best-case snapshot. Every new failure in production should spawn a new golden case. If your last eval run had zero failures, your dataset is stale.
- **Node-level scores can be high while trajectory fails.** An agent that calls the right tools but in the wrong order, or makes a good call for the wrong reason, will score well at node level and fail at session level. Always evaluate both — trajectory quality is not the sum of step quality.
