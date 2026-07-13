# S-1044 · The Trajectory Eval Stack — When Your Agent Looks Accurate But Fails in Production

Your agent scores 94% on your held-out test set. It also silently loops on 15% of support tickets, fabricates tool arguments on 8%, and returns wrong numbers to users who don't know better. Your final-answer accuracy metric showed green. Your users see red. The problem is that evaluating the last token of a trajectory tells you nothing about the 47 tokens before it. You need a trajectory eval stack.

## Forces

- **Per-step success compounds multiplicatively.** 95% accuracy × 8 steps = ~66% end-to-end. If you only measure the final answer, you miss the 34% that already failed on step 3.
- **Offline evals and online evals answer different questions.** Offline tests gate pre-deploy changes ("should I ship this?"). Online monitoring catches production drift ("is the agent still healthy?"). Teams conflating them ship regressions silently or pull the lever on phantom alarms.
- **Final-answer pass/fail hides which dimension broke.** A task that completed the wrong way still "passes" if the answer looks plausible. Per-dimension scoring tells you whether the tool selection failed versus the error recovery versus the reasoning.
- **LLM-as-judge is useful but gameable.** A judge model that only sees the final output produces thin signals. Agent-as-a-judge — which sees intermediate states, tool payloads, and loop counts — achieves parity with human evaluators on code tasks while remaining cheaper than human-in-the-loop.

## The move

Build a three-layer eval harness: **final-answer layer**, **trajectory layer**, **per-turn layer**. Instrument all three as gates in CI and as monitors in production.

**Layer 1 — Final-answer eval (output correctness):**
- Deterministic checks: exact match, JSON schema validation, code compilation, test run pass/fail
- LLM-as-judge for subjective criteria: coherence, tone, relevance (use a different model than the agent under test)
- Threshold-based gate in CI: block deploy if success rate drops below threshold across N runs

**Layer 2 — Trajectory eval (path quality):**
- Tool call sequence accuracy: did the agent call the right tools in the right order?
- Plan coherence: no loops, no dead ends, no premature finalization, right depth
- Error recovery: did the agent retry, fall back, or escalate when a tool failed?
- Trajectory efficiency: number of steps vs. a reference minimum — excessive steps signal looping or thrashing
- Use Agent-as-a-judge when trajectories are complex: the judge agent sees intermediate states and produces richer scores than a final-output judge

**Layer 3 — Per-turn eval (component-level regression):**
- Per-turn classifiers on retrieval quality, tool selection, argument extraction, result utilization
- Latency and cost tracking per turn to catch regressions that inflate token spend
- Labeled per-turn data feeds back into the offline eval corpus — corrections made in production become regression cases in the next deploy
- Keep per-turn eval under 90ms per instance (one forward pass on a purpose-built small model) to enable continuous monitoring without cost blowout

**Offline + Online in a single pipeline:**
- Offline: curated golden dataset, run pre-deploy, block on threshold — answers "should I ship?"
- Online: production traces fed into eval pipeline, statistical process control on success rate and per-dimension scores — answers "is it still healthy?"

**Practical thresholds (baseline, adjust to your domain):**
- Task completion rate: >85% pass
- Tool selection accuracy: >90% correct tool, correct arguments
- Error recovery rate: >75% (agent correctly handles at least one failure mode)
- Retrieval precision: >0.80 (top chunks are the most relevant)
- Retrieval recall: >0.90 (all available relevant info retrieved)

## Evidence

- **Blog post:** Future AGI's "The Definitive Guide to AI Agent Evaluation (2026)" formalizes the multiplicative per-step compounding insight — 95% × 8 = ~66% end-to-end — and maps six eval dimensions (tool selection, argument extraction, result utilization, error recovery, plan coherence, task completion) with failure-mode descriptions for each. — [https://futureagi.com/blog/definitive-guide-ai-agent-evaluation-2026](https://futureagi.com/blog/definitive-guide-ai-agent-evaluation-2026)

- **arXiv paper:** "When AIs Judge AIs: The Rise of Agent-as-a-Judge Evaluation" (arXiv:2508.02994v1) reports that agent-as-a-judge — which evaluates intermediate states across a trajectory — dramatically outperforms standard LLM-as-a-judge on code tasks and achieves parity with human evaluators. Key finding: agent judges that only see final outputs produce meaningfully weaker signals than those with access to intermediate tool payloads and step counts. — [https://arxiv.org/html/2508.02994v1](https://arxiv.org/html/2508.02994v1)

- **Technical guide:** Langfuse's agent eval cookbook documents trajectory-level metrics (tool call sequence accuracy, plan adherence) alongside practical implementation patterns using LLM-as-a-judge for black-box eval, noting that evaluating the trajectory — not the response — is the core architectural difference from plain LLM eval. — [https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)

- **Benchmark analysis:** Benchmarking Agents' survey of SWE-Bench, WebArena, AgentBench, and OSWorld notes that solution leakage (tasks in training data), high variance without confidence intervals, and a structural benchmark-to-production gap mean agent benchmarks serve as floor tests, not capability certificates. A 70% SWE-Bench Verified score does not mean 70% of real software engineering tasks will succeed. — [https://benchmarkingagents.com/agent-benchmarks/](https://benchmarkingagents.com/agent-benchmarks/)

- **HN Show HN:** "Agent Red Team" (HN post, mid-2025) surfaces deterministic validation as a design principle — the red-team pipeline rejects findings that cannot cite evidence from the artifact, and the validator is deterministic code, not LLM judgment. Fails closed on ambiguity. — [https://news.ycombinator.com/item?id=47581993](https://news.ycombinator.com/item?id=47581993)

## Gotchas

- **Don't measure task completion without measuring why it succeeded or failed.** An 87% completion rate tells you nothing about whether the agent is looping on the 13% and getting lucky on the 87%. Per-dimension scoring is the diagnostic.
- **Don't use the same model as both agent and judge.** Model judges favor model outputs — they rate hallucinations as coherent at a rate that human evaluators don't. Use a separate judge model or deterministic code wherever possible.
- **Offline eval sets go stale.** Production data drifts. If you never refresh your golden dataset, your eval will pass while users are seeing degradation. Budget time to label new failure cases and add them to the corpus.
- **Aggregate success rates mask hidden failure modes.** If tool selection accuracy drops 5% but task completion stays flat (because error recovery masks it), you will not catch the regression until error recovery also degrades. Monitor per-dimension scores independently.
- **Benchmarks are not your production test set.** SWE-Bench Verified covers 12 Python repos. Real engineering teams have Django, Terraform, legacy PL/SQL, and domain-specific tooling. Use benchmarks to catch regressions in foundational capability; use your own golden dataset for domain-relevant coverage.
