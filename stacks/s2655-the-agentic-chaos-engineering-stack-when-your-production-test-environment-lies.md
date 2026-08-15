# S-2655 · The Agentic Chaos Engineering Stack — When Your Production Test Environment Lies

Your agent passed every test. Your load tests showed sub-200ms p99 latency. Your integration suite is green. Three weeks into production, you discover it has been returning subtly wrong answers to 8% of requests — silently, continuously, with no 500 errors, no alerts, and no log anomalies. Your test environment never produced the right failure to catch the real one. This is the agentic chaos engineering problem: agents fail in ways your staging environment cannot reproduce.

## Forces

- **Agents fail differently than services.** A microservice failure is observable: exceptions, error rates, latency spikes. An agent failure is often a confident, fluent, HTTP-200 response that is simply wrong. Your observability stack sees nothing anomalous. Your test suite never triggered the failure because it never saw the specific input pattern that caused it.
- **Production traffic is the only honest test environment.** The gap between agent behavior in staging and production is structural. Staging can't reproduce: the drift in user query distribution over time, the cascade of tool failures in a real multi-agent pipeline, the token budget pressure that changes model behavior mid-session, or the subtle data distribution shift that turns an 85th-percentile query into a hallucination trigger.
- **Traditional chaos engineering doesn't capture agent failures.** Netflix Chaos Monkey kills instances and watches circuit breakers. What do you watch when an agent quietly starts ignoring tool errors? When it starts answering questions about data it hallucinated from prior turns? The blast radius of agent failures is behavioral, not architectural — and behavioral failures need behavioral fault injection.
- **The evaluation framework for agent reliability is still being built.** ReliabilityBench (January 2026) is the first chaos-engineering-style fault injection framework for LLM agents, evaluating 1,280 production-like episodes. AgentBreak and BalaganAgent bring chaos engineering tooling to agentic systems. But the field is nascent — most teams are still running unit tests on agents and calling it reliability engineering.
- **The compounding accuracy problem makes reliability engineering urgent.** At 90% per-step accuracy, a 5-step workflow succeeds only 59% of the time. At 95%, a 10-step pipeline still fails ~40% of the time. With organizations averaging 12 agents in production (Gartner, 2025), the failure surface grows combinatorially. You cannot tune your way out of compounding inaccuracy — you must engineer for controlled failure.

## The move

**Fault injection taxonomy for agents.** Unlike distributed systems chaos (kill a pod, corrupt a packet), agentic fault injection targets five failure axes:

| Axis | What to inject | Why it matters |
|------|---------------|---------------|
| **Tool failure** | Return errors, timeouts, partial responses | Agent must handle degraded tool availability |
| **Hallucinated tool output** | Inject plausible-but-wrong API responses | Tests whether agent validates tool returns |
| **Budget exhaustion** | Trigger mid-task token limit | Models behave differently under pressure |
| **Context corruption** | Inject contradictory prior context | Tests memory consistency and self-correction |
| **Model degradation** | Switch to a weaker model mid-pipeline | Tests graceful degradation |

**The AgentBreak pattern.** AgentBreak (GitHub: mnvsk97/agentbreak, MIT) lets you inject failures through plain-English directives — describe the fault you want to simulate and the tool you want to target. This lowers the bar for reliability testing: instead of writing custom chaos scripts, engineers describe the failure scenario and the framework handles injection. Supports tool timeout injection, response corruption, and budget depletion simulation.

**The BalaganAgent pattern.** BalaganAgent (GitHub: arielshad/balagan-agent) brings Gremlin-style chaos engineering principles to multi-agent systems: inject failures during development, not production. Targets shared state corruption during multi-agent coordination, tool-call failures in agent pipelines, and context window exhaustion mid-execution.

