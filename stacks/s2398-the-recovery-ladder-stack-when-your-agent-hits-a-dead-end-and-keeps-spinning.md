# S-2398 · The Recovery Ladder Stack — When Your Agent Hits a Dead End and Keeps Spinning

Your agent is mid-workflow. Step 3 of 10 failed — maybe a tool timed out, maybe the LLM output was unparseable, maybe the model confidently produced a hallucination that downstream code accepted silently. The agent retries. Fails again. Retries again. You're watching tokens burn and the pipeline isn't moving. No error log. No alert. Just silence and a growing bill. The fix isn't more retry logic — it's a bounded recovery ladder that matches the intervention intensity to the severity of the stuck state.

## Forces

- **The naive retry loop is a cost absorber, not a recovery strategy.** Retrying the same approach with the same inputs rarely unsticks a genuinely stuck agent — it just multiplies spend
- **Framework defaults are crash barriers, not stop conditions.** Hitting LangGraph's recursion limit or OpenAI's `MaxTurnsExceeded` means work is lost, tokens are spent, and nothing records why the agent failed to converge
- **The worst failures look like success.** HTTP 200, confident output, no exceptions — but the CRM record was created three times and the answer is a hallucination about a policy that doesn't exist
- **"Human handoff" as a first resort is both expensive and ineffective.** Field data from Alibaba's Taobao platform (680K chats, 2024) shows human takeover preserves quality for technical escalations but *degrades* it for emotional ones — workers reduce effort after taking over sensitive cases
- **Progress monitoring must distinguish loops from slow legitimate work.** A research agent downloading 50 sources will look like a loop to an iteration counter but is making real progress

## The move

Model failure recovery as a bounded ladder of escalating interventions. Each rung costs more and should only be tried if the previous rung failed to make progress.

**The 5-rung recovery ladder:**

1. **Nudge** — Re-send the last tool result with an explicit error prefix ("Previous attempt failed: timeout. Retry with a 10s timeout and a simpler query") and let the agent self-correct with the same approach
2. **Replan** — Provide a full state summary and explicitly ask the agent to propose an alternative approach before continuing. Don't just re-run the same prompt
3. **Escalate** — Switch to a more capable model (e.g., from GPT-4o-mini to GPT-4.5) or switch to a different tool for the same task. The capability change breaks the loop pattern
4. **Reset** — Clear the conversation history for this branch and restart the task from the last known good state with a tighter, more constrained prompt. Use a checkpoint if available
5. **Hand off to human** — Queue the task with full context (last N messages, tool outputs, error history) for human review. Do not present this as a fallback; design it proactively

**Detection before recovery:**

- Track a **progress metric** that only increases on real work (unique sources gathered, test failures resolved, records written). Token count and iteration count are poor proxies
- Set a **token budget** that hard-stops the run, not just an iteration cap — this catches slow loops that iterate slowly but burn tokens fast
- Implement **semantic loop detection**: log tool call signatures + results as hashes; fire when the same (tool, args, result_hash) tuple repeats within N steps
- **Validate outputs before proceeding** — catch hallucinated IDs, malformed JSON, or contradictory claims *before* they hit downstream systems. ~70% of hallucinated outputs are caught by output validation gates

**Error classification drives the recovery path:**

| Error type | Examples | Strategy |
|---|---|---|
| Transient | Rate limit (429), server error (500/503), timeout | Retry with exponential backoff (2^attempt delay + jitter) |
| Client | Bad key (401), context overflow (400) | Do not retry; alert and escalate |
| LLM quality | Hallucination, unparseable output | Validation gate → replan or escalate |
| Tool failure | API timeout, schema mismatch | Circuit breaker → fallback tool or provider |

**Circuit breaker pattern for LLM calls:**

- Track failure counts per provider/model
- After N consecutive failures (typically 5), open the circuit — fail fast instead of retrying
- Close after a cooldown period (60s baseline, configurable)
- For agents: also track cost per run and hard-stop when a session exceeds a budget threshold (AgentFuse and similar tools target exactly this failure mode)

