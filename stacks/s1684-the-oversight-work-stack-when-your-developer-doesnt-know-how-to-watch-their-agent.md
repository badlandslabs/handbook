# S-1684 · The Oversight Work Stack — When Your Developer Doesn't Know How to Watch Their Agent

You gave your developer access to a coding agent. You told them to use it responsibly. Six weeks later they've shipped 847 pull requests, approved 312 without reading them, and delegated 14 database migrations the agent invented from whole cloth. Nobody caught it because the agent returned "success" every time. This is the **oversight work gap**: the distance between "giving an agent access" and "knowing what your agent actually did."

## Forces

- **Agents make natural-language delegation the primary interface — and natural language is a terrible specification mechanism.** Unlike a function signature or a design document, a prompt has no contract, no boundary, and no formal semantics. Developers can issue vague intents and not know they're underspecified until the agent's interpretation diverges.
- **Oversight is uncompensated cognitive labor that nobody trained developers to do.** Writing prompts feels like chatting. Approving a PR feels like rubber-stamping. The stakes are invisible until they aren't.
- **The agent's success signal and the system's actual outcome routinely diverge.** A task can complete from the agent's perspective (tool call succeeded, code wrote, test passed) while the system-level outcome is wrong (wrong feature, wrong schema, wrong customer, wrong behavior). The agent doesn't know the difference. Neither does the developer until a customer reports it.
- **Autonomy and oversight are in tension.** The more autonomous an agent, the more oversight surfaces it needs — but the cognitive overhead of overseeing a highly autonomous agent is often higher, not lower, than overseeing a scripted automation. Developers consistently underestimate this.

## The move

**Harness engineering** (Böckeler, Thoughtworks, April 2026) gives us the operational frame: the system that constrains, informs, verifies, and corrects an agent. **FAccT 2026 empirical research** (Dhanorkar, Passi, Vorvoreanu — Microsoft, arXiv:2606.05391v1) gives us the empirical frame: how developers actually do oversight work, and where they systematically struggle.

### The four forms of oversight work

Dhanorkar et al. interviewed 17 developers who use software agents daily. Four distinct oversight practices emerged:

**1. A Priori Control (preventative)**
Setting the conditions before the agent acts. Includes:
- Configuring autonomy settings (what the agent can do without asking)
- Deny lists (blocking specific tools, packages, or environments)
- Affirmative scopes (positive permission lists rather than blocking)
- Output constraints (max file size, restricted directories, no network calls)

This is the most tractable form of oversight — it's configuration, not judgment. But it's systematically underused: most teams set autonomy at "high" and hope for the best.

**2. In-Process Monitoring (concurrent)**
Watching the agent as it works. Includes:
- Real-time trace review (OpenTelemetry spans, tool call sequences)
- Token budget alerts (stop if cost exceeds threshold)
- Anomaly detection (Lemma, Galileo AgentStudio, Confident AI — detect drift/cycles/missing details automatically)
- Live Slack/PagerDuty alerts on semantic failures (the "200 OK but everything wrong" pattern)

Concurrent monitoring is where the natural-language gap bites hardest. Most monitoring tools report HTTP status, latency, and token count. They don't tell you whether the agent's interpretation of the task matched the developer's intent. That's a semantic failure that only trace analysis catches.

