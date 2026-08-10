# S-2431 · The Eval Stack — When You Ship on Confidence and Regret It

You ship the agent. The demo was flawless. Three weeks later, users have workarounds, data is quietly corrupted, and you can't tell if the new version is better or worse than what you had. You have no eval. You have no signal. You are flying blind. This is the stack for that moment — the evaluation harness that teams wish they'd built before they shipped, not after.

## Forces

- **Agents are systems, not models.** Single-turn accuracy metrics (BLEU, ROUGE) don't capture multi-turn failures. A task completion rate of 100% means nothing if the agent reached the answer through the wrong reasoning steps — it will fail on the next variation.
- **What you measure is what you optimize.** Teams instrument latency and token count because they're easy, not because they're what matters. The hard things — hallucination rate, tool-selection accuracy, context faithfulness — are the ones that kill production deployments.
- **Eval quality compounds over time.** Early evals create a regression test suite. Every subsequent change is checked against it. Without that, you can't tell whether the new model version or prompt actually improves the agent or just makes it louder.
- **40% of agentic AI projects will be canceled by end of 2027 (Gartner).** Root cause: teams ship without evaluative guardrails, catch failures in production, and spend the rest of their time in reactive firefighting.

## The move

Build a three-layer evaluation harness that treats the agent as a system with observable behaviors, not a black box with a pass/fail output.

**Layer 1 — Outcome metrics (did it complete the task correctly?)**
- Task success rate: binary or graded pass/fail per task across N trials (model outputs vary between runs, so run each task multiple times)
- Output quality: correctness against ground truth, factual accuracy, adherence to format constraints
- Use a **golden dataset** — curated production representative cases with known correct answers — as the primary test bed
- Augment with **synthetic test case generation**: use the LLM itself to generate test case variations from a seed set, expanding coverage without hand-labeling every case

**Layer 2 — Trajectory metrics (how did it get there?)**
- **Tool-use accuracy**: was the right tool called with the right parameters? Track tool selection precision and parameter correctness independently
- **Reasoning coherence**: does the agent's intermediate steps logically connect? Catch cases where the agent "got lucky" — reached the right answer through wrong reasoning
- **Retrieval quality**: context relevance (are retrieved chunks relevant to the query?) and context recall (did we retrieve all relevant info available?)
- **Trace analysis**: store complete execution transcripts — every LLM call, tool invocation, intermediate state — to reconstruct failures after the fact

**Layer 3 — Operational metrics (what did it cost and how fast was it?)**
- Cost per task and token efficiency (an agent achieving 95% task success but requiring 50 API calls may be technically correct but economically unviable)
- Latency per step and end-to-end completion time
- Policy compliance rate, PII handling, permission boundary violations
- Drift detection: compare trajectory distributions over time — if the agent starts calling a different tool on the same inputs, something changed

**Choose your grader based on what's being measured:**
- **Diffing** (fast, exact-match): for code outputs, structured formats, API responses — compare output to expected result character by character
- **Output-based grading** (moderate, LLM-assisted): for open-ended quality, helpfulness, tone — use a grader LLM to score the output against a rubric
- **Process-based grading** (slowest, most powerful): for agentic behavior — examine the full execution transcript, check whether correct tools were selected, whether state was managed correctly, whether errors were handled gracefully

**Run evals in CI, not manually.** Trigger on commit, on schedule, and on production events (failed user interactions automatically become new test cases). An eval that isn't automated is an eval that doesn't run.

## Evidence

- **Engineering blog: Anthropic "Demystifying Evals for AI Agents" (Jan 2026)** — Defines core eval vocabulary: task, trial, grader, transcript, assertion. Documents three grading strategies (diffing, output-based, process-based) and recommends building a golden dataset as the anchor. Emphasizes that "good evaluations help teams ship agents more confidently" and that eval value compounds over an agent's lifecycle. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Engineering post: Amazon AWS "Evaluating AI Agents: Real-world lessons from building agentic systems at Amazon" (Feb 2026)** — Documents two-component framework built across thousands of agents: an automated evaluation workflow (input definition → expected behavior definition → execution → evaluation) plus Bedrock AgentCore Evaluations library. Key insight: traditional LLM eval methods treat agents as black boxes and only measure final outcomes. Amazon's approach decomposes agents into components and measures each — tool selection accuracy, reasoning coherence, memory retrieval efficiency, task completion success rates — separately. — [URL](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Industry article: InfoQ "Evaluating AI Agents in Practice: Benchmarks, Frameworks, and Lessons Learned" (March 2026)** — Synthesizes findings across production deployments: agents are systems not models (evaluate accordingly), behavior beats benchmarks (task success and graceful recovery matter more than test-set scores), hybrid evaluation is non-negotiable (LLM-as-judge + human judgment), operational constraints (latency, cost, token efficiency) are first-class evaluation targets alongside accuracy, and safety/governance/red-teaming complete the picture. — [URL](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **The LLM-as-judge needs its own eval.** Judge models can exhibit position bias (preferring first or last options), self-preference bias (favoring outputs similar to their own), and verbosity bias (rewarding longer answers). Calibrate your judge against human judgments and target ≥0.80 Spearman correlation before relying on it at scale.
- **A single metric hides failure modes.** Task success rate of 90% sounds great until you discover that the agent achieves it by always taking the safe, wrong path that happens to produce plausible-looking output. Segment metrics: success rate by task type, by tool used, by step count.
- **Benchmark scores ≠ production readiness.** Agents scoring well on AgentBench, WebArena, SWE-bench, or GAIA frequently fail in real deployments because benchmarks measure task completion on curated environments, not context faithfulness, hallucination resistance, or graceful degradation under distribution shift.
- **Production feedback loops require curation.** Automatically turning failed user interactions into new test cases is powerful, but requires a human review step to prevent dataset poisoning — adversarial users can intentionally trigger failures that get added to your golden set.