**Checkpoint-and-resume for long-running agents:**

- Snapshot full channel state at each step boundary before the next step starts
- Durability modes: `sync` (written before next step — highest safety), `async` (written during next step — small crash window), `exit` (written only when graph exits — most efficient but least safe)
- Backend selection: Postgres/Redis for hot checkpoints, object storage for completed-run history
- Use run identifiers stable across sessions — in LangGraph, a missing `thread_id` means no persistence and no resume
- The `agent-resume` library (zero-dependency Python, JSONL store) provides a lightweight alternative: crash on item 47, resume from item 48

## Evidence

- **GitHub repo + blog post:** CAUM analysis of 80K AI agent sessions found 88.7% of loops fail to converge, with AUC=0.814 for loop detection — providing a quantitative benchmark for how prevalent the stuck-agent problem is in production — [HN discussion](https://news.ycombinator.com/item?id=47606768)
- **GitHub repo:** `MukundaKatta/agent-resume` — zero-dependency checkpoint-and-resume library for sequential agent jobs; crashes on item 47, next run resumes from item 48 — [GitHub](https://github.com/MukundaKatta/agent-resume)
- **GitHub repo:** `AbdulBasitA/agent-fuse` — local circuit breaker for LLM calls that prevents runaway bills from stuck agent loops; built after the author woke up to a drained OpenAI balance — [HN](https://news.ycombinator.com/item?id=46404312) / [GitHub](https://github.com/AbdulBasitA/agent-fuse)
- **ArXiv field study:** Wang et al. (2026) — 680,676 Alibaba customer service chats, randomized experiment on human-in-the-loop interventions. Human takeover preserves quality for technical escalations but *reduces* it for emotional ones because workers reduce effort on sensitive handoffs — [ArXiv](https://arxiv.org/pdf/2605.14830v1)
- **Engineering blog:** ValuestreamAI 2026 benchmarks — LLM API error rate is ~5% of all spans (60% from rate limits); multi-agent system failure rate in production is 41–86.7%; 70% of hallucinated outputs caught by validation gates; token budget guardrails reduce waste by ~40% — [ValuestreamAI](https://valuestreamai.com/blog/ai-error-handling-patterns-2026)
- **Pattern catalog:** Agentpatterns.ai — Stuck-Loop Recovery pattern with the full 5-rung ladder (nudge → replan → escalate → reset → human handoff), last reviewed 2026-06-29, maturity: adopted — [Agentpatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **Engineering blog:** Agent Native — Loop termination patterns for LangGraph, OpenAI Agents SDK, and CrewAI; documents the recursion limit discrepancy (docs say 25, default is 1000) and how framework crash barriers differ from proper stop conditions — [Agent Native](https://www.agentnative.dev/patterns/agent-loop-termination-pattern)

## Gotchas

- **Iteration caps are crash barriers, not stop conditions.** An agent hitting `MaxTurnsExceeded` or LangGraph's recursion limit has already wasted tokens and lost work. Proper stop conditions verify task completion, not just step count
- **Retry logic without idempotency guarantees creates duplicate side effects.** If a tool call succeeds but the response times out, retrying blindly creates duplicate CRM records, duplicate emails, duplicate GitHub issues. Make tool calls idempotent or track execution state before retrying
- **HTTP 200 is not success.** LLM APIs return 200 for hallucinated outputs. Validate structured outputs (JSON schemas, ID existence checks, consistency with prior steps) before committing side effects
- **Never retry 401 errors.** Re-authenticating after a bad key is correct; blindly retrying burns money and doesn't fix the credential problem
- **HITL as fallback is backwards design.** 40% of successful AI deployments use human-in-the-loop patterns — not as a last resort but as a proactive architectural layer. Designing it as a fallback creates inconsistent escalation criteria and surprised human operators
