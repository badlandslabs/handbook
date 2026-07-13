# S1029 · The Evaluator Stack: When Your Agent Quality Measurement Is the Real Failure Mode

You have agent traces, test suites, and an LLM-as-judge pipeline. You're confident in your quality metrics. Then a regression ships to production and you find out your eval suite had a 60% false-positive rate.

## Forces
- **Automated eval is cheap but biased** — LLM-as-judge costs 500x–5,000x less than human review, but every LLM judge has systematic position preferences, self-preference biases, and length conflations you haven't measured
- **Human review is reliable but doesn't scale** — practitioners report 74%+ of teams still rely primarily on human evaluation in production, which creates bottlenecks and doesn't catch regressions between review cycles
- **Agent failures are qualitatively different** — loops, tool call cascades, semantic hallucinations, and context-window traps don't surface in traditional test suites
- **Failure handling is often an afterthought** — most agent frameworks ship without circuit breakers, loop detection, or budget guards; the $400 overnight API bill is the standard origin story

## The move
Build a layered evaluation and failure-handling stack. Separate quality measurement (eval) from runtime protection (watchdog). Don't trust an eval pipeline you haven't audited for bias. Don't run agents in production without guards.

### Eval layer — measure quality without fooling yourself

- **Use LLM-as-judge with explicit bias mitigations**: apply order-flip averaging (run each pairwise comparison twice with reversed order, average the scores), use a different judge model than the agent model, and calibrate against a human-labeled gold set before trusting absolute scores
- **Track a bias audit ratio**: if your LLM judge agrees with humans less than 75% of the time on a calibration set, recalibrate the rubric or swap the judge model — don't ship
- **Run trajectory evals, not just output evals**: score the full sequence of tool calls and decisions, not just the final output; an agent can arrive at the right answer via wrong reasoning and fail on the next turn
- **Maintain a regression test suite via DeepEval or Opik**: define concrete test cases with deterministic expected outcomes for deterministic sub-tasks; these catch the regressions that LLM-as-judge misses on open-ended tasks
- **Gate production deploys on eval pass rates**: require ≥90% on deterministic test suite AND a human-reviewed sample of ≥20 trajectory evals before each deploy

### Protection layer — stop runaway agents before they cost money

- **Implement per-tool circuit breakers**: each external tool (search API, code executor, database) gets its own failure counter; after N consecutive failures, the circuit opens and the agent is notified to route to an alternative or escalate — standard circuit breaker patterns adapted for agents: token-aware thresholds (open after N tokens wasted, not just N failures), per-tool granularity, session-scoped state reset
- **Set hard budget guards**: maximum total cost per agent run, maximum steps per run, maximum context-window utilization percentage; all three are configurable and enforced by a watchdog layer independent of the agent loop
- **Implement loop detection via state fingerprinting**: hash recent tool-call sequences; if the same N-step sequence repeats M times within a run, trigger a halt and escalation — loop detection must be framework-agnostic (works with LangChain, CrewAI, AutoGPT, or raw API calls)
- **Log full trajectories for post-mortems**: every tool call, every LLM call, every decision point — not just user messages. Replay failed runs against a modified agent without touching production systems
- **Define confidence thresholds for human escalation**: when an agent's self-reported confidence drops below a threshold, or when a critical action (write, delete, send) is about to execute, pause for human review

## Evidence

- **Engineering blog — Zylos Research:** In multi-agent deployments, specification failures account for ~42% of failures, coordination breakdowns for 37%, and resource contention for 21%. Found that 86% of agent failures are recoverable with proper mechanisms — most agents lack them. Proposes supervisor pattern: a parent agent monitors child agent health, injects corrections, and can terminate and restart failed sub-agents — [Zylos Research, 2026-05-06](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **HN thread — Ask HN: How are you monitoring AI agents in production?:** Practitioners report common failure modes: no step-by-step visibility, surprise LLM bills from runaway loops, risky outputs undetected, no audit trail. Multiple solutions discussed including Lava (spend keys with hard limits, usage logging) and AgentShield (observability SDK). Incidents cited: DataTalks database wiped by Claude Code agent, Replit agent deleted data during code freeze — [Hacker News](https://news.ycombinator.com/item?id=47301395)
- **Technical blog — Vadim Nicolai:** LLM-as-judge has systematic biases: Claude 3.5 Sonnet rates its own outputs ~25% higher than human panels; GPT-4 gives itself a 10% boost; position preference causes verdict flips in 10–30% of pairwise comparisons when order is swapped. Most teams measure the cost savings and never measure the biases. Mitigation: order-flip averaging, different judge model, human-labeled calibration set — [Vadim's Blog, 2026-03-15](https://vadim.blog/llm-as-judge/)
- **DEV.to — George Konnaris:** Built agent-watchdog after hearing about a $400 overnight API bill from an agent stuck in an error loop. Pattern: loop detection via recent action fingerprinting, real-time budget guards on cost and step count, graceful halts with context preservation for post-mortem. Framework-agnostic design — [DEV.to, 2025-06-05](https://dev.to/george_konnaris_f9eb70683/i-built-a-circuit-breaker-for-ai-agents-after-hearing-about-a-400-overnight-api-bill-3hkk)
- **GitHub — Comet ML Opik:** Open-source evaluation platform with LLM-as-judge, trajectory tracing, online evaluation rules, and production monitoring dashboards. Used by teams doing continuous agent quality tracking. Includes agent-specific metrics: step count, tool call success rate, cost per trajectory — [GitHub comet-ml/opik](https://github.com/comet-ml/opik)

## Gotchas
- **LLM-as-judge without calibration is theater** — an uncalibrated judge can give 85% pass rates on outputs humans would rate as 40%. Always validate against a human-labeled sample before treating scores as ground truth
- **Step-count limits alone don't stop loops** — agents can take semantically different actions that all fail for the same underlying reason. Loop detection must be semantic (similar outputs/patterns), not just step-count based
- **Eval pass rate ≠ production quality** — an agent can score 95% on your eval suite and still fail on the 5% of real-world cases it wasn't tested against. Keep the test distribution aligned with production traffic patterns
- **Budget guards are not optional** — the $400 overnight bill story is not an edge case; it is the modal outcome for agents running unattended without hard limits. Set budget guards before the first production run, not after
