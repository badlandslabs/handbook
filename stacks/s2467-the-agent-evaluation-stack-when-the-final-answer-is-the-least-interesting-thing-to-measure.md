# S-2467 · The Agent Evaluation Stack — When the Final Answer Is the Least Interesting Thing to Measure

Your agent passed every test. Correct final output. Clean logs. Then it took 47 tool calls to do what a human would do in 3, hallucinated a reasoning step in the middle that went undetected, and called a deprecated API that happened to still work. Your evaluation suite passed. Production didn't.

The core problem isn't measuring text quality — it's measuring whether an agent actually works: task completion, tool selection, reasoning fidelity, and failure recovery. No single metric covers it. Most teams start with one approach and miss the rest.

## Forces

- **Unit tests can't stub an LLM.** Traditional mocks return canned strings; the real agent might call three tools in an order your mock never anticipated. You can't assert on execution traces.
- **The input space is infinite.** Production exposes agents to distributions no synthetic test suite can anticipate. Handcrafted test cases cover happy paths; real failures live in the edges.
- **The judge has biases.** LLM-as-judge scales but systematically prefers longer answers, inflates scores on later-presented options (position bias), and struggles with numeric ranges. A naively configured judge produces opposite conclusions from a calibrated one.
- **Trajectories matter as much as outcomes.** Two agents produce the same correct answer — one in 3 steps, one in 47. Measuring only the final output misses cost, efficiency, and reasoning quality entirely.
- **Regression in production is silent.** Agents degrade gradually as model versions shift, prompts drift, or upstream APIs change. Without systematic evals, you discover failure only when users complain.

## The Move

Build a layered evaluation system where each layer uses the right measurement instrument for what it's checking.

**Layer 1 — Unit: Isolate and mock the LLM boundary.**
Push LLM calls behind interfaces so deterministic components (routing logic, tool selection, state transitions) can be unit tested with mock returns. These tests are fast, reproducible, and cover the logic you own. They cannot evaluate the LLM itself, but they catch regressions in the scaffolding.

**Layer 2 — Integration: Does the tool chain fire correctly?**
Test whether the agent calls the right tools in response to a given context, without asserting a fixed order. Use deterministic tool-call extractors to verify presence of expected invocations. This layer catches broken tool definitions, schema mismatches, and routing errors.

**Layer 3 — Trajectory: How did it reason, not just what did it output?**
Evaluate the full execution path — number of steps, tool call efficiency, hallucination in reasoning chains, and recovery from tool failures. The TRACE framework (KAIST, arXiv 2510.02837) decomposes trajectory quality into efficiency, hallucination, and adaptivity — each scored independently from the final answer. Multi-step agents with the same correct output can have wildly different quality trajectories.

**Layer 4 — Outcome: Did it accomplish the goal?**
End-to-end behavioral tests that ask "did the agent complete the objective?" rather than "did it use these specific tools in this exact order?" Use LLM-as-judge for nuanced scoring: task completion, adherence to constraints, response quality. Pair with code-based scorers for deterministic checks (exact matches, regex, JSON schema validation).

**Layer 5 — Production: Capture real failures as test cases.**
The highest-signal regression dataset is not handcrafted — it comes from production. Every production failure is a test case you could not have invented: an authentic edge case, real input distribution, ground truth for what "broken" looks like. Feed production traces into the eval loop: capture full execution paths (not just final errors), tag them by failure mode, add to the golden dataset, gate CI/CD on the updated suite.

**The CI flywheel:**
```
Production failure → Full trace capture → Test case authored → Golden dataset grows → CI regression gate
```

A practical first dataset: 20–50 high-signal cases. Enough to catch regressions, not so many that the suite becomes unmaintainable. Add cases incrementally as new failure modes surface.

**LLM-as-judge calibration checklist:**
- Use a judge model ranked at or above the agent being evaluated
- Apply rubrics with explicit criteria rather than open-ended scoring
- Include reference examples (anchor cases with known scores) to stabilize judges
- Track bias metrics: position bias, verbosity bias, numeric instability across runs
- Consider multi-agent debate or meta-judge approaches to reduce single-judge bias (EMNLP 2025 findings show debate amplifies bias; meta-judge is more stable)

## Evidence

- **Blog post (MachineLearningMastery, Feb 2026):** The four pillars of agent evaluation — task success, tool use quality, reasoning quality, and recovery & robustness — each require different measurement instruments. Traditional LLM metrics (BLEU, ROUGE, perplexity) measure text overlap, not behavioral outcomes. — [URL](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance)

- **Research article (Zylos Research, May 2026):** The agent testing pyramid layers unit tests (LLM isolated behind interfaces), integration tests (tool orchestration), E2E behavioral tests (goal completion), and production monitors. Key principle: push LLM dependency as high in the pyramid as possible. E2E tests should ask "did the agent accomplish the goal?" not "did it use these specific tools in this exact order?" — [URL](https://zylos.ai/en/research/2026-05-07-ai-agent-testing-strategies-production-validation/)

- **Engineering post (Arthur.ai, June 2026):** The regression test flywheel: production failure → trace → test case → golden dataset → CI gate. The first dataset should be 20–50 high-signal cases. Production failures hand you test cases no synthetic effort could invent. Capturing full traces (not just final errors) is essential for authoring meaningful regression cases. — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

- **Platform docs (Braintrust):** Notion, Stripe, Zapier, Vercel, Airtable, and Ramp use structured eval pipelines — data + task + scorers — with offline evaluation on datasets and online scoring on production traffic. Evals run on every pull request; results gate merges. Production traces feed back into the offline test suite. — [URL](https://www.braintrust.dev/articles/how-to-eval)

- **arXiv paper (KAIST/Yonsei, 2026 — arXiv 2510.02837):** The TRACE framework evaluates tool-augmented agents on trajectory efficiency, hallucination, and adaptivity — separate from answer accuracy. Same correct answer can come from dramatically different quality trajectories. Single ground-truth trajectory comparison is insufficient; multi-dimensional trajectory scoring is required. — [URL](https://arxiv.org/pdf/2510.02837)

- **Docs (Azure AgentOps Accelerator):** Three-line eval config (version, agent, dataset) maps to CI exit codes: 0 = thresholds passed, 2 = run succeeded but thresholds failed (treated as hard fail blocking deploy). Evaluator auto-selection by task kind: RAG tasks get groundedness checks, agent workflows get tool-use quality scoring, safety tasks get RAIs checks. — [URL](https://azure.github.io/agentops/evaluation)

## Gotchas

- **LLM-as-judge has systematic biases.** Verbosity bias (longer answers score higher), position bias (later-presented options score higher), and numeric instability (same scorer gives different scores across runs). Calibrate with reference anchors and track bias metrics over time.
- **Golden datasets drift.** Production distributions shift; a dataset that was representative 6 months ago may not cover current failure modes. Treat the golden dataset as a living artifact — prune stale cases, add current ones.
- **Non-determinism breaks reproducibility.** The same test case can pass or fail across runs with the same agent due to temperature or model-level variance. Run each eval case multiple trials and track variance, not just pass/fail.
- **E2E tests without trajectory visibility miss reasoning failures.** An agent can reach a correct answer via flawed reasoning that will fail on the next similar case. Instrument the execution trace, not just the outcome.
- **Synthesized test cases have a ceiling.** Handcrafted test suites cover only what engineers can anticipate. They cannot generate edge cases from real production input distributions. Always supplement with production-captured cases.
