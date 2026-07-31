# S-1895 · The Agent Failure Handling Stack — When Your Agent Keeps Running Past the Point of Usefulness

An agent fails in ways that look like success: it returns HTTP 200 while looping, calls a tool that doesn't exist confidently, or exits a retry cycle having burned 10x the budget on a problem that was never going to resolve. Traditional `try/catch` covers none of this. The failure modes that actually kill production agents — infinite loops, retry storms, silent hallucinated completions, cascading error amplification — are invisible to standard error handling. You need explicit, layered defenses: hard budget caps, failure taxonomy routing, circuit breakers, and graceful degradation.

## Forces

- **Agents fail non-obviously** — the most dangerous failure mode looks like success: the agent completes and reports "done" while having accomplished nothing or burned 10x budget
- **Retries compound differently than in traditional software** — each retry replays the full conversation context, turning a single flaky API call into exponential token amplification
- **Completion is not correction** — an agent can loop, retry, and re-retry while remaining equally wrong each time
- **Failure types require different handlers** — a rate limit (retry), a capability failure (escalate), and a policy violation (stop) need three distinct responses; treating them as one blob produces either over-retries or over-escalation
- **Naive error handling makes cascading failures worse** — a 429 response triggering 3 retries across a multi-step agent = 4x token amplification per step, compounding to 10–50x by the time the chain completes

## The move

**Five-layer defense stack, from cheapest to most expensive to execute:**

1. **Loop bounds as the first hard line.** Set max iterations (total step count), max consecutive same-tool calls (catches tool-specific loops), and max total tool calls (hard global budget). This is a physical execution ceiling — it stops the graph regardless of what the model wants to do. Default to conservative numbers (10–20 iterations) and tune upward once you have production data. The agent-loop-bound library (MIT, zero deps) exposes strict and relaxed modes with a callback hook for custom handling when the cap is hit.

2. **Classify failures before deciding how to respond.** Three buckets:
   - *Transient* — rate limit (429), provider timeout, brief network error. Retry with exponential backoff (start at 1s, cap at 60s, jitter ±20%).
   - *Capability* — malformed output, missing context, retrieval returns nothing useful, validation fails. Retries do NOT fix these. Route to a narrower path, simplify the task, or escalate.
   - *Policy* — the request violates safety or business rules. Never retry; escalate or stop closed.

3. **Circuit breaker per downstream dependency.** Track failure rates per API/tool over a sliding window (e.g., 5 failures in 60 seconds → open circuit). When open, skip calls to that dependency for a cooldown period rather than hammering a failing service. The AgentFuse project (HN "Show HN", 2026) specifically addresses this for LLM API calls, preventing runaway token costs from cascading failures. Without a circuit breaker, a single 429 can propagate into a full retry storm.

4. **Graceful degradation instead of hard failure.** Define a degradation ladder before deploying: primary model down → fallback model (smaller/cheaper) → simpler narrow-path handler → human escalation → safe default. A customer support agent running on a fallback model still resolves ~70% of queries correctly; one that errors out resolves zero. Crucially, carve out explicit opt-outs for safety-critical domains (medical, financial, legal) where degradation is not acceptable.

5. **Self-correction loop with explicit convergence criteria.** When the agent produces an output, feed it back through a critique step before accepting it. The loop runs: generate → critique → revise → re-check. Three valid convergence tests: critic-pass (the critic explicitly approves), delta-quality (quality score improved by ≥ threshold since last revision), or max iterations (cap at 1–3 revisions to control cost). Using a separate critic model breaks agreement bias at the cost of an extra model call; self-critique (the same model critiques itself) is cheaper but gentler. Bound the loop with a max-iterations counter in the agent state — this integrates cleanly with LangGraph's cycle handling.

## Evidence

- **Simon Willison (blog post, HN 284 pts):** "Designing agentic loops" — defines an agentic loop as "LLM running tools in a loop to achieve a goal," analyzes YOLO mode risks (bad shell commands, prompt injection, exfiltration), and advocates for careful loop design and sandboxing. — [simonwillison.net/2025/Sep/30/designing-agentic-loops](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/)

