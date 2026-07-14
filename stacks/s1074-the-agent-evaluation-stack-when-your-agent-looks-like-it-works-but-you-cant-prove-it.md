# S-1074 · The Agent Evaluation Stack — When Your Agent Looks Like It Works, But You Can't Prove It

Your agent demo was flawless. The five test cases you ran all passed. Finance approved the project. Then three weeks into production, a pattern emerges: the agent completes 68% of tasks successfully, but you only know this because a customer complained. You have no automated way to know whether the 32% failure rate is improving or degrading after the latest model update. You cannot ship faster without a measurement system. The agent evaluation stack closes this gap.

## Forces

- **Standard LLM benchmarks don't measure agents.** Task-completion scores on SWE-bench or WebArena score a model's capability in isolation — not how it behaves when wired to tools, state, and real users. A model that scores 90% on HumanEval can still loop forever on a production task.
- **Task completion alone is insufficient.** Two agents can both "succeed" while taking 4 steps or 47. The failure mode that costs money is not wrong answers — it's wrong paths, excessive tool calls, and silent semantically-broken outputs that look successful to observability.
- **Benchmarks can be gamed.** UC Berkeley's Center for Responsible, Decentralized Intelligence (RDI) built an automated scanner and found exploitable vulnerabilities in every major agent benchmark — SWE-bench, WebArena, OSWorld, Terminal-Bench, FieldWorkArena, and CAR-bench all had bypass paths. A 10-line Python file achieved near-perfect scores on SWE-bench Verified without solving any tasks. The scores on leaderboards reflect harness exploitation, not agent capability.
- **Production requirements differ from benchmark tasks.** AlphaEval (arXiv:2604.12162, April 2026) surveyed 27 AI companies deploying agents commercially and found: 63% report low confidence that model updates actually improve their products; 25.9% have no explicit evaluation system at all. Real production tasks have implicit constraints, heterogeneous inputs, and success judged by evolving domain expert standards — none of which benchmark tasks capture.
- **Evaluation without a release gate is just measurement theater.** Teams that ship fast have treated evaluation as CI/CD infrastructure, not a pre-launch checklist. Static benchmarks that run monthly are too slow to catch regressions in agents that process thousands of sessions per day.

## The Move

Build a three-layer evaluation harness: deterministic gates for objective task success, LLM-as-a-judge for subjective quality dimensions, and production span analysis for behavioral drift detection.

**1. Define task-completion gates first — always.** Before any LLM judge, define what "done" means for each task type. Use exact-match checks where possible (file written, API response code, database row created). These are fast, free of judge bias, and serve as non-negotiable release blockers. If the agent's final output doesn't match ground truth, nothing else matters.

**2. Score at every decision point, not just the output.** Agent failures compound: a wrong tool selection in step 2 corrupts steps 3–8. Instrument your trace to record per-step outcomes — which tool was called, with what arguments, what it returned — and score each independently. This gives you step-accuracy metrics, not just end-to-end success. Braintrust frames it this way: "a bad decision in step two affects step three, which affects step four, until the final output fails."

**3. Use LLM-as-a-judge for quality dimensions LLMs can't self-evaluate.** Faithfulness (does the output stay within the retrieved context?), answer relevance, tone alignment, and safety are quality dimensions that require a second model to evaluate. Use a judge model from a different family than your agent (e.g., Claude to judge a GPT agent) to reduce alignment gaming. Calibrate the judge against 50–100 human-annotated examples before treating its scores as ground truth — LLM judges exhibit systematic biases like favoring longer outputs or certain writing styles.

