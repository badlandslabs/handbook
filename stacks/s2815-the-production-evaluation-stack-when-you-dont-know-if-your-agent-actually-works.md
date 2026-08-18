# S-2815 · The Production Evaluation Stack — When You Don't Know If Your Agent Actually Works

You shipped the agent. It works in the demo. You have no idea if it's actually working for users. The prompt changed last week and nobody caught the regression. This is the evaluation problem — and it's the reason most agent teams ship blind.

## Forces

- **Agents are non-deterministic systems.** They plan, call tools, maintain state, and adapt across turns. Single-turn accuracy metrics (BLEU, ROUGE, precision) don't capture how agents fail — a task can succeed on output alone while the agent took a wildly inefficient or reasoning-broken path to get there.
- **The evaluation surfaces are three layers deep.** Task outcome (did it succeed?), trajectory quality (was the path sound and efficient?), and component integrity (which tool or sub-agent failed?) require distinct measurement approaches. One number cannot carry all of this.
- **Production vs. benchmark divergence is massive.** AlphaEval (arXiv:2604.12162, April 2026) evaluated 94 real commercial agent tasks from 7 companies. Best configuration scored 64.41/100. Existing agent benchmarks — with curated tasks, well-specified requirements, and deterministic metrics — do not reflect the messy reality of production: loosely defined requirements, heterogeneous multi-modal inputs, fragmented information, and success judged by domain experts whose standards evolve over time.
- **Most teams have no eval infrastructure at all.** Per LangChain's 2026 State of AI Agents report, only 52% of organizations have formal evaluation processes. No evals means reactive loops: user complaint → manual reproduction → fix → hope nothing broke.
- **Evals are a moving target.** As agents improve, your golden dataset needs to evolve. As production traffic drifts, edge cases you never imagined become load-bearing. Stale evals are worse than no evals — they give false confidence.

## The Move

Build a production evaluation system in four layers:

1. **Mine a golden dataset from production failures, not fiction.** The golden dataset is the single most leveraged artifact in an agent program — a versioned, auditable, evolving collection of inputs paired with reference outputs and graders. Mine it from production traces (failed runs, edge cases, user escalations). Have domain experts annotate, not interns. Every time the agent fails in a new way, add that case. Without a golden dataset, every prompt change is judged on whichever 6 calls the on-call engineer happened to look at that morning — that is augury, not evaluation.

2. **Evaluate at three levels, not one.** End-to-end: did the task succeed? Trajectory-level: was the path efficient and sound (correct tools in correct order, no skipped logical steps, graceful recovery from tool errors)? Component-level: which specific tool, retriever, or sub-agent malfunctioned? A task can succeed while the trajectory is bloated and fragile — you need to catch both.

3. **Stack multiple grader types, not one.** No single scoring method covers all failure modes. Use exact match (deterministic outputs with clear right/wrong answers). Programmatic checks (structured outputs, schema validation, tool call sequences). LLM-as-judge (reasoning quality, answer faithfulness, tone, contextual appropriateness). Trace analysis (regression on tool call counts, token efficiency, recovery behavior). The grader is a composition of assertions, not a single score.

4. **Gate CI/CD on eval scores, not vibes.** The evaluation pipeline: Git commit → CI runner executes agent → captures full trajectory → LLM-as-judge grades → asserts score ≥ threshold (e.g. 0.85) → deploy or block. This makes behavioral regressions visible before they reach users. Without CI gates, evals become post-hoc theater — interesting data nobody acts on.

5. **Close the loop: production failures populate the golden dataset.** When a production trace fails in a new way, extract the input, annotate the expected output with a domain expert, add it to the dataset. This is the mechanism by which eval coverage grows proportionally with real-world exposure — not through imagined edge cases but through actual failure patterns.

## Evidence

- **arXiv paper:** AlphaEval benchmarked 94 real commercial agent tasks from 7 companies across 6 O\*NET domains. Best system scored 64.41/100. Average task required 46 interaction turns and 14 minutes of execution. Key finding: "existing benchmarks measure agent capabilities through retrospectively curated tasks with well-specified requirements and deterministic metrics — conditions that diverge fundamentally from production environments." — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162)

- **Engineering blog:** Anthropic's agent evaluation guide establishes the core vocabulary: tasks (inputs + success criteria), trials (attempts), graders (scoring logic with multiple assertions), and transcripts (complete execution records including tool calls and intermediate reasoning). Key insight: "The capabilities that make agents useful also make them difficult to evaluate. Good evaluations help teams ship agents more confidently. Without them, it's easy to get stuck in reactive loops — catching issues only in production, where fixing one failure creates others." — [Anthropic Engineering, Jan 2026](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Engineering post:** CallSphere principal engineer details golden dataset construction from production trace mining to LangSmith annotation queues. Key quote: "Without a golden dataset, every prompt change is judged on whichever 6 calls the on-call engineer happened to look at that morning. That is not evaluation — that is augury." — [CallSphere Blog, May 2026](https://callsphere.ai/blog/golden-dataset-production-ai-agents-langsmith)

- **Industry survey:** LangChain 2026 State of AI Agents report: only 52% of organizations have formal evaluation processes. Top-performing teams (top 15%) use multi-layered observability across task success, trajectory efficiency, and component integrity. — cited in [Heym.run Blog, May 2026](https://heym.run/blog/ai-agent-evaluation)

- **Industry guide:** InfoQ analysis of production agent evaluation lessons: "Agents are systems, not models — evaluate them accordingly. Single-turn accuracy metrics don't capture how agents fail in practice. Hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) with human judgment (tone, trust, contextual appropriateness) is non-negotiable." Five pillars: intelligence, performance, reliability, responsibility, user experience. — [InfoQ, March 2026](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Writing golden dataset cases from imagination.** Synthetic test cases miss the shape of real failures. Mine from production traces; have domain experts annotate; let failures drive coverage growth.
- **Running single trials.** Agents are non-deterministic. One run is a sample, not a measurement. Run each test case 3–5 times and measure consistency, not just average score.
- **Scoring outputs without inspecting trajectories.** A task can succeed with the wrong tools, excessive LLM calls, and no recovery from errors. The path matters as much as the outcome — trajectory-level evaluation catches what end-to-end metrics hide.
- **Building evals once and forgetting them.** Eval coverage decays as the agent improves and production traffic evolves. Set a cadence (monthly review minimum) to mine new failures, retire outdated cases, and refresh thresholds.
- **Treating LLM-as-judge as ground truth.** LLM judges carry their own biases — preferring certain writing styles, being lenient on self-criticism, disagreeing 15–30% of the time on complex trajectories (per ACL 2025 research cited in Awesome-Agentic-System-Design). Calibrate judges against humanannotated samples; use multi-judge debate frameworks for high-stakes evaluations.