- **Tianpan.co (engineering blog, 2026):** "The Retry Storm Problem in Agentic Systems" — quantifies token amplification: naive 3-retry policy creates 4x token amplification per tool call, compounding to 10–50x across multi-step chains. Proposes layered defense: circuit breakers, conversation-level budgets, deadline propagation, honest degradation. — [tianpan.co/blog/2026-04-10-retry-storm-agentic-systems-cascading-failure](https://tianpan.co/blog/2026-04-10-retry-storm-agentic-systems-cascading-failure)

- **MukundaKatta/agent-loop-bound (GitHub, 2026):** Zero-dependency Python library implementing hard caps on agent iterations: `max_iterations`, `max_consecutive_same_tool`, `max_total_tool_calls`. Strict and relaxed modes with callback hooks. Readme: "A runaway agent loop is the bug that eats your budget at 3am." — [github.com/MukundaKatta/agent-loop-bound](https://github.com/MukundaKatta/agent-loop-bound)

- **r/LocalLLaMA (discussion, 5mo ago):** "Do Your Agents Ever Loop Forever?" — developer built a simulator that detects infinite loops by tracking step/time budgets and repeated tool-call patterns, and suggests practical fixes: add a finalizer step, dedupe keys, hard stop rules. — [reddit.com/r/LocalLLaMA/comments/1r7ooae](https://www.reddit.com/r/LocalLLaMA/comments/1r7ooae/do_your_agents_ever_loop_forever/)

- **r/AI_Agents (discussion, 5mo ago):** "Our AI agent got stuck in a loop and brought down production, rip our prod database" — first-hand account of an agent loop taking down a production database, illustrating the real operational risk of unbounded agent loops. — [reddit.com/r/AI_Agents/comments/1r9cj81](https://www.reddit.com/r/AI_Agents/comments/1r9cj81/our_ai_agent_got_stuck_in_a_loop_and_brought_down/)

- **Geodocs.dev (technical spec, May 2026):** "Agent Self-Correction Loop: Critique, Revise, and Converge" — formal spec covering three convergence tests (critic-pass, delta-quality threshold, max iterations), self-critic vs. separate critic model trade-offs, and cost/latency scaling. — [geodocs.dev/ai-agents/agent-self-correction-loop-spec](https://geodocs.dev/ai-agents/agent-self-correction-loop-spec)

- **LangChain docs + machinelearningplus.com:** LangChain's `max_iterations` parameter (default caps execution steps; `None` leads to infinite loop). LangGraph's `recursion_limit` as a hard fail-safe that physically halts the execution graph before runaway costs. Pattern: state counter increments each loop pass; router checks counter and routes to END when cap is hit. — [langchain-doc.readthedocs.io](https://langchain-doc.readthedocs.io/en/latest/modules/agents/examples/max_iterations.html) + [machinelearningplus.com/gen-ai/langgraph-cycles-recursion-limits-agent-loops](https://machinelearningplus.com/gen-ai/langgraph-cycles-recursion-limits-agent-loops)

## Gotchas

- **Setting max_iterations too low** — agents genuinely doing complex multi-step work will hit the cap and fail closed. Profile real task trajectories before setting the cap; start conservative and loosen based on data, not intuition.
- **Retrying capability failures** — the most common mistake. If the agent is producing malformed JSON because the schema is wrong or context is insufficient, more retries will just reproduce the same failure faster. Classify first, then decide to retry or escalate.
- **Ignoring the "same tool, consecutive" dimension** — a max-iterations cap of 50 still lets an agent call `web_search` 49 times in a row. Track same-tool consecutive counts separately.
- **Hard failure on model degradation** — treating every model outage as a hard error instead of a trigger for graceful degradation means a brief API hiccup turns into an outage. Define the degradation ladder before deploying, not during.
- **No callback or log on loop termination** — a loop-bound hitting its cap without logging what it was doing when it stopped means you have no signal for improvement. Hook the termination callback to record iteration count, tool calls made, and state at exit.