**3. A Posteriori Review (retrospective)**
Checking the agent's output after completion. Includes:
- Code review with agent-aware diff tools (don't just show the diff — show what the agent was asked, what tools it called, what context it retrieved)
- Test review (did the agent write meaningful tests or "all tests green" stubs?)
- Rollback readiness (can you revert this in one command?)
- Compliance audit trail (EU AI Act Article 14 requires human oversight measures with evidence — PR metadata isn't enough)

A posteriori review is the fallback. It's also the most expensive in human time — which is why teams skip it. The goal is to push as much oversight as possible upstream (a priori) and sideways (in-process), leaving a posteriori review for edge cases.

**4. Repair Work (corrective)**
Fixing what the agent did wrong. Includes:
- Identifying the class of failure (not just the instance) — was this a tool misinterpretation? A schema hallucination? An intent misread?
- Building a constraint or rule that prevents recurrence — this is the core feedback loop of harness engineering
- Updating the agent's context (AGENTS.md, deny lists, tool descriptions) so the next agent run doesn't repeat the mistake
- Retiring the agent from the task if the failure mode is structural (agents are bad at certain task types; knowing which is a skill)

The repair-to-rule loop is where oversight becomes infrastructure. Every developer incident becomes a harness improvement — a deny list entry, a test case, a constraint, or a tool description update.

### The natural language specification gap

Dhanorkar et al. identify one root cause that no tool solves directly: **natural language is underspecified by default.** A developer who says "refactor the auth module" has not specified what "auth" means, what "refactor" means, what "module" refers to, or what preservation constraints apply. The agent fills in the gaps — confidently, silently, and sometimes catastrophically.

The practical mitigation is **progressive disclosure**: decompose large tasks into smaller, verifiable units. Each unit should have a clear completion criterion before the next starts. This isn't waterfall — it's the same discipline used in iterative human code review, applied to agentic workflows.

### The progressive autonomy model

Don't give agents "high" or "low" autonomy as a global setting. Use a per-task autonomy model:

| Task Type | Autonomy | Oversight Mode |
|-----------|----------|---------------|
| Read-only analysis | High | A posteriori |
| Non-destructive write (docs, tests) | Medium | In-process monitoring |
| Destructive write (migrations, deletions) | Low | A priori + in-process |
| Production deployments | Requires explicit approval | All four forms |

```python
# Example: autonomy-gated agent invocation
def run_agent(task: Task, context: Context) -> RunResult:
    autonomy = get_task_autonomy(task.type)

    # A priori: check deny lists and scope before running
    violations = check_deny_lists(task, context.deny_lists)
    if violations:
        return RunResult(blocked=True, reason=violations)

    if autonomy == "low":
        # Instrument for concurrent monitoring
        with trace_span(f"agent.{task.type}", tags={"autonomy": "low"}):
            result = execute_with_approval_gates(task, [
                lambda r: r.cost < 0.50,           # cost ceiling
                lambda r: r.tool_calls < 20,        # iteration limit
                lambda r: not r.destructive,        # destructive flag
            ])
    else:
        result = execute_with_instrumentation(task)

    # A posteriori: always log for retrospective review
    log_for_review(result, task, context)

    # Repair: if failed, trigger harness improvement loop
    if result.needs_repair:
        queue_harness_improvement(task, result.failure_class)

    return result
```

## Receipt
> Verified 2026-07-26 — Sources: FAccT 2026 (Dhanorkar et al., Microsoft, arXiv:2606.05391v1, 17-developer interview study, ACM FAccT '26); Harness Engineering (Böckeler, Martin Fowler, April 2026); OpenAI Harness Engineering (OpenAI Blog, Feb 2026, 5-month agent-first experiment, ~1M lines, 3.5 PRs/engineer/day); Lemma (YC F25, silent semantic failure detection); Gartner (75% orgs hit by supply chain attacks in 2021 forecast exceeded by 2025 reality).

## See also
- [S-1307 · The Silent Failure Stack](stacks/s1307-the-silent-failure-stack-when-your-agent-returns-200-ok-and-everything-is-wrong.md) — the "200 OK but wrong" pattern this chapter's monitoring catches
- [S-1612 · The Agent Harness Stack](stacks/s1612-the-agent-harness-stack-when-your-model-is-excellent-and-your-agent-still-fails.md) — the technical harness layer (tools, retries, error handling) that complements oversight work
- [S-1329 · The Authorization Velocity Gap](stacks/s1329-the-authorization-velocity-gap-when-your-agent-runs-before-the-controls-know-it-exists.md) — the governance lag problem that a priori control tries to address
