# S-1452 · The Trajectory Stack — When Your Agent Passes the Answer but Fails the Reasoning

When your agent's final output looks correct, but the reasoning path was broken — it called the wrong API, passed bad parameters, and arrived at the right answer by accident. You can't ship it and you can't explain why it fails in prod.

## Forces

- **Output quality ≠ reasoning quality** — a travel agent can return the correct flight by calling the wrong booking API and getting lucky with a cached result. The answer passes; the agent is broken.
- **Traditional LLM metrics don't apply** — BLEU, ROUGE, and perplexity measure text generation quality. They tell you nothing about whether the right tools were called, in the right order, with the right arguments.
- **Vibe-check is the default trap** — change a prompt, test a few inputs, ship if it "looks good." This works until production, where silent failures (right answer, wrong path) compound invisibly.
- **The three gulfs of LLM development** — the development-evaluation gulf (writing code vs. knowing it's correct), the eval-reality gulf (passing tests vs. working in prod), and the eval-maintenance gulf (evals that rot as the system evolves).

## The Move

Measure the trajectory, not just the destination. Evaluate the full action sequence — planning, tool selection, parameter passing, intermediate state, failure recovery — alongside the final output.

**Build a layered evaluation stack:**

- **Black-box layer** — evaluate final output against known correct answers. Catches gross failures. Fast and deterministic but tells you nothing about *how* the agent arrived.
- **Grey-box layer** — trace analysis. Instrument every tool call, step sequence, and decision point. Verify: was the right tool selected? Were parameters correct? Did the agent recover from failures gracefully? This is where most agent-specific bugs live.
- **White-box layer** — inspect internal state: reasoning chains, memory access, context management. Captures silent failures where the agent "hallucinates" a tool call or loses track of prior steps.

**Use code-based evals for deterministic failures** — assertions that fail if a specific tool wasn't called, wrong parameters were passed, or a step was skipped. These are fast, repeatable, and integrate into CI.

**Use LLM-as-judge for subjective cases** — tone, trustworthiness, contextual appropriateness. Partition test data so the judge doesn't memorize answers; measure generalization to unseen cases. Validate the judge's own accuracy (true positive rate, true negative rate) against human experts before trusting it.

**Track operational metrics as first-class evaluation targets** — cost per task, token efficiency, tool reliability, retry loops, and latency. An agent that's right but 50x over budget still fails in production.

**Integrate evals into CI/CD** — run regression suites on every code change. A prompt or tool change that degrades quality on edge cases should block a deploy, not reach production.

## Evidence

- **Pragmatic Engineer / Gergely Orosz & Hamel Husain (Dec 2025):** The "vibe-check development trap" — NurtureBoss changed prompts, tested a few inputs, shipped on LGTM — until production revealed failures. Recommends error analysis workflow, code-based evals for deterministic cases, LLM-as-judge for subjective ones, and aligning judge accuracy against human expertise. Partition test data to prevent judge memorization.
  — https://newsletter.pragmaticengineer.com/p/evals

- **AI Workflow Lab (Jun 2026):** Three-layer evaluation framework: black-box (output quality), grey-box (trace analysis — tool calls, step sequences), white-box (internal state). Highlights silent failures where correct outputs mask broken reasoning paths. Recommends CI/CD integration with golden datasets and trajectory evaluation.
  — https://aiworkflowlab.dev/article/test-ai-agents-production-trajectory-evaluation-tool-validation-python

- **InfoQ / Amit Kumar Padhy (Mar 2026):** "Agents are systems, not models — evaluate them accordingly." LLM metrics (BLEU, ROUGE) don't capture multi-step reasoning, tool failure recovery, or consistency under variability. Emphasizes hybrid evaluation (automated + human judgment) and operational constraints as first-class evaluation targets alongside accuracy.
  — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/

- **MachineLearningMastery / Vinod Chugani (Feb 2026):** LLM eval vs. agent eval distinction: text quality vs. action and decision assessment. Evaluates right API endpoints called, correct parameters passed, and failure recovery capability. Agents "take actions" — the evaluation surface is fundamentally different.
  — https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance

## Gotchas

- **Don't evaluate the answer without evaluating the path.** Silent failures (right output, broken reasoning) are the most dangerous class of agent bug and the hardest to catch with black-box-only evaluation.
- **LLM-as-judge needs its own evaluation.** A judge model that isn't validated against human ground truth will confidently rate wrong trajectories as correct. Measure TPR and TNR before trusting scores.
- **Evals rot.** When the agent's capabilities change or new tools are added, old golden datasets become stale. Treat eval maintenance as a first-class engineering concern, not an afterthought.
- **Operational metrics reveal what accuracy misses.** An agent scoring 87% on task completion but burning 50x the budget per task is not production-ready — track cost, latency, and token efficiency alongside quality metrics.
- **CI gate discipline matters.** If evals aren't blocking deploys, they're just observability dashboards. The investment only pays off when regressions actually stop ships.
