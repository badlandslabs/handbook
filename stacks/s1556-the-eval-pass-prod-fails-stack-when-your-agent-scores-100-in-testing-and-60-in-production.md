# S-1556 · The Eval-Pass, Prod-Fail Stack

_You've shipped a 20-step agent. It scores 95% on your eval suite. Production uptime: 36%._

## Forces

- **Lab benchmarks measure capability, not reliability.** AgentBench, MT-Bench, and HELM score whether a model _can_ do a task in isolation. They don't measure whether it _will_ keep doing it reliably over 20 sequential steps on messy real inputs.
- **Eval sets age the day they ship.** Every prompt update, model swap, API schema change, and shift in user intent widens the gap between your frozen rubric and live behavior. Without a pipeline that promotes failures back into the eval set, you're scoring yesterday's agent against tomorrow's production.
- **Lusser's Law bites harder than people expect.** At 95% per-step accuracy, a 10-step task succeeds ~60% of the time. A 20-step task succeeds ~36%. No amount of prompt engineering closes this gap — only architectural changes do.
- **Three grader types, one right answer.** Code graders are fast and objective but brittle. Model graders handle nuance but are non-deterministic. Human graders are gold standard but slow and expensive. Most teams use one; the teams that ship reliably use all three in combination.

## The Move

Treat evaluation as a continuous production pipeline, not a pre-deploy gate.

- **Start with 5–10 curated examples per critical component.** Break the agent into LLM calls, retrieval steps, tool invocations, and output formatting. Create examples of what "good" looks like for each. These seed both offline evals and human annotation queues.
- **Run offline evals on curated datasets before every deploy.** Target deterministic correctness — did the agent reach the right answer, call the right tools in the right order? Code graders work well here. Catch regressions before they reach users.
- **Run online evaluations continuously on production traffic.** Sample real traces, check for quality patterns and safety concerns, flag anomalies. Don't wait for users to report failures — the trace volume in production makes manual debugging unsustainable.
- **Feed production failures back into the eval set.** The "promote-back" pattern: capture failing traces → annotate them → add them as test cases → run evaluations → deploy fixes. This closes the drift loop. A static eval set is an aging eval set.
- **Prefer shorter chains.** Every step multiplies failure probability. If you can compose two steps into one, do it. If a step can be verified programmatically between agent calls, add that verification.
- **Combine grader types.** Use code graders for anything with a verifiable ground truth. Use model graders for subjective quality (tone, relevance, helpfulness). Use human graders for calibration and edge-case review. Run all three on a sample of production traces monthly.

## Evidence

- **arXiv paper:** Seven failure modes unique to production agentic systems at billion-event scale — compounding decision errors, tool failure cascades, output drift, and more — where standard metrics (ROUGE, BERTScore, accuracy/AUC) fail to detect each failure mode. Proposes PAEF: a five-dimension continuous evaluation framework. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **FutureAGI blog:** Six "drift modes" that age every eval set from the moment it ships — dataset drift, tool-API drift, prompt drift, retrieval-corpus drift, user-distribution drift, and agent-step compounding. Proposes the four-dimensional trace score and Error Feed loop (trace → analyze → dataset → eval → improve). — [futureagi.com](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)
- **Anthropic engineering guide:** Evals for AI agents — defines the eval lifecycle, recommends combining code-based, model-based, and human graders. Capability evals measure what the agent can do; regression evals catch behavioral changes as the system evolves. — [anthropic.com](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **LangSmith docs:** Offline evaluations target curated datasets (reference outputs); online evaluations target production traces (no reference outputs). The fastest teams connect observation to action: capture traces, build test datasets from real usage, run evaluations, drive improvements. — [docs.langchain.com/langsmith/evaluation-concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- **LensHQ blog:** Math behind compounding errors — 95% per-step accuracy → ~60% success over 10 steps, ~36% over 20 steps. The fix: shorter chains, verification between steps, human-in-the-loop for risky actions. — [lenshq.io](https://www.lenshq.io/blog/ai-agent-compounding-errors-math)

## Gotchas

- **Your eval set is a snapshot; production is a river.** An eval set that isn't continuously updated from production failures will confidently tell you an agent is working while it's silently degrading in production.
- **Single-grader evaluations lie.** Teams that only use model-based graders lose sensitivity to regressions in objectively-measurable behaviors. Teams that only use code graders miss quality regressions that don't affect correctness. Teams that only use human graders can't run evals at scale.
- **Trajectory evaluation is distinct from output evaluation.** Checking whether the agent produced the right answer doesn't tell you whether it took a sensible reasoning path. For agents using multiple tools or steps, you need to evaluate the trajectory — did it call the right tools in the right order?
- **Drift is invisible without tracing.** Without a production trace pipeline, there's no way to detect prompt drift, API-schema drift, or user-distribution drift until users complain.
