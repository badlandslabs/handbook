# S-910 · The Evaluation Gap Stack — When You Can See Everything and Know Nothing

You have traces for every agent decision. Latency histograms. Token counts per call. Error rates by tool. You have 89% observability coverage across the industry — but only 52% of teams running agents have evaluation frameworks that actually tell them whether the output was correct. You know the agent called the right tools. You don't know if it was the right sequence of tools. You can't tell if it solved the problem or just produced a confident wrong answer.

## Forces

- **Observability vs. evaluation** — Teams conflate tracing with measuring quality. You can watch an agent loop 47 times without knowing if looping was the right call.
- **Single-turn vs. trajectory** — LLM benchmarks check if the final answer is right. Agent evaluation must check if the path to the answer was sound — the right tools called in the right order with right arguments.
- **Non-determinism by design** — An agent can reach a correct answer via multiple valid execution paths. Assertion-based unit testing can't handle this. You need trajectory-level grading.
- **Eval expense vs. shipping pressure** — Writing good eval cases is slow. Product timelines reward shipping. Teams skip the eval work until something breaks in production.

## The move

The pattern that separates shipping teams from production-ready teams is layered evaluation across three levels simultaneously, with CI/CD gates that block regressions.

**Layer 1 — Unit-level tool call testing.** Test each tool in isolation: correct arguments, correct error handling, correct schema parsing. Mock external dependencies. This catches hallucinated tool calls (model calling a tool that doesn't exist) and malformed arguments before they reach production.

**Layer 2 — Trajectory-level workflow testing.** For each agent task, define the valid execution paths. A task that should require search → extract → write should fail if the agent skips directly to write. Use pass@k metrics (does the task succeed in k attempts) rather than pass/fail, because non-determinism means you need statistical confidence. The 4-D trajectory score (FutureAGI framework) evaluates: tool selection, argument extraction, result utilization, and plan coherence per turn.

**Layer 3 — Outcome-level grading with LLM-as-judge.** Use a separate, stronger model to score outputs on dimensions that are hard to code-assert: response quality, tone, whether the agent asked clarifying questions when appropriate. Hamel Husain's "Critique Shadowing" method (7-step iterative process) builds reliable judges by comparing the judge model's critique to domain expert critiques until they align. Critically: validate the judge itself before trusting its scores.

**The CI/CD gate.** Set per-dimension thresholds, not aggregate scores. An agent that scores 85% overall but drops to 40% on error recovery on a new prompt version should fail the gate — even if overall quality looks acceptable. LangChain's 2025 survey found that teams with eval gates in CI report significantly fewer production regressions.

**Offline + Online.** Offline eval on golden datasets catches regressions before deploy. Online eval on production logs catches the failure modes that only emerge under real usage — input distribution shifts, tool API changes, model drift. Neither layer alone is sufficient.

## Evidence

- **LangChain State of AI Agents survey (Nov–Dec 2025, n=1,340):** Only 52.4% of teams running AI agents have offline evaluation frameworks, despite 89% having observability tools. Quality concerns are the #1 barrier to wider adoption at 32%. — [https://www.langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)

- **RaftLabs AI Agent Testing Guide (May 2026):** 89% observability adoption vs. 52% eval adoption creates a "37-point gap" — teams can see traces but can't answer "was the output correct?" — [https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)

- **HackerNoon postmortem (Tijo Gaucher, May 2026):** Running OpenClaw agent on a $24/month droplet for 30 days. The agent itself was trivial — systemd retry logic, memory limits, and restart configuration determined whether it ran 30 days or 3. Total cost: ~$37/month, 11h 20m human time over 30 days. — [https://hackernoon.com/lessons-from-running-an-openclaw-agent-in-production-for-30-days](https://hackernoon.com/lessons-from-running-an-openclaw-agent-in-production-for-30-days)

- **Agentbrisk real-incident analysis (March 2026):** A Q3 2025 e-commerce refund agent with $500 no-review limit generated $1.2M in unauthorized refunds before detection. Root cause: no outcome-level eval on refund authority escalation behavior. The agent called the right tools correctly — it just wasn't constrained correctly. — [https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents/](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents/)

- **Ask HN discussion (2026, 43 comments):** Multiple practitioners confirmed that measuring "this is a good response vs. a better response" remains an unsolved problem in practice. Composite function calling and multi-turn reasoning make ground-truth comparison difficult. — [https://news.ycombinator.com/item?id=47319587](https://news.ycombinator.com/item?id=47319587)

- **Easton Blog LangGraph architecture guide (2026):** 60%+ of production LangGraph incidents stem from state management issues. Explicit TypedDict schemas between graph nodes surfaced latent bugs that had been silently reconciled by the model — caught only when something unrelated broke five steps later. — [https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture](https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture)

## Gotchas

- **LLM-as-judge has its own failure modes** — the judge model can be biased, inconsistent across score ranges, or gaming the rubric. Always validate the judge against domain expert labels using Hamel's Critique Shadowing method before deploying.
- **Aggregate scores hide regressions** — a drop from 82% to 79% looks minor. A drop in error recovery from 90% to 45% on a new prompt version is a production incident waiting to happen. Gate on per-dimension thresholds.
- **Golden datasets rot** — test cases built for v1 of your agent become stale as capabilities grow. Audit and refresh eval datasets quarterly, or they become noise that passes while real regressions go undetected.
- **Tracing is not evaluation** — you can have perfect observability (every tool call, every token, every latency) and still not know if your agent is producing correct outputs. The eval layer is separate and must be built deliberately.
