# S-2169 · The Failure Recovery Stack — When Your Agent Won't Stop Doing the Wrong Thing

Your agent failed. That's expected — 95% one-shot success sounds great until you're running a 10-step workflow, where compounded reliability means only 20% of runs complete cleanly. The real problem isn't that it failed. It's that it kept going: 47 messages deep, burning $47 in tokens, retrying the exact same action with more conviction, or silently returning an HTTP 200 that means nothing was actually done. The agent that fails fast is safer than the one that fails confidently.

## Forces

- **Compounded failure dominates long workflows.** A 10-step pipeline where each step has 85% reliability has an overall success rate of ~20%. Each additional step is a new failure surface. The agent isn't failing once — it's failing in a new way at every step.
- **Semantic failures outnumber technical ones.** Tool timeouts and parse errors are detectable with try-catch. The agent that calls the right tool with hallucinated parameters, the one that completes the task but changes the wrong file, the one that loops because the goal is ambiguous — none of these throw exceptions.
- **Bounded cost is a safety feature.** An unbounded retry loop is not resilience — it's a runaway process waiting to happen. The budget constraint isn't about saving money. It's the only thing that stops a confident failure from becoming a catastrophic one.
- **State loss is permanent and invisible.** When an agent crashes mid-workflow, you don't just lose progress. You lose the reasoning trail — the accumulated judgments about ambiguous inputs, the context that guided every decision. Restarting means re-sampling those decisions, which may produce different results.

## The move

**Build a progressive failure hierarchy with hard stops at every level.**

- **Self-correct first, but only if the fix is measurable.** Retry with a different parameter, rephrase the tool call, or switch to an alternative approach. Retrying the identical action is not self-correction — it's a loop. Log the fix attempt so subsequent retries don't repeat the same adjustment.
- **Hard-cap iterations and timebox every step.** LangChain's `max_iterations=10` with `early_stopping_method='generate'` has been reported to cut token costs by 92% in production. Set per-tool timeouts (15s default, configurable). When the cap hits, return partial progress, not silence.
- **Per-tool circuit breakers.** After 3 consecutive failures on the same tool, mark it unavailable for this session. The agent can still route around it with a fallback — it just can't keep hammering the same broken surface.
- **Checkpoint after every completed step.** Serialize the full state: accumulated decisions, reasoning log, current tool outputs, message history. On resume, skip completed steps and reload decisions verbatim. This prevents decision drift — the problem where a restarted agent re-evaluates an ambiguous input like "03/04/2026" and picks a different date, corrupting everything downstream.
- **Safety gates before execution, not after.** FailWatch and similar tools implement deterministic policy checks (numeric limits, regex patterns, allowlists) that intercept dangerous tool calls *before* they run — not as a prompt instruction, but as a code-enforced block. No LLM judgment call on whether a $10,000 refund should go through.
- **Route unrecoverable cases to humans with evidence attached.** Don't escalate blankly. Bundle the failure context — what the agent tried, what went wrong, what partial progress exists. The human reviewer should be able to evaluate the situation without re-running the investigation.

## Evidence

- **Blog post / analysis:** Coasty analyzed 14,000+ real agent sessions and found 95% single-tool success that cascades to 81% in 4-tool workflows (compounded). A 47-message retry loop — identical action repeated with increasing confidence — consumed $47 without recovering. — [coasty.ai](https://coasty.ai/blog/ai-agent-error-handling-recovery-why-your-agent-is-wasting-millions)
- **HN post:** FailWatch, a Show HN project, implements fail-closed circuit breakers that intercept agent tool calls before execution against deterministic policy rules (numeric limits, account allowlists, regex constraints). — [github.com/Ludwig1827/FailWatch](https://github.com/Ludwig1827/FailWatch) — [HN thread](https://news.ycombinator.com/item?id=46529092)
- **GitHub repo:** agent-checkpoint-resume demonstrates decision drift: when an agent crashes mid-workflow, restarting without state recovery re-samples ambiguous decisions (e.g. date format interpretation), producing different downstream results. The fix is serializing accumulated judgments at each step. — [github.com/crzyc0d3r/agent-checkpoint-resume](https://github.com/crzyc0d3r/agent-checkpoint-resume)
- **Research synthesis:** Zylos Research 2026 found specification failures account for 42% of multi-agent failures, coordination breakdowns for 37%, verification gaps for 21%. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)
- **GitHub repo:** agent-reliability-patterns implements confidence measurement and fallback strategies for reasoning failures — GitHub stars/usage unverified (new repo). — [github.com/hamley241/agent-reliability-patterns](https://github.com/hamley241/agent-reliability-patterns)

## Gotchas

- **Adding a prompt instruction is not a circuit breaker.** Telling an agent "do not retry more than 5 times" in the system prompt is not enforcement — the model can still ignore it. Hard limits must live in orchestration code, not in the prompt.
- **Bounded retries still need backoff.** Retrying immediately on a rate-limited API or a transient error doesn't help — it makes things worse. Use exponential backoff (start at 1s, cap at 60s) between retry attempts.
- **Checkpoint the reasoning log, not just the result.** Serializing outputs is table stakes. What you need to recover is *why* the agent made each decision — the accumulated context that would otherwise be re-derived differently on restart.
- **Per-tool circuit breakers don't help if the tool reports success while failing semantically.** A tool that returns HTTP 200 with an error message in the body still technically succeeds. Validate outputs, not just HTTP status codes.
- **Graceful degradation requires planning at design time.** You can't add a meaningful fallback path to a workflow you already shipped. Degraded-mode handling — what partial result to return, what to leave incomplete, how to mark it for human review — needs to be part of the workflow specification, not improvised at failure time.
