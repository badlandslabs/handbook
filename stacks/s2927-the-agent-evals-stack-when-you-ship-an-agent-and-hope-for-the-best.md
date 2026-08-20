# S-2927 · The Agent Evals Stack — When You Ship an Agent and Hope for the Best

Your agent passed every internal test. It aced the demo, handled the happy paths, and impressed the stakeholders. Three weeks in production, a cascade of silent failures has eroded user trust. Nobody caught it because nobody was measuring what mattered — not whether the model sounded smart, but whether the agent actually completed the right task, via the right path, without hallucinating a tool or losing state.

## Forces

- **Agents fail non-deterministically.** A traditional test checks "does X produce Y?" An agent test must check "did the agent produce Y through a valid sequence of decisions?" — and that sequence varies run-to-run even with identical inputs.
- **Benchmarks don't transfer.** A model scoring 90% on HumanEval can still fail a multi-step purchasing workflow because it calls the wrong API when two endpoints have similar names. Constraint Decay research found agents lose ~30 percentage points on pass rates when structural constraints (architecture, database schema, ORM patterns) accumulate — bench performance ≠ production reliability.
- **Silent failures dominate.** The most dangerous failures return HTTP 200: hallucinated facts, wrong tool selection, state drift across steps. An agent that confidently calls the wrong function is harder to catch than one that crashes.
- **You need three levels of signal.** End-to-end task success (did it work?), trajectory efficiency (did it take a reasonable path?), and component-level diagnostics (which tool or sub-agent broke?) — and most teams only measure the first.
- **Evaluation compounds.** Each eval run becomes a regression suite, a drift detector, and a training signal for the next iteration. Without it, you can't tell if a prompt change fixed something or broke three other things.

## The move

Build a three-layer eval stack: **trace → diagnose → score**, and run evals continuously — not just before deployment.

### The diagnostic stack

1. **Trace every agent action** — tool calls, model responses, state transitions, and errors. This is the evidence chain. Without traces, you're debugging a black box.
2. **Evaluate at three levels simultaneously:**
   - **End-to-end (task success):** Did the agent complete the goal? Binary or rubric-graded. The ground truth.
   - **Trajectory-level (path quality):** Did it use the right tools in the right order? Did it recover from errors? Did it loop or get stuck?
   - **Component-level (diagnostic):** Which specific retriever, tool, or sub-agent failed? Isolate the breaking part.
3. **Use deterministic graders for exact things** — was the right tool called? Were the parameters valid? Was the output in the expected format? Fast, reproducible, no model cost.
4. **Use LLM-as-judge for subjective things** — did the response read naturally? Was the reasoning coherent? Is the tone appropriate? Use a separate (often smaller, faster) model to avoid circular evaluation.
5. **Build golden datasets from real traces.** The best eval cases come from production failures, not imagination. When something breaks in prod, write a test case for it before you fix it.
6. **Run evals in CI, not just pre-launch.** Every prompt change, tool modification, or model swap triggers the full suite. Catch regressions before they reach users.
7. **Monitor drift in production.** Task success rate, tool call accuracy, and cost-per-task degrade over time as models change or data shifts. Set thresholds, alert on violations.

## Evidence

- **Anthropic Engineering Blog (Jan 2026):** "Demystifying Evals for AI Agents" — defines the three eval levels (task/trial/grader vocabulary), recommends deterministic graders + LLM-as-judge combination, and emphasizes that eval value compounds over an agent's lifecycle as the suite grows. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **arXiv:2605.06445 — "Constraint Decay" (May 2026):** Systematic study showing LLM agents lose ~30 percentage points on assertion pass rates when structural constraints (architecture patterns, database dialects, ORM mappings) accumulate. Benchmarks rewarding functional correctness miss the structural fidelity that production requires. — [URL](https://arxiv.org/abs/2605.06445)

- **Prefactor Tech Blog (Jul 2026):** "Agent Evaluation in Production" — 62% of enterprises have agents live in production, 74% of those have rolled back or shut down agents due to quality failures. Identifies four production metrics: task success rate, trajectory cost (steps/tokens), failure mode distribution, and behavioral drift over time. — [URL](https://prefactor.tech/blog/agent-evaluation-in-production-what-to-measure-and-how-to-prove-it)

- **HN Ask Thread — "How are you monitoring AI agents in production?":** Real practitioners sharing failure modes and tools: surprise LLM bills from untracked token usage, risky outputs going undetected, no audit trail for post-mortems. Shared tools include AgentShield (observability SDK with tracing, risk detection, cost tracking), LangSmith (trace inspection, online evals, alerts), and custom dashboards. — [URL](https://news.ycombinator.com/item?id=47301395)

- **Langfuse production users:** 16,500+ GitHub stars; companies like Samsara, Twilio, and Khan Academy use it in production (self-hosted or hosted). Integrates tracing with offline eval datasets for the OpenAI Agents SDK and other frameworks. — [URL](https://www.datacamp.com/tutorial/langfuse)

- **OpenAI Evaluations:** SWE-Lancer benchmark (1,400+ real freelance software engineering tasks with end-to-end grading triple-verified by engineers) and structured eval tooling. OpenAI's 2025 developer roundup notes evals, graders, and tuning "matured into a more repeatable measure → improve → ship loop." — [URL](https://evals.openai.com/)

- **Google Cloud Agent Evaluation:** Structured four-phase workflow (Define → Run → Score → Refine) as part of the Gemini Enterprise Agent Platform. Emphasizes trace generation and automated scoring via Task Success and Safety metrics. — [URL](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation)

- **GitHub/TribeAI claude-evals:** Production eval framework for Claude Agent SDK workflows, hooking into `PreToolUse`, `PostToolUse`, and `SubagentStop` lifecycle events — evaluates tool selection, multi-step task completion, and cost efficiency, not just final output. — [URL](https://github.com/TribeAI/claude-evals)

## Gotchas

- **Don't evaluate only the final output.** A correct answer produced via a broken tool chain is still a liability — the next input might not be so lucky. Always inspect the trajectory.
- **LLM-as-judge has bias.** Models favor verbose, confident, structurally polished responses. Calibrate your judge against human ground truth, especially for edge cases.
- **Task success ≠ system success.** An agent can complete a task while violating business rules, leaking data, or calling an unauthorized tool. Define success criteria that include behavioral constraints, not just outcomes.
- **Constraint Decay is real.** If your agent operates in a structured environment (specific framework, DB schema, API contract), test with those constraints enforced — not just loose functional specs. A 90% benchmark score can mean near-zero production pass rate under full constraint.
- **Evals go stale.** As your agent evolves, eval cases become outdated. Budget time to refresh the golden dataset alongside the agent — a test suite that hasn't been updated in six months is measuring the wrong thing.
