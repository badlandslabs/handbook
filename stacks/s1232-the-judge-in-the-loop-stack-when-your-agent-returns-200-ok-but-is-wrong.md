# S-1232 · The Judge-in-the-Loop Stack

[Your agent's last 200 runs all returned HTTP 200. Your monitoring shows no errors. You feel confident. Then you spot-check the outputs: it has been routing complex billing disputes to the wrong team for three days. The agent never crashed. It just quietly got worse, invisibly, at scale.]

## Forces

- **Agents fail sideways, not forward.** Unlike traditional software that crashes with an exception, agents return 200 OK with plausible-but-wrong answers. A misclassification costs you nothing in error rate and everything in correctness.
- **Static eval suites are snapshots, not surveillance.** A CI gate tests against a fixed golden dataset. It cannot detect behavioral drift on your real traffic distribution, edge cases that never made the eval set, or slow regression under live conditions.
- **Task-completion scores lie.** The benchmark crisis research (Berkeley, 2025-2026) shows a 37% performance gap between lab scores and production outcomes. Agents ace the happy path and silently decay on constraints and edge cases.
- **Rule-based evals can't judge nuance.** Hallucination, tone, relevance, and contextual appropriateness require judgment that regex and exact-match cannot provide.
- **Cost and latency make per-call judge LLMs impractical at scale.** Running GPT-4o as a judge on every agent step is expensive and slow. The economics need to work.

## The Move

Use LLM-as-judge as load-bearing production infrastructure — not just an eval harness. The key decisions:

- **Deploy judge checks at three boundaries.** Gate before user-facing output (is this answer safe and grounded?), before irreversible actions (should this email actually be sent?), and before cross-system tool calls (is this API call correctly formed?).
- **Distill the judge for economics.** Small distilled models (3B–8B parameters) achieve 0.88–0.95 accuracy as judges at 97% cost reduction versus GPT-4o. Build a task-specific judge rather than using the same model for generation and judgment. Classifying quality is simpler than generating it — smaller models reliably judge larger ones.
- **Separate trajectory evaluation from output evaluation.** Output quality asks "is this answer right?" Trajectory quality asks "did the agent take the right path?" Track both: a correct answer achieved via wrong tool-calling sequence is a regression waiting to happen.
- **Build a continuous eval pipeline, not a one-time CI gate.** Run offline evals on every commit (golden dataset, regression suite). Run online evals on a sample of live traffic. Feed production failures back into the eval dataset. The loop is the product.
- **Measure four dimensions in production.** Output quality (correctness, hallucination rate, groundedness), trajectory quality (tool call sequence, order, efficiency), latency and efficiency (p50/p95/p99, token consumption), and safety/guardrails (policy violations, escalation rate).
- **Use human-in-the-loop as a judge-labeling path.** For high-stakes outputs, queue the agent's decision and have a human label whether it was correct. Use those labels to fine-tune or RLHF the judge model over time.

## Evidence

- **Research report (Zylos, 2026-04-10):** 57%+ of production agent teams now rely on judge LLMs at runtime. Six distinct patterns: offline eval, online runtime verifier, self-consistency loops, Reflexion/reflection, constitutional AI/RLAIF, and inference-time reward models. Small distilled judges (3B–8B) achieve 0.88–0.95 accuracy at 97% cost reduction vs. GPT-4o. — [https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)
- **Research report (Zylos, 2026-05-13):** Berkeley examined eight prominent AI agent benchmarks (SWE-bench, WebArena, GAIA, etc.) and found 37% average performance gap between lab scores and production outcomes, with 50x cost variation for equivalent accuracy across agent configurations. Dynamic, adversarial, multi-dimensional evaluation is replacing static task-completion scoring. — [https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **Technical guide (RPABotsWorld, 2026):** Four dimensions of agent quality: output quality (correctness, relevance, completeness, hallucination), trajectory quality (tool call sequence, order, efficiency), latency/efficiency (p50/p95/p99, token consumption), and safety/guardrails. LangSmith integration for continuous monitoring with the feedback loop: production failures → dataset gold. — [https://rpabotsworld.com/agent-quality-evaluation-llm-as-judge-langsmith/](https://rpabotsworld.com/agent-quality-evaluation-llm-as-judge-langsmith/)

## Gotchas

- **Judging too late is useless.** If your judge runs only at deploy time and not in production, it catches regressions weeks after they reach users. Inline runtime verification catches failures at the point of impact.
- **Ungrounded self-correction degrades performance.** Reflexion-style agents that correct themselves without external grounding tend to amplify errors. Corrections must be anchored to verified external signals, not just model confidence.
- **Eval contamination at scale.** Static golden datasets get memorized. Rotate test sets, use procedural generation, maintain private held-out sets, or use live environment evaluation. The benchmark crisis is real — your eval suite is probably already lying to you.
- **Measuring trajectory is harder than measuring output, but more valuable.** You can LLM-judge a final answer in one call. Understanding whether the agent's 15-tool-call sequence was efficient and correct requires structured trace analysis and intent-replay. Skip this and you'll ship agents that happen to work, not agents that work for the right reasons.
