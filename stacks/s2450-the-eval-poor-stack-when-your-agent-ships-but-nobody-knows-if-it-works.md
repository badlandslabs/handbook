# S-2450 · The Eval-Poor Stack — When Your Agent Ships But Nobody Knows If It Works

You have a multi-step agent running in production. You upgraded the model last week. You changed the prompt two days ago. You shipped the new tool definition last night. And you have no idea if any of that made things better or worse — because nothing is measuring whether the agent actually does what it's supposed to do. Failures surface as user complaints, not test failures.

## Forces

- **The evaluation gap is real:** 72% of AI teams believe comprehensive testing drives reliability, but only 15% achieve elite eval coverage (90–100% of behaviors tested). This 57-point belief-execution gap is not negligence — it's that eval infrastructure is genuinely hard to build for agents. (Galileo, 2025)
- **Agents fail in the middle, not at the end:** A weak plan or wrong tool call cascades through every subsequent step. The final answer looks fine while the trajectory is broken. End-to-end scores tell you something broke, not which component broke. (Confident AI, 2026)
- **Traditional LLM metrics don't translate:** BLEU scores, perplexity, and ROUGE measure text quality — not tool selection, recovery behavior, or trajectory coherence. Evaluating an agent with the same tools as a standalone model is like testing a calculator's display instead of the entire financial system. (MachineLearningMastery, Feb 2026)
- **LLM-as-judge has known biases:** It favors longer answers and outputs similar to its own style, and it is non-deterministic. Research suggests a 0–5 scale with explicit criteria aligns best with human judgment compared to binary pass/fail. Relying on it unquestionably for every production decision is a known failure mode. (DataKnobs, 2025)

## The move

Build a layered eval system that spans development, staging, and production — not a single test at ship time.

- **Define task-level success criteria before writing a single prompt.** The evaluation is the spec. Without it, "good enough" is unmeasurable. Start with 50–100 test cases covering happy paths, critical edge cases, and known failure modes. Grow to 500+ by ingesting every production failure as a new test case. (DataKnobs, Maxim.ai)
- **Evaluate at three granularities simultaneously:**
  - *Session level:* Did the agent complete the task? (task success rate, escalation quality, end-to-end outcome)
  - *Trace level:* Was the reasoning path sound? (trajectory coherence, tool selection sequence, step utility)
  - *Span level:* Did individual tool calls use the right parameters and produce usable output? (tool call accuracy, parameter fidelity)
  (Maxim.ai, Anthropic evals guide)
- **Run a golden dataset against every change.** A golden dataset is a curated set of inputs with known-correct outputs or outcomes, built from real production interactions. Before a model upgrade, prompt change, or tool definition edit, run the full dataset and compare pass rates. This is the regression gate that catches silent regressions. (TribeAI claude-evals, GitHub jbelnick/llm-judge-evals)
- **Use deterministic scorers where possible.** For tasks with verifiable outputs (code that must compile, math that must evaluate, API calls that must return specific shapes), write deterministic grading logic. Reserve LLM-as-judge for subjective or open-ended evaluations, and calibrate it on a human-labeled sample before using it as a gate. (jbelnick/llm-judge-evals)
- **Add async production evals that don't block the agent.** Production evaluation should run asynchronously — score the trace after the agent completes, not during. This avoids latency overhead and lets you evaluate trajectory quality, not just the final token. (DeepEval docs, MLflow agent eval roundup)
- **Instrument with trace-level observability before writing any evals.** You cannot evaluate what you cannot see. Add structured tracing (spans, tool calls, intermediate states) as the foundation. Without it, you have no data to grade against. (Inference.net, Lucidic HN launch)

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" (Jan 2026) describes the three-layer eval structure and the importance of task/trial/sample separation. States that evals make behavioral changes visible before they affect users — the reactive loop is the failure mode. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Survey:** "Evaluation and Benchmarking of LLM Agents: A Survey" (arXiv:2507.21504) documents that ~83% of surveyed agent eval studies focus on capability metrics, while human-centered and economic metrics are each considered in ~30% of studies — indicating a gap between what teams measure and what matters in production. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **Y Combinator company:** Lucidic (YC W25, launched July 2025) was founded specifically to solve the eval problem — their origin story describes every one-line change (prompt tweak, model switch, tool logic adjustment) requiring a 10-minute rerun to check if the agent still hit the right checkout page. Built trace-level observability as the foundation for their eval platform. — [news.ycombinator.com/item?id=44735843](https://news.ycombinator.com/item?id=44735843)
- **HN discussion:** On "Principles for production AI agents" (July 2025, 128 pts), practitioner roadside_picnic argued evals are "vital for improving performance" and criticized teams relying on LLM-as-critic without empirical validation. App.build's response centered on evaluation as a discipline, not just a tool. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **Open-source harness:** TribeAI/claude-evals (Feb 2026) implements Anthropic's published eval patterns with native SDK hooks, a 50-case golden dataset, and one-command model comparison — explicitly targeting enterprise teams who "hit the same wall" without eval infrastructure. — [github.com/TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)

## Gotchas

- **Shipping without a baseline is the default and the trap.** If you don't measure before the first ship, you have no regression baseline. Every subsequent change is compared against "seems fine." Establish the baseline on day one, even if it's just a 10-case golden set.
- **LLM-as-judge gamed by your own model is a real failure mode.** If your judge model and your agent model are from the same family, they share style biases. Use a different model family for judgment, or fall back to deterministic scorers for verifiable outputs.
- **Eval coverage is not binary.** A test suite that covers 40% of your agent's behaviors gives you false confidence. The goal is 90%+ behavioral coverage — you know you've reached it when you can confidently predict what the agent will do on edge cases, not just happy paths.
- **Production evals catch what staging misses.** Agents are non-deterministic and their behavior depends on real-world tool responses. A staging eval against mocked APIs won't catch the failure mode where the real payment gateway returns an unexpected error code on a full-moon Tuesday.
- **Cost of eval compounds if you build it late.** Retrofitting eval infrastructure into an existing agent system is expensive — every trace needs to be instrumented, every tool needs structured output, every failure needs a test case. The later you start, the more retrofitting required.