**4. Combine user signals and offline metrics.** Purely automated evaluation misses what users actually experience. Thumbs up/down is insufficient but still useful as a leading indicator. Teams shipping reliable agents at scale (per Maxim's production learnings) combine: automated eval scores (deterministic + LLM judge), user feedback signals, and span-level drift detection. Failed production sessions become regression tests — this closes the loop between production reality and your eval suite.

**5. Evaluate at three lifecycle points: pre-merge, staging, and production sampling.** Pre-merge catches regressions before they enter the codebase. Staging runs the full suite against a staging environment. Production sampling runs 5–10% of live sessions through the eval pipeline to catch distribution drift. Static benchmarks that run monthly are insufficient; teams that move fast run evals in every CI pipeline.

**6. Treat your eval suite as a living dataset.** The most effective teams (per AlphaEval's findings) build production-grounded benchmarks — authenticated requirements from actual deployments rather than retrospectively curated tasks. As user behavior shifts, your eval suite must evolve. Use production failure patterns to expand test coverage automatically.

## Evidence

- **AlphaEval production-grounded benchmark (arXiv:2604.12162, April 2026):** Surveyed 27 AI companies deploying agents commercially. Found 63% lack confidence that model updates improve products; 25.9% have no explicit evaluation system. Best-performing agent scored 64.41/100 on real commercial tasks — a significant gap from leaderboard scores. Key insight: scaffold design matters as much as model choice, and six production-specific failure modes were identified that research benchmarks miss entirely. — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162)

- **UC Berkeley RDI — Benchmarks are gamed (April 2026):** Automated vulnerability scanner found exploitable paths in every major agent benchmark tested — SWE-bench, WebArena, OSWorld, Terminal-Bench, FieldWorkArena, and CAR-bench. A 10-line Python script achieved near-perfect scores on SWE-bench Verified without solving any underlying tasks. Findings to be submitted to NeurIPS. Released BenchJack vulnerability scanner for benchmark authors. — [Ship or Skip / Berkeley RDI](https://shiporskip.io/news/berkeley-rdi-ai-agent-benchmarks-broken-swebench-webarena-exploit-2026)

- **Braintrust — Practical agent evaluation framework:** Documents the architectural difference between LLM eval (single prompt-response) and agent eval (multi-step decision sequences). Recommends evaluating at every tool call boundary, not just final output. Frames the four evaluation dimensions as: task completion, efficiency (steps taken vs. optimal), quality (faithfulness, relevance), and safety. — [Braintrust](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)

- **deepsense.ai — Production agent evaluation from enterprise deployments:** Deployed multi-agent systems for clients in sports analytics, pharma, and telecom. Key finding: orchestration patterns that survive production differ significantly from single-agent architectures; evaluation and monitoring are the primary differentiators between proof-of-concept and production. — [Hacker News](https://news.ycombinator.com/item?id=45718390)

- **Maxim (getmaxim.ai) — Evaluation as production infrastructure:** "The teams shipping reliable agents fastest combine deterministic rules, statistical monitoring, LLM judges, and human review." Treats evaluation as CI/CD infrastructure: failed sessions become regression tests, successful patterns inform persona modeling. — [Maxim Blog](https://maxim-articles.ghost.io/how-to-evaluate-ai-agents-in-production-metrics-methods-and-pitfalls)

## Gotchas

- **Don't trust leaderboard scores for agent selection.** Benchmarks can be gamed and don't reflect production task distributions. A model that scores 90% on SWE-bench can fail on your specific workflow. Use benchmark scores as a sanity filter, not a selection decision — evaluate on your actual task distribution.
- **LLM-as-a-judge needs calibration, not just prompting.** Judges exhibit systematic biases: favoring longer outputs, preferring certain formats, avoiding low scores on safety dimensions. Run 50–100 human-annotated examples through your judge before trusting its scores. Use DSPy or LLM-Rubric techniques to correct judge drift over time.
- **Task-completion metrics hide efficiency.** An agent that "succeeds" in 47 tool calls costs 10× what an agent that succeeds in 5 does. Measure step count, token usage, and cost per session alongside completion rate.
- **Offline eval suites go stale.** User behavior shifts; new failure modes emerge in production. If your eval suite hasn't changed in 60 days, it's no longer measuring what matters. Build a pipeline that auto-expands test coverage from production failures.
- **Don't evaluate agents the way you evaluate models.** The agent is a system — model + tools + memory + orchestration. Changing the model is one intervention; changing the scaffold (how the model uses tools, when it loops, how it recovers from errors) is often the higher-leverage change. AlphaEval confirms: scaffold design matters as much as model choice.
