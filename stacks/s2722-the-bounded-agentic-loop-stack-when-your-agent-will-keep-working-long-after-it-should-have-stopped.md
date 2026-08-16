# S-2722 · The Bounded Agentic Loop Stack — When Your Agent Will Keep Working Long After It Should Have Stopped

You gave your agent a goal and a tool. It started working. The API calls kept coming. The tokens added up. Thirty-five minutes later, it was still going — not making progress, not failing, just running. This is the bounded agentic loop problem: agents don't naturally stop when they've lost the plot. They keep producing plausible next steps until something external forces them to quit. The loop that looked smart in demos is the loop that cost you $200 while you slept.

## Forces

- **Agents are designed to keep going.** The model is trained to find plausible next actions. Stopping feels like failure; continuing looks like diligence. Without explicit bounds, the loop ends only when the context window fills or the API key runs out.
- **Failure cascades compound exponentially.** A 10-step pipeline where each step has 85% reliability delivers only ~20% end-to-end success. Every extra step isn't additive work — it's multiplicative risk. Teams underestimate this because they test individual steps, not the full loop.
- **Multi-step failures are qualitatively different from API errors.** An API call that returns 500 is obvious. An agent that calls the same search tool eleven times with minor variations looks like normal execution — more tokens, more cost, more activity — until you read the transcript.
- **Convergence is invisible without instrumentation.** "Good enough" is not a stop criterion. Agents and developers both tend to stop too early (leaving unresolved issues) or over-refine (wasting compute on passes that change nothing). Neither is detectable without change-velocity tracking.
- **Bounded termination is a design requirement, not a safety add-on.** Practitioners who add max_iterations after their first runaway incident report that the default framework limits are either absent, misconfigured, or placed outside the actual feedback path.

## The Move

Design loop termination as a first-class constraint, not a catch-all safety net. The loop always terminates on a reason you chose, never on the model deciding it is finished.

**The five bound types — use at least three in parallel:**

- **Max round limit** — hard cap on loop iterations. Fallback for all loops; prevents runaway when all else fails. LangChain has `max_iterations`, LangGraph has recursion limits, OpenAI Agents SDK has maximum turn limits, CrewAI has `max_iter`. Set conservatively — teams report 3–10 rounds covers the vast majority of legitimate tasks, and rounds beyond that are almost always thrashing.
- **Token budget** — per-step and cumulative. Treat token budget like memory in a 1990s embedded system: budget every byte, evict aggressively, never assume the next call gets the same allocation. Caps both cost and context growth. Most production teams set step budgets at 8K–32K tokens and a hard total cap at 128K.
- **Wall-clock timeout** — absolute elapsed time ceiling. Bounds user-facing latency and catches loops where the model keeps producing short responses that accumulate without progress. Pairs well with a minimum-step requirement to avoid premature exits on fast failures.
- **Convergence detection** — detect when the loop is no longer making progress. Track change velocity across consecutive passes: output length delta, semantic similarity (embed the last two outputs and check cosine distance), or structural diff (count of modified fields in structured outputs). Stop when velocity drops below a threshold for N consecutive rounds. Microsoft's VS Code Advanced Autopilot ships a utility-model judge that reads the run transcript to decide loop completion, bounded by a maximum of three loops.
- **Tool call caps** — per-tool and per-step limits. Prevent individual tools from dominating the loop. A search tool called 11 times in a row is almost always a loop. An image generation tool called more than twice in a single turn is almost always a mistake. The Lava.so founder reported losing $200 from a single agent loop; he built per-tool AI budget controls as a result.

**The termination hierarchy:**

```
if stop_reason == "goal_achieved": return result
elif round_count >= max_rounds: escalate_or_return(summary + "round_limit")
elif token_count >= token_budget: escalate_or_return(summary + "token_limit")
elif elapsed >= wall_clock_limit: escalate_or_return(summary + "timeout")
elif not_converging(convergence_signal, window=3): escalate_or_return(summary + "no_progress")
else: continue loop
```

**Escalation, not silent death:** When a bound fires, return a structured result with `termination_reason`, a summary of what was accomplished, what was not, and suggested next steps. Don't just crash. A $0.30 loop that returns "ran out of rounds after step 4 of 10; recommend human review of steps 5-10" is infinitely more valuable than silence.

## Evidence

- **Engineering blog (aiarch.dev):** "A bounded agentic loop is an autonomous tool-using loop with hard, explicit limits on how far it can go before it must stop or hand off. The loop always terminates on a reason you chose, never on the model deciding it is finished (or never deciding at all)." Documents all five bound types with production implementation notes — https://aiarch.dev/patterns/bounded-agentic-loop
- **Research brief (Zylos Research, 2026):** A 10-step pipeline with 85% reliability per step yields only ~20% end-to-end success. Multi-agent specification failures account for ~42% of failures, coordination breakdowns for ~37%, and verification gaps for ~21%. "An agent may silently loop for 35 minutes, spawn redundant subprocesses that contend for shared resources, accumulate context until the model halts, or take an irreversible action before a human can intervene." — https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery
- **HN Show HN (LoopGain, 2025):** "Stop agent loops with control theory, not max_iterations." A new tool explicitly addresses the failure mode where naive iteration caps (max_iterations) don't prevent loops because developers misconfigure them or place them outside the actual feedback path. — https://news.ycombinator.com/item?id=48919562
- **HN Show HN (Lava.so, 2025):** "I lost $200 from an agent loop, so I built per-tool AI budget controls." Concrete cost of unbounded per-tool iteration. — https://news.ycombinator.com/item?id=46991656
- **GitHub pattern (agentpatterns.ai):** VS Code's Advanced Autopilot mode uses a utility-model judge that reads the run transcript to decide loop completion, bounded by a maximum of three loops. Documents convergence detection patterns that pair with hard round caps rather than relying on either alone. — https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/convergence-detection.md

## Gotchas

- **Naive max_iterations doesn't work.** Developers may omit them, misuse them, set ineffective bounds, or place them outside the actual feedback path. The loop keeps running because the limit lives in a place the loop doesn't check. Audit your framework's loop path and verify the bound fires, not just that it's configured.
- **Premature termination on fast failures.** If a tool fails immediately and returns early, a low round count can fire before you've given the agent a chance to recover or try an alternative. Set a minimum step count (2–3 rounds) before bounds become active, paired with a minimum elapsed time if wall-clock limits are tight.
- **Convergence detection requires ground truth.** For code tasks with test harnesses, PASS/FAIL gates solve stop conditions cleanly. For prose, specs, and design documents, you need explicit change-velocity tracking because no machine-checkable gate exists. Don't assume the absence of an error signal means progress.
- **Tool call caps must account for legitimate retry.** A tool that fails transiently should retry 1–2 times before the cap fires. Design your cap as "consecutive failures" or "failures beyond step 2," not a flat total-count limit that catches legitimate retry logic.
- **Context accumulation is a silent budget consumer.** Token budgets often seem adequate until you realize the conversation history is growing with each loop. Track both per-turn token budget and cumulative context size — they hit different ceilings at different times.
