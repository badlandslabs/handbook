# S-1038 · Failure Handling for AI Agents

Agents fail in ways that crash logs don't show. An agent can loop for 35 minutes producing nothing, silently corrupt every downstream step with a wrong tool argument, or burn $24.88 of real money before you notice. The failure modes are qualitatively different from traditional software — and so are the remedies.

## Forces

- Agents succeed technically (HTTP 200) while failing semantically (hallucinated results, confident nonsense) — traditional try/catch misses everything that matters
- A single bad output from step 2 silently corrupts steps 3 through N — failures cascade invisibly
- Autonomous operation means nobody is watching when it breaks — by the time you notice, hours of damage may be done
- Garbage in early steps snowballs into worse garbage later, hiding the root cause
- Cost accumulation during loops means failures are not free — you pay for every wasted token
- Multi-agent delegation introduces loops between agents and task drift at every handoff

## The Move

Build a layered defense system: classify failures by type, apply the right recovery strategy to each, and cap what each failure mode can cost you.

### Classify failures into four types, each requiring different handling

| Type | Example | Strategy |
|------|---------|----------|
| **Transient** | Rate limit (429), timeout, 503 | Retry with backoff |
| **Semantic** | Malformed JSON, wrong tool, schema violation | Re-prompt or fallback to human |
| **Validation** | Tool output looks valid but fails a business rule check | Reject and retry with stricter prompt |
| **State** | Stale data treated as current, context overflow | Reset or truncate context |

### Layer recovery mechanisms

- **Retry with backoff** for transient failures: exponential backoff (e.g., delay × 2^attempt) for API rate limits; linear backoff for predictable short blips. Cap total attempts.
- **Fallback paths** via conditional edges: when a node fails, route to a fallback node instead of crashing the graph. LangGraph and CrewAI both support this via `if_error` conditional routing.
- **Circuit breakers** for cascading failures: after N consecutive failures on a dependency, stop calling it and return a safe default. Set per-topic thresholds — aggressive for irreversible actions (fail-closed), lenient for read-only operations.
- **Loop detectors**: track `tool_history` and `total_tool_calls`. Trigger a circuit break after MAX_CONSECUTIVE_SAME_TOOL (commonly 3) or MAX_TOTAL_TOOL_CALLS (commonly 15–25). LiteLLM supports `max_iterations` (e.g., 25) and `max_budget_per_session` (e.g., $5.00) at the session level.
- **Supervisor pattern** for multi-agent systems: a parent agent monitors child agent outputs and can halt delegation when failures accumulate. Prevents the delegation-loop failure mode where agents ping-pong tasks indefinitely.

### Enforce hard resource limits

- Set `timeoutSeconds` at minimum 1200 for non-trivial tasks — the default 300 causes silent death spirals where tasks complete 80% but produce nothing.
- Configure per-session spend caps: `$5.00/session` is a common starting point.
- Set tool call validation gates before execution: reject path traversal attempts, unreasonable timeouts (cap at 300s), and calls to undefined functions.

### Detect silent failures through observability

- Log every tool call: input arguments, output, duration, token cost. Treat absence of progress (same tool called N times with similar args) as a failure signal.
- Validate tool outputs against expected schemas before passing them downstream. Don't let hallucinated tool results propagate silently.
- Track context window utilization — long-running agents accumulating context until the model halts is a common failure mode.
- Alert on: breaker-open rate, fail-open counter, session cost approaching budget cap.

## Evidence

- **HN Ask HN (marvin_nora):** Documented 5 real failure modes from 2 weeks of unsupervised agent operation — auto-rotation costing $24.88, documentation trap producing 500KB instead of execution, static numbers treated as current for days, and an implementation gap where bugs were found but never fixed. — [HN Thread](https://hn.nuxt.dev/item/47112543)
- **Zylos Research (2026):** Multi-agent failure breakdown: 42% specification failures, 37% coordination breakdowns, 21% verification gaps. Notes agents may "silently loop for 35 minutes, spawn redundant subprocesses contending for shared resources, accumulate context until the model halts, or take irreversible actions before a human can intervene." — [Zylos Research](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **DEV Community (Midas Tools):** A practitioner running 24/7 agents on emails, content, and code found that a 300-second default timeout caused tasks to silently die at 80% completion — "6 hours of work that produced zero results." Fixed by setting `timeoutSeconds: 1200`. — [DEV Community](https://dev.to/midastools/5-things-that-break-when-you-run-ai-agents-unsupervised-and-how-to-fix-them-32ip)
- **CrewAI failure patterns (Vex):** Multi-agent workflows exhibit delegation loops between agents, hallucinated tool outputs propagating unchecked between agents, and task drift where agents reinterpret objectives at each handoff. — [Vex / CrewAI](https://www.tryvex.dev/learn/error-handling/crewai)
- **LiteLLM agent budgets:** Supports `max_iterations: 25` and `max_budget_per_session: 5.00` with session-level tracking via `session_id`. Counters expire after 1 hour by default. — [LiteLLM Docs](https://docs.litellm.ai/docs/a2a_iteration_budgets)

## Gotchas

- Retrying semantically wrong outputs with the same prompt just produces the same wrong output — exponential backoff doesn't help schema violations; you need a different prompt or a human in the loop
- Circuit breakers for irreversible actions must be **fail-closed** (stop the action); for read-only operations they can be **fail-open** (return a safe default)
- Loop detectors that only check for repeated tool names miss the case where an agent cycles through 3 different tools in the same bad pattern — track argument fingerprints too
- Session-level cost caps are reset-per-session, so a compromised agent can spawn multiple sessions; pair with global spend monitoring
- Timeout misconfiguration is the most common silent killer — tasks appear to complete but produce nothing because they were killed before finishing
