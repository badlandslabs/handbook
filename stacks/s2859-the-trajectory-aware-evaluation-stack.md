# S-2859 · The Trajectory-Aware Evaluation Stack

[When your agent gets the right answer 90% of the time but burns 12 tool calls and $0.40 per task doing it — and you have no idea.]

## Forces

- **Answer correctness hides path failure.** An agent that produces a correct output via 8 hallucinated tool calls and 3 retries is scored identically to one that got there cleanly in 2 steps. Aggregate success rate is a lie you tell yourself.
- **LLM-as-judge is not a free lunch.** Used without rubrics or calibration, it inherits the model's biases and gives false confidence. Practitioners who skipped structured judge prompts report that judges systematically prefer verbose, confident-sounding outputs over concise, correct ones.
- **Trajectory data is the only debuggable record.** A multi-step agent that fails silently in production is unfixable without a replayable execution trace. Teams that deferred observability regret it when the first real incident hits.
- **Eval depth and eval count trade off.** Running 500 evals with thin outcome checks beats running 20 with deep trajectory grading — but only if you can operationalize the signal to actually change what the agent does.

## The move

Measure agents on *how* they solved a problem, not just *whether* they did. Use a two-axis evaluation framework (outcome + process) and instrument traces from day one.

### Outcome axis — did it work?

- **Task success rate** — binary or numeric-tolerant match of the final deliverable against a reference answer. The baseline.
- **Pass@k / Cost@k** — success rate at a given cost ceiling. Filters out agents that succeed by brute-forcing through retries.

### Process axis — did it get there sensibly?

- **Tool-call F1** — precision, recall, and F1 on the multiset of tools called vs. the reference trajectory. Did it use the right tools in the right order, without hallucinated steps?
- **Step efficiency** — actual steps vs. optimal steps. A correct answer in 12 steps scores differently from the same answer in 3 steps.
- **Token/trajectory cost** — measures verbosity and reasoning overhead. Useful for budget-constrained deployments.
- **Reasoning quality** — captured via structured rubrics fed to LLM-as-judge, not raw "is this good?" prompts.

### Instrument everything from the start

- **LangSmith** (LangChain): offline eval datasets + online production monitoring, calibration workflow for LLM-as-judge against human-labeled samples. Used by Klarna, LinkedIn, Coinbase, Harvey in production.
- **Langfuse** or **OpenTelemetry** traces: capture every tool call, LLM response, and state transition as a replayable trace. Non-negotiable for multi-step agents.
- **Open-source harness** (tkarim45/agent-eval-harness on GitHub): Claude-compatible, measures success + tool-call F1 + step efficiency + cost per run. Good for teams wanting self-hosted without vendor lock-in.

### Calibrate judges, then trust them

- Write explicit rubrics with score anchors (0–5 per criterion, not freeform).
- Calibrate against a small human-labeled golden set (20–50 examples) before running at scale.
- Use **trajectory-aware judges** — feed the full execution trace, not just the final answer. A judge that sees the agent call `delete_table()` and recover gets a different score from one that sees only the final "I successfully completed the task."
- Run human spot-checks on 5–10% of judge decisions indefinitely.

### Operationalize the signal

- Block deploys on eval regressions (e.g., tool-call F1 drops >5% or step efficiency degrades).
- Use production traffic sampling: replay real user sessions through evals nightly, alert on divergence from baseline.
- Curate eval datasets continuously — production failures become new eval cases.

## Evidence

- **HN Discussion (128 points, 2025):** Practitioners on "Principles for production AI agents" debate: "If you don't have evals, you really don't know if you're moving the needle at all" — but an experienced eval-suite owner cautions that LLMs are unreliable as critics *without structured rubrics*. Advice evolved from "hundreds of evals" to "fewer, tightly tied to specific features and prod behavior." — [HN #44712315](https://news.ycombinator.com/item?id=44712315)
- **NVIDIA Technical Blog (2026):** Distinguishes AI model evaluation (static benchmarks: MMLU, HumanEval) from agent evaluation (dynamic workflows: task success, tool call accuracy, trajectory efficiency). Emphasizes evaluating the *complete trajectory* — plans, tool calls, intermediate reasoning, outcomes — not just final answers. — [developer.nvidia.com](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **LangSmith / LangChain docs:** Documents offline + online eval split. Offline: curated datasets for regression testing before deploy. Online: production traffic sampling with LLM-as-judge scoring. Stresses calibration against human-labeled data before scaling judge evaluation. — [docs.langchain.com](https://www.langchain.com/langsmith/evaluation)
- **MLflow LLM-as-a-Judge guide:** "Traditional metrics like BLEU and ROUGE measure token overlap but miss whether a response hallucinated or violated tone guidelines. Human reviewers catch these issues but can only evaluate a limited number of outputs per day." — [mlflow.org](https://mlflow.org/llm-as-a-judge)
- **Turion.ai — Multi-Agent Orchestration in Production (March 2026):** Production multi-agent systems are harder to operate by roughly the order of their agent count. Without instrumented traces from day one, debugging is impossible. LangGraph supervisor pattern and CrewAI hierarchical mode cited as the most debuggable multi-agent approaches. — [turion.ai](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production/)
- **Sandeep Kumar Chaudhary — Framework comparison (2026):** "Instrument traces from day one — you cannot debug a multi-step agent you cannot replay." Recommends LangGraph for stateful graph-structured control flow; pipeline pattern (researcher → writer → editor) for predictable cost and per-step eval. — [sandeepkumarchaudhary.com](https://sandeepkumarchaudhary.com/blog/multi-agent-orchestration-frameworks-in-production-lessons)
- **GitHub: tkarim45/agent-eval-harness:** Open-source harness for Claude agents. Grading schema: success rate, tool-call accuracy (F1), step efficiency (actual vs. optimal steps), cost per run. Interactive trajectory viewer for manual inspection. — [github.com/tkarim45/agent-eval-harness](https://github.com/tkarim45/agent-eval-harness)
- **Maxim AI — Three-Layer Eval Framework:** System Efficiency (latency, tokens, tool calls) + Session-Level Outcomes (task success, trajectory quality) + Node-Level Precision (tool selection, step utility). Offline simulation → online production monitoring with alerts. — [getmaxim.ai](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices/)
- **Thoughtworks — Evaluating AI Agents in Production (2026):** "~95% of AI projects fail." Proposes a four-step eval cycle: define success criteria, run offline evals, monitor production with online evals, continuously improve with production feedback. — [thoughtworks.com](https://www.thoughtworks.com/en-in/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)

## Gotchas

- **Relying on answer-only metrics** — the single most common mistake. A final-answer check tells you nothing about *how* the agent got there, so you can't distinguish a clean solve from a lucky hallucination chain.
- **LLM-as-judge without calibration** — judges have documented biases: preference for verbose outputs, over-confidence, positional bias in comparisons. Calibrate against human judgments before trusting scores at scale.
- **Too many evals that don't drive decisions** — 500 evals that nobody looks at before a deploy are noise. Better to have 20 evals with clear pass/fail gates that block regressions.
- **Deferring observability** — teams that skip trace instrumentation until something breaks end up unable to replay failures. Add tracing on day one, even if you don't have dashboards yet.
- **Benchmark shopping** — public benchmarks (MMLU, HumanEval) measure model capability, not your agent's performance on your specific task. Build task-specific eval datasets; use benchmarks only for model selection.
