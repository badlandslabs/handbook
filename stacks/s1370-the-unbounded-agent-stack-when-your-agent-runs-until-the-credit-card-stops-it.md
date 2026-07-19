# S-1370 · The Unbounded Agent Stack — When Your Agent Runs Until the Credit Card Stops It

Agents consume tokens at every step: planning, executing, verifying, retrying. Unlike traditional software where execution either succeeds or crashes with a stack trace, an agent can fail silently — returning HTTP 200 while hallucinating, looping on a misformed stop condition, or compounding errors into a budget event that nobody notices until the billing email arrives. The gap between demo-ready and production-ready agentic systems is largely a guardrails problem.

## Forces

- **Agents are expensive by design.** A chat session uses a few thousand tokens. An agent planning, executing, verifying, and retrying a multi-step task uses multiples of that — multiplied by every step. Two agents with identical accuracy can differ 50x in cost (3 focused calls vs. 40+ with redundant loops). [jobsbyculture.com/blog/ai-agent-evaluation-guide-2026](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)
- **Failure looks like success.** The most dangerous agent failures return HTTP 200, complete without raising exceptions, and produce confident nonsense. Traditional try-catch blocks don't catch a reasoning chain that produces the wrong answer — only a semantic guardrail does. [preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)
- **App-level guardrails drift.** Teams using CrewAI or LangChain callbacks to implement budget handlers find these drift from actual agent behavior as the agent evolves — they require independent testing and generate events invisible to the observability layer. [forum.langchain.com](https://forum.langchain.com/t/system-design-why-in-app-budget-handlers-fail-in-production-multi-agent-systems/4082)
- **The 3 AM problem.** A kill switch requires a human to notice and act. Production incidents happen at 11 PM, when nobody is watching. An agent running on a weekend loop accumulates costs until Monday morning's billing email. [weesec.com](https://www.weesec.com/en/articles/ai-agent-cost-runaway-guardrails.html), [waxell.ai](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)

## The move

Build runtime guardrails as first-class infrastructure, not application code.

**Budget enforcement at the runtime layer:**
- Hard max steps or max tokens per run — abort unconditionally, not after a callback
- Per-tool timeouts alongside per-run deadlines — a stuck browser automation step shouldn't block the entire agent
- Spend caps enforced by the runtime, not injected handlers — the difference between "catches most cases" and "actually stops"

**Circuit breaker pattern:**
- Open after N consecutive failures or when error rate exceeds a threshold
- Three states: CLOSED (normal), OPEN (block calls), HALF-OPEN (test with limited traffic)
- Configurable reset behavior — do not reopen silently; surface the state to observability

**Cost-per-task tracking as a reliability signal:**
- An agent requiring 40+ steps to complete a task is usually looping, not working harder
- Trajectory length is a better production signal than pass rate alone [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)
- Track: tokens consumed per task, number of tool calls, retry count, step-to-success ratio

**Semantic output validation:**
- Check not just whether the tool call succeeded (HTTP 200) but whether the output is semantically correct for the task
- Use a lightweight grader model to verify tool outputs before the agent acts on them
- This catches the "confident nonsense" failure mode that return-code checks miss

**Guardrails as platform primitives:**
- OpenAI Agents SDK provides first-class guardrail primitives (input, output, and tool-level) built into the runtime [openai.github.io/openai-agents-python/guardrails](https://openai.github.io/openai-agents-python/guardrails)
- Prefer runtime-enforced limits over application callbacks — they survive agent code changes and are auditable
- Bespoke circuit breakers maintained outside the agent stack drift from agent behavior and generate events invisible to the observability layer [waxell.ai](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)

## Evidence

- **Case study:** A multi-agent LangChain system entered a retry loop and ran undetected for 11 days, accumulating $47,000 in API charges — discovered via monthly billing statement, not alerting. No per-agent spend limit, no runtime timeout, no alert. — [kognita.co](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **Incident report:** A Q1 2026 team burned €23,000 of Claude tokens in 4 hours when an agent began looping due to a misformulated stop condition (*"until you're satisfied"*). Detected Monday morning via Anthropic billing email. In 14 similar engagements since October 2025, two had comparable incidents. — [weesec.com](https://www.weesec.com/en/articles/ai-agent-cost-runaway-guardrails.html)
- **Post-mortem:** A $437 overnight bill from a document-summarization agent entering a retry loop at 11 PM, running until 7 AM with thousands of identical failing tool calls. No alert fired. No threshold tripped. Fix: 20 minutes. — [waxell.ai](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)
- **Production eval guidance:** Anthropic recommends code-based graders (fast, objective, brittle), model-based graders (flexible, non-deterministic), and human graders (gold standard, expensive) — and tracking trajectory length as a signal separate from pass rate. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Eval pipeline pattern:** Run 100–500 representative test cases on every PR that changes prompts or models; block merge if overall score drops >2% or any category drops >5%. Key metric: not "is this model good?" but "is this model better than what we have in production for our use case?" — [aidev.fit](https://aidev.fit/en/ai/llm-evaluation-benchmarks.html)

## Gotchas

- **Max iteration callbacks in LangChain/CrewAI are app-level, not runtime-level.** They execute after the agent decides to continue, which means they can miss the loop's early iterations and require independent maintenance. The observability events they generate are invisible to the runtime monitoring stack.
- **Retry logic amplifies costs, not just failures.** A simple retry-with-backoff on a flaky API can compound if the agent retries the same failing approach with the same wrong assumptions. Add a "try a different approach" branch after N retries, not just a retry counter.
- **Endpoint scoring (pass/fail on final output) misses 20–40% of regressions.** An agent can reach the right answer through a reckless path — wrong tool first, lucky recovery, ignored constraints. Trajectory-level scoring catches these. [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)
- **Context accumulation is a silent cost multiplier.** As the conversation grows, every subsequent LLM call includes the full history. Long-running agents can accumulate thousands of tokens per turn without obviously looping — monitor context window utilization, not just step count.
