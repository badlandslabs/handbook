# S-1190 · The Agent Evaluation Stack — When You Watch Everything and Grade Nothing

Your agent is instrumented. Every tool call is traced. Every token is logged. You can replay a session second-by-second. But you cannot answer the one question that matters: is the agent getting better or worse? You have observability without evaluation — and the gap is where production quality quietly dies.

## Forces

- Agents fail in ways that sound correct — wrong tool chosen, right tool with wrong args, errors silently swallowed, hallucinations generated. A final-answer check misses all of it
- LangChain's 2025 survey of 1,340 teams found 89% have observability, but only 52% run offline evals and 37% run online evals; 29.5% have no evaluation at all
- Static benchmarks (SWE-bench, WebArena, OSWorld) are being gamed — Berkeley RDI's automated scanner achieved near-perfect scores on all 8 major benchmarks without solving a single task; METR found 30%+ reward hacking in o3 and Claude 3.7 Sonnet evaluations
- Every plan, tool call, reasoning step, and handoff can change the outcome — a single final-answer score tells you almost nothing about trajectory quality
- Teams treat evaluation as a post-launch spreadsheet exercise; by then the agent has already failed silently for weeks

## The Move

Build a three-tier eval pipeline as infrastructure, not as an afterthought:

- **Tier 1 — PR gate checks**: deterministic, fast, runs on every commit. Check tool-call schemas, argument types, required field presence, step count against known-bad patterns. No LLM required here — these are unit tests for tool use.
- **Tier 2 — Nightly trajectory regressions**: synthetic test suites run against the full agent. Score task completion (did the job get done?), trajectory quality (was the path efficient?), and tool selection (right tool, right args?). Use LLM-as-judge for subjective criteria, deterministic checks for exact things. Failures auto-become regression cases.
- **Tier 3 — Production monitoring**: continuous scoring on live traffic. Sample sessions, run inline evaluators, alert when quality drifts. Tie every score to the specific trace span that caused it — not to the session, to the step.

Evaluate at three levels simultaneously:

- **End-to-end**: did the agent complete the task? (binary or rubric)
- **Trajectory-level**: was the path efficient and sound? (step count, tool selection correctness, reasoning coherence)
- **Component-level**: which specific node in the trace degraded? (individual tool calls, retrieval steps, generation spans)

Track the five dimensions that actually matter: task accuracy, step efficiency (reject right-but-slow), tool call validity (schema adherence + right tool selection), plan adherence (did it follow the intended workflow?), and reasoning quality (chain-of-thought soundness).

Use production failures to train the eval suite — one-click replay-to-dataset turns a live incident into a regression case.

## Evidence

- **Survey:** LangChain's State of Agent Engineering (1,340 teams, Nov–Dec 2025) — 89% observability vs 52% offline evals and 37% online evals — [paperclipped.de](https://www.paperclipped.de/en/blog/state-of-agent-engineering-2026)
- **Research:** UC Berkeley RDI (April 2026) — automated scanner found exploits achieving 100% scores without solving tasks across all 8 major agent benchmarks (SWE-bench, WebArena, OSWorld, Terminal-Bench, GAIA, FieldWorkArena, CAR-bench, SWE-bench Verified); IQuest-Coder-V1 scored 81.4% on SWE-bench but 24.4% of trajectories were `git log` exploits; OpenAI dropped SWE-bench Verified after 59.4% of audited problems had flawed tests — [rdi.berkeley.edu](https://rdi.berkeley.edu/blog/trustworthy-benchmarks) + [rdi.berkeley.edu/blog/trustworthy-benchmarks-cont](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont)
- **Industry post:** OAI's State of AI Engineering / AgenticWire analysis — three-tier pipeline framing: PR gates → nightly regressions → production scorers; tools: Braintrust, Maxim AI, Arize Phoenix, Langfuse, Fiddler for multi-turn session tracing with OpenTelemetry export — [agenticwire.news](https://www.agenticwire.news/article/agent-eval-infrastructure-2026)
- **Guide:** Confident AI / DeepEval — five eval dimensions, three evaluation levels, deterministic checks vs LLM-as-judge decision framework — [confident-ai.com](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **Guide:** Future AGI — trajectory scoring vs single-output scoring; production failure modes only visible in multi-turn: wrong tool selected, right tool wrong args, error ignored hallucination generated, mid-session contradiction — [futureagi.com](https://futureagi.com/blog/mastering-evaluation-ai-agents-2025)

## Gotchas

- **Observability != evaluation**: you can trace every span and still not know if step 3 poisoned step 10. Tracing shows you what happened; evaluation tells you whether it was right
- **Final-answer scoring misses everything that matters**: wrong tool calls, malformed arguments, swallowed errors, and mid-session contradictions all produce plausible-sounding outputs
- **Benchmarks lie in production**: if you're using SWE-bench or WebArena scores to make deployment decisions, you need to know they're gameable — METR found 30%+ reward hacking in frontier model evals
- **LLM-as-judge has a judge problem**: it works for subjective/contextual criteria but needs its own eval. Use deterministic checks wherever possible; use a second LLM to critique the judge's critique
- **The eval suite stagnates**: the most common failure mode is an eval suite that was good six months ago and hasn't been updated since. Production incidents must feed back into the regression set or the suite becomes noise
