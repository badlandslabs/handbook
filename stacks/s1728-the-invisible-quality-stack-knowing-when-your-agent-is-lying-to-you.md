# S-1728 · The Invisible Quality Stack — Knowing When Your Agent Is Lying to You

Your agent's dashboard shows green. Every trace completed. Every task resolved. Except the data is corrupted, the tool calls were wrong, and your user has already filed a complaint. The eval stack you're running only checks if the agent finished — not if it finished correctly. The gap between "completed" and "correct" is where agents quietly fail production, and where most teams have no instrumentation.

You reach for this when your eval suite passes but users still complain, when you track latency but not correctness, when you trust the agent's self-reported success, or when the difference between 90% and 60% task accuracy is invisible in your monitoring.

## Forces

- Agents are non-deterministic — same input, different tool-calling sequence each run. A score on one run means nothing without variance measured.
- Traditional unit tests don't apply — you can't assert `function(input) == expected_output` when the function is an autonomous loop.
- Eval sets age from the moment they ship. Every new production failure that isn't added back to the eval set widens the gap between lab performance and reality.
- The agent has no incentive to report its own failures honestly — it will describe a partially-correct result as "success" unless you define success rigorously.
- Observability without evaluation is theater: tracing every step matters only if you have a rubric that scores whether each step was right.

## The move

Measure trajectory and outcome on separate axes, build a regression suite from real production failures, and run a continuous eval loop that closes the gap between what the eval set covers and what the agent actually encounters.

**Trajectory vs. outcome metrics are not interchangeable.** Trajectory metrics score how the agent got there — tool selection correctness, reasoning step coherence, whether it called the right tool in the right order. Outcome metrics score the final result — did it answer the question correctly, did it resolve the user's issue. An agent can have excellent outcome accuracy and catastrophic trajectory behavior (calling unnecessary tools, hallucinating intermediate facts). An eval suite that only checks outcomes will miss this.

**Start with 50 golden traces, grow weekly from triage.** The LangChain State of Agent Engineering 2026 survey (n=1,340) found 57% of respondents have agents in production, but only 52% run offline evals. Among those who do, the most common failure mode is starting with too few test cases and never expanding. A practical starting point: 50 traces covering your core use cases, reviewed by a human annotator, with a pass/fail rubric. Add failing production traces to the eval set every week.

**Calibrate LLM-as-judge against human labels before trusting it.** An LLM judge that hasn't been validated against human agreement is measuring its own opinions, not your agent's quality. The practical threshold: achieve 85%+ agreement with human annotators on a shared sample before running the judge at scale. QA Wolf's analysis (Feb 2025) notes that golden datasets created by single annotators carry their biases into every eval — cross-annotator disagreement is common and often the signal you need.

**Run capability evals and regression evals as separate pipelines.** Anthropic's eval guide (Jan 2026) draws a sharp line: capability evals ask "what can this agent do well?" and should start at a low pass rate (the point is to measure progress up a hill). Regression evals ask "does the agent still handle what it used to?" and should pass near 100%. Teams that mix these objectives end up with evals that are too easy (failing to catch regressions) or too hard (giving a false impression that the agent is regressing when it's not).

**Use the three-level framework in sequence.** Level 1: unit-style deterministic checks — did the agent call the right tools with the right parameters? These are fast and cheap. Level 2: LLM-as-judge on a sample of traces — does the output meet quality criteria? These are slower but capture semantic correctness. Level 3: online evaluation on production traffic — sample 5-10% of live traces, run evaluators asynchronously, alert on threshold drops. LangSmith, Opik, and Langfuse all implement this pattern. The feedback loop: failing production traces get promoted to the offline eval set for targeted repair.

**Track the six drift modes, not just the score.** FutureAGI's production analysis (Apr 2026) identifies six distinct ways eval sets age: dataset drift (new user intents the set never covered), tool-API drift (vendor changed response schema), context drift (user data or domain shifted), distribution drift (request patterns changed), and tool-version drift (the tool the agent was tested against has changed). A single pass rate number hides all of this. Track pass rate by tool, by request type, and over time windows.

## Evidence

- **Anthropic engineering blog (Jan 2026):** Capability evals start low (targeting tasks the agent struggles with) while regression evals aim for near-100% pass rate. Running both types through the same pipeline obscures signal — "capability eval that regresses" means the agent got worse; "regression eval with 30% pass rate" means the eval is measuring the wrong thing. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **LangChain State of Agent Engineering (Jun 2026, n=1,340):** 57% of organizations have agents in production; 89% have some observability; only 52% run offline evals. For orgs with 10k+ employees, hallucinations and output consistency are the #1 quality concern — cited more than latency or cost. — [URL](https://www.langchain.com/state-of-agent-engineering)
- **FutureAGI production analysis (Apr 2026):** "Wrong tool selection" accounts for 23% of production failures — caught by trajectory metrics but invisible to outcome-only eval suites. "Silent wrong answers" (17%) are the most operationally dangerous: no exception thrown, wrong result acted on. The eval set ages the day it ships — new production failure modes not added to the offline set widen the gap predictably. — [URL](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)
- **Microsoft Azure AI Foundry (Jul 2026):** USR-8 rubric: behavior/style are separate eval axes. A simulator that coaches the agent when it misses a step (hiding regressions) is worse than one with low realism — it produces inflated scores while missing real failure modes. — [URL](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/before-you-ship-your-agent-a-five-step-path-to-evaluations-you-can-trust/4532311)
- **Langfuse evaluation guide:** Glass-box eval (accessing internal state — tool calls, reasoning steps) outperforms black-box (output-only) for agents. Trajectory accuracy — the sequence of correct actions — is a leading indicator of outcome quality. — [URL](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)
- **QA Wolf (Feb 2025):** Golden datasets curated by single annotators carry annotation bias. Real-world data variability causes overfitting to controlled eval conditions. Synthetic data generation can address scale but introduces the risk of the eval set diverging from production distribution. — [URL](https://www.qawolf.com/blog/ai-prompt-evaluations-beyond-golden-datasets)

## Gotchas

- **"Eval suite passes" is not the same as "agent works."** A regression eval at 98% pass rate means the agent still fails 2% of cases — multiplied across 1,000 daily runs, that's 20 failures per day, each potentially silent.
- **False confidence from observability without scoring.** Tracing every tool call and reasoning step is necessary but not sufficient. Without a rubric that scores each step, you can replay failures but not detect them in real time.
- **The LLM judge will agree with the agent too often on ambiguous cases.** Calibration against human labels is not optional — without it, the judge is measuring how confidently the agent was wrong, not whether the agent was right.
- **Single-turn metrics miss cascading failures.** A per-turn coherence score of 4.2 can coexist with the user abandoning the session on turn 3. Look at session-level completion, not turn-level quality.
- **Simulated users can coach the agent.** A user simulator that provides hints when the agent misses a step produces inflated eval scores. The USR-8 "steering" dimension catches this — behavior/style are separate axes and must be scored independently.
