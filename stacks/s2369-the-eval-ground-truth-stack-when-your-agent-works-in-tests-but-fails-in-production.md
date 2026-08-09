# S-2369 · The Eval Ground Truth Stack

When your agent passes every test but degrades silently in production — and you have no signal until users complain.

## Forces

- **The reliability cliff** — an agent that scores 60% on a single test run drops to 25% when run 8 consecutive times. Standard test suites miss this entirely. This isn't a flaky test problem; it's a system-level property that emerges from step-by-step failure compounding.
- **Two kinds of quality** — LLM eval measures static knowledge ("does the model know things?"). Agent eval must also measure trajectory ("did it use the right tools, in the right order, for the right reasons?"). Most teams apply the wrong framework.
- **Judges are only as good as their rubrics** — an unaligned LLM-as-a-judge gives false confidence. It produces scores that correlate poorly with user experience and diverge systematically from domain expert judgment.
- **The instrumentation gap** — you can't evaluate what you can't see. Agent traces (every tool call, reasoning step, and handoff) must be captured before any evaluation framework can touch them.

## The Move

Evaluate agents at three levels simultaneously, starting from production traces:

**End-to-end: pass/fail, not scores.** Binary task completion is the primary signal. Did the agent actually solve the user's problem? Numeric scales (1–5) are nearly useless — they don't tell you what to fix and different reviewers interpret them inconsistently. Prefer binary pass/fail or win/lose comparisons. The exception: if you have a well-aligned LLM judge, score trajectory quality separately from outcome.

**Trajectory-level: check the path, not just the destination.** Inspect execution traces to verify the agent used correct tools, in the correct order, with coherent reasoning. A task can "succeed" end-to-end while taking a wildly inefficient or dangerous path. Tools like `agent-trace-eval` (PyPI, MIT license) make this declarative: assert required/forbidden tools, expected argument shapes, and handoff sequences as a CI gate.

**Component-level: isolate which part broke.** When a trace fails, diagnose which layer — the reasoning layer (LLM planning), the action layer (tool selection), or the retrieval layer (context quality). Evaluating only the final output makes debugging impossible.

**The three-step eval loop (from Eugene Yan):**

1. **Label a small golden dataset.** 20–30 representative examples for your most critical use case. Add binary pass/fail labels. Source from real production interactions, not synthetic inputs. As Hamel Husain and Shreya Shankar note: "Spend 30 minutes manually reviewing 20–50 LLM outputs when making significant changes — use one domain expert as your reference."
2. **Align the LLM judge via critique shadowing.** Have a domain expert label 20–30 examples, then run your judge and compare. Iteratively refine the rubric until judge and expert agree. A well-aligned judge reaches 70–85% human agreement — comparable to inter-human labeler agreement (80–85%) on the same tasks.
3. **Gate CI on eval scores.** Integrate the eval harness so any prompt, model, or tool change triggers a regression run. When the score drops, the change is blocked. This is the only way to catch regressions before users do.

**Capture traces first.** LangChain's agent eval guide puts it bluntly: "most teams still evaluate agents the way they evaluate prompt chains" — they check the final output and miss the full trajectory. Lucidic (YC W25) built an observability platform around trace capture, trajectory clustering, and time-travel debugging because the founding team found that "each one-line change (prompt tweak, model switch, tool logic adjustment) required 10-minute reruns to verify."

## Evidence

- **Benchmark:** GAIA ("Generalized AI Assistants" benchmark, Meta / Hugging Face / AutoGPT, 2023+). Humans score 92% on 466 real-world multi-skill questions. Claude Sonnet 4.5 hit 74.6% as of February 2026. The gap is not about difficulty — GAIA deliberately tests tasks trivial for humans but hard for AI (multi-step reasoning + tool use + document parsing). This reveals real-world readiness better than tests that are hard for everyone. — https://agentmarketcap.ai/blog/2026/04/05/gaia-benchmark-general-purpose-agent-evaluation
- **Reliability collapse:** AWS ML Blog (February 2026) and The Operator Collective (May 2026) independently documented that agents achieving 60% single-run pass rates drop to 25% on 8 consecutive runs. "Traditional LLM evaluation methods treat agent systems as black boxes and evaluate only the final outcome, failing to provide sufficient insights to determine why AI agents fail." — https://theoperatorcollective.org/blog/ai-agent-evaluation-measure-agent-performance
- **Eval engineering time:** Hamel Husain and Shreya Shankar (2024, ongoing) report from production LLM teams that 60–80% of development time goes to error analysis and evaluation — not feature work. Tian Pan (February 2026) corroborates: "Most teams building LLM systems start with the wrong question. They ask 'how do I evaluate this?' before understanding what actually breaks." — https://hamel.dev/blog/posts/evals-faq/
- **LLM-as-judge calibration:** Chanl's production eval guide notes LLM judges achieve 70–85% human agreement on well-defined rubrics — comparable to inter-human labeler agreement of 80–85% on identical tasks. Critically: "A poorly designed judge gives false confidence. The biases are real and systematic." — https://www.channel.tel/blog/llm-as-a-judge-production-eval-pipeline
- **Binary vs. numeric:** Eugene Yan's product eval framework (November 2025) explicitly recommends binary pass/fail or win/lose labels over numeric scales: "If the criteria are objective — such as whether a summary is faithful to the source, or contains a refusal — use binary labels. Track at most 3–5 dimensions." — https://eugeneyan.com/writing/product-evals
- **Trace-based eval tooling:** `agent-trace-eval` (PyPI, MIT) performs golden trace regression checking for tool-using agents: required/forbidden tool selection, argument shapes, ordering, multi-agent handoffs, and recovery decisions. DeepEval (Confident AI, Apache-2.0, 15k+ GitHub stars) provides an end-to-end eval framework with agent-specific metrics including tool call correctness, planning coherence, and trajectory efficiency across 10+ frameworks (LangChain, LangGraph, OpenAI Agents, CrewAI, Google ADK, etc.). AgentBench (THUDM, ICLR'24) evaluates LLM-as-Agent across 8 containerized environments (ALFWorld, KnowledgeGraph, OS, Database, etc.). — https://github.com/BLVCK-MAMBA-6/llm-eval-pipeline, https://github.com/THUDM/AgentBench, https://deepeval.com/guides/guides-ai-agent-evaluation

## Gotchas

- **Don't benchmark once and ship.** A single eval run is a snapshot, not a quality signal. Run evals continuously — every prompt change, model swap, or tool modification is a regression risk. Gartner (cited by Operator Collective) predicts 40%+ of agentic AI projects will be cancelled by 2027 not because models aren't capable, but because teams can't reliably measure whether their agents work.
- **Synthetic golden datasets go stale fast.** If your eval inputs don't reflect actual user behavior, your scores are meaningless. Re-sample from production traces regularly.
- **Judge bias is systematic, not random.** Position bias (judges favoring longer responses), recency bias, and self-preference (a judge model favoring outputs similar to its own style) are well-documented. Calibration via critique shadowing is not optional — it's the only thing that makes the judge trustworthy.
- **Multi-run pass rate is the real production metric.** If your agent is for automated production use (no human in the loop), evaluate pass@8 or pass@10 — the single-run pass rate will mislead your rollout decision.