**The ReliabilityBench pattern.** ReliabilityBench (January 2026, arXiv:pending) introduces chaos-engineering-style fault injection as a standardized evaluation methodology for LLM agents. It defines a structured fault taxonomy and evaluation protocol for measuring how agents degrade under each failure type. The key metric isn't "did the agent crash" — it's "did task success rate remain above threshold under fault injection."

**The production shadow testing pattern.** Run the agent in production with a parallel shadow arm: for every real request, also run a version with injected faults and compare outcomes. The shadow arm never affects users but generates ground-truth reliability data. This is the only way to reproduce production distribution failures in a controlled setting.

**Build a failure playbook, not a resilience promise.** For each fault type, define: what the agent should do (graceful degradation, escalate, retry intelligently), what the user experience should be (transparent error vs. confident wrong answer), and what the observability signal should be (alert vs. silent). Test each entry in the playbook with injected faults before it matters.

## Example

```python
# AgentBreak-style fault injection (pseudocode)
from agentbreak import inject_fault, AgentUnderTest

agent = AgentUnderTest(model="claude-sonnet-4",
                       tools=[search_db, write_file, send_email])

# Inject tool timeout — agent should gracefully degrade
result = inject_fault(
    agent,
    fault_type="tool_timeout",
    tool="search_db",
    delay=30.0,  # seconds
    scenario="user asks about Q3 revenue during DB maintenance window"
)
assert result.task_success  # agent either re-queries or reports inability cleanly
assert result.confidence_score < 0.7  # agent expressed uncertainty, not false confidence

# Inject hallucinated tool output — agent should validate response
result = inject_fault(
    agent,
    fault_type="hallucinated_response",
    tool="search_db",
    fake_data={"revenue": "$99B", "quarter": "Q3"},  # deliberately wrong
    scenario="user asks Q3 revenue — DB returns corrupted data"
)
assert result.task_success  # agent caught the inconsistency
assert "validation" in result.reasoning_trace.lower()  # agent checked the response

# BalaganAgent-style chaos run
from balagan import ChaosRunner

runner = ChaosRunner(agent_pipeline=[planner, executor, reviewer])
runner.run(
    faults=[
        {"type": "context_exhaustion", "at_step": 3},
        {"type": "tool_failure", "tool": "write_file", "error": "PermissionError"},
        {"type": "model_degradation", "model": "claude-haiku-4", "at_step": 5},
    ],
    iterations=50,
    success_threshold=0.80
)
# Generates: failure_rate_per_fault_type, recovery_rate, task_completion_rate
```

## Receipt

> Verified 2026-08-14 — AgentBreak (GitHub: mnvsk97/agentbreak, 20 stars, MIT), BalaganAgent (GitHub: arielshad/balagan-agent, active development), and ReliabilityBench (January 2026) are real tools and frameworks. The fault taxonomy maps to production failure patterns documented in Trantor Inc.'s 2026 AI agent failure modes research (88% of agent projects never reach production; 40%+ of agentic projects cancelled by Gartner 2027 prediction). The compounding accuracy math is confirmed: 90% per-step accuracy → 59% task success for 5-step workflow. The Forge guardrail research (ACM CAIS '26) independently validates that adding reliability layers to agents produces measurable, large accuracy improvements — chaos engineering and guardrails are complementary reliability investments.

## See also

- [S-2640 · The Production Eval Gap Stack](s2640-the-production-eval-gap-stack-when-your-agent-passes-every-benchmark-and-fails-every-tuesday.md) — eval frameworks miss what chaos engineering finds
- [S-2653 · The Autonomous Recovery Stack](s2653-the-autonomous-recovery-stack-when-your-agent-retries-the-same-mistake-11-times.md) — what agents should do after a chaos-injected fault
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — behavioral degradation over time is a chaos engineering target
- [S-1005 · The AI SRE Stack](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-know-it-needs.md) — chaos engineering fits within AI SRE discipline
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-your-benchmarks-say-pass-but-production-breaks.md) — production evals + fault injection = complete reliability picture
