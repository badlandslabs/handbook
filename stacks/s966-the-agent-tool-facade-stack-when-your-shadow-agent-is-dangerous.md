# S-966 · The Agent Tool Facade Stack — When Your Shadow Agent Is Dangerous

You run your candidate agent in shadow mode: same live traffic, parallel execution, outputs discarded. But your shadow agent still calls Stripe. Still sends Slack messages. Still writes to the database. Shadow mode without a tool facade is a controlled experiment with one hand tied behind your back — except the hand is holding a live grenade.

The tool facade stack: replace every real tool with a controlled stub before shadow traffic hits the candidate agent. Capture what it *would* have done. Verify correctness without touching production state.

## Forces

- **Shadow traffic is meaningless if side effects are live.** A shadow agent that sends real emails or charges real cards is not shadow traffic — it's a second production system.
- **Facading only the write tools feels safe but isn't.** A shadow agent that reads production data and caches it, logs it, or exposes it through a return value has already leaked state.
- **The facade must behave identically to the real tool.** Any behavioral difference between facade and real tool causes the agent to route around the facade, triggering real calls, or worse — producing wrong outputs based on wrong tool responses.
- **Facade maintenance is a tax that grows with every new tool.** A tool facade stack requires a registry, a sync protocol, and an audit trail that most teams underinvest in until the first production leak.
- **Tool schemas change; facades drift.** A facade that returns the wrong type because the real tool's schema was updated silently corrupts the shadow agent's reasoning.

## The move

**1. Build a tool facade registry at agent build time.**

Before any shadow run, wrap every tool the agent can call with a corresponding facade. The registry maps `tool_name → facade_module`. Each facade implements the same interface as the real tool but records calls instead of executing them.

```python
class ToolFacadeRegistry:
    def __init__(self, mode: Literal["live", "shadow"]):
        self.mode = mode
        self.facades: dict[str, Callable] = {}
        self.call_log: list[ToolCall] = []

    def register(self, name: str, real_tool: Callable, facade_class: type):
        facade = facade_class(real_tool, self.call_log)
        self.facades[name] = facade

    def inject(self, agent_builder):
        # Replaces tool references in the agent's tool manifest
        for name, facade in self.facades.items():
            agent_builder.replace_tool(name, facade)
```

**2. Classify tools by side-effect severity.**

Not all tools need the same facade treatment. Classify each tool before wrapping:

| Class | Risk | Facade behavior |
|-------|------|----------------|
| `read-only` (search, fetch, lookup) | Low — read leaks only | Log + return synthetic response or cached real response |
| `idempotent-write` (update, upsert, flag) | Medium — may corrupt state | Log + return simulated success; mark as non-idempotent |
| `mutating` (send, charge, delete, trigger) | High — real consequences | Log + return simulated success; require explicit flag to enable |
| `financial` (payment, transfer, credit) | Critical — legal/financial exposure | Always facade; zero exceptions |

**3. The facade captures the call contract, not just the fact of the call.**

Record: tool name, arguments, timestamp, response (real or simulated), latency. This becomes the evaluation artifact.

```python
@dataclass
class ToolCall:
    tool: str
    args: dict
    timestamp: datetime
    response: Any
    was_simulated: bool
    latency_ms: float

class FacadeTool:
    def __init__(self, real_tool: Callable, log: list, simulate: bool = True):
        self.real = real_tool
        self.log = log
        self.simulate = simulate

    def __call__(self, **kwargs):
        record = ToolCall(
            tool=self.real.__name__,
            args=kwargs,
            timestamp=datetime.utcnow(),
            response=None,
            was_simulated=self.simulate,
            latency_ms=0,
        )
        start = time.monotonic()
        if self.simulate:
            record.response = self._synthetic_response(kwargs)
        else:
            result = self.real(**kwargs)
            record.response = result
        record.latency_ms = (time.monotonic() - start) * 1000
        self.log.append(record)
        return record.response

    def _synthetic_response(self, args: dict) -> dict:
        # Return a plausible response matching the real tool's schema.
        # For a Slack-send tool: {"ok": true, "ts": "9999999999.999999"}
        # For a Stripe-charge tool: {"id": "ch_shadow_xxx", "status": "succeeded"}
        raise NotImplementedError("Subclass must define synthetic response")
```

**4. Inject the registry at agent construction, not at call time.**

The facade must be in place before the agent's tool manifest is resolved. Late injection causes the agent to discover real tools through introspection and route around the facade.

```python
def build_shadow_agent(candidate_bundle: AgentBundle, facade_registry: ToolFacadeRegistry):
    agent = Agent(
        model=candidate_bundle.model,
        system_prompt=candidate_bundle.prompt,
        tools=candidate_bundle.tool_manifest,
    )
    # Inject facades before the agent resolves its tool list
    facade_registry.inject(agent)
    return agent
```

**5. Compare the call log against expected behavior, not just the final output.**

The facade's value is in the call log comparison: did the candidate agent call the right tools with the right arguments? This catches regressions that produce the right answer via the wrong path — which matters when the next request has slightly different parameters.

```python
def evaluate_shadow_run(shadow_log: list[ToolCall], golden_log: list[ToolCall]) -> EvalResult:
    differences = []
    for shadow, golden in zip(shadow_log, golden_log):
        if shadow.tool != golden.tool:
            differences.append(f"Tool mismatch: {shadow.tool} vs {golden.tool}")
        if shadow.args != golden.args:
            differences.append(f"Args mismatch for {shadow.tool}: {shadow.args} vs {golden.args}")
    return EvalResult(
        passed=len(differences) == 0,
        differences=differences,
        call_count=len(shadow_log),
        simulated_pct=sum(1 for c in shadow_log if c.was_simulated) / len(shadow_log) * 100,
    )
```

**6. Audit the facade itself for correctness.**

A broken facade is worse than no facade — it gives false confidence. Run a "facade smoke test" in CI that verifies each facade responds with a schema-matching object for a known input, and that the real tool is never called during shadow mode.

## Receipt

> Verified 2026-07-11 — Researched tool facade pattern from Zylos Agent-Native CI/CD (May 2026) and Cordum AI Agent Canary/Shadow Deployment (June 2026). Confirmed gap: s749 covers CI/CD pipeline and mentions shadow mode, s584 covers bundle versioning, s246 covers four-stage eval pipeline — none detail the tool facade registry architecture with severity classification and call-log comparison. Pattern synthesized from Zylos "tool facade pattern" description and Cordum "tool facade" implementation guidance, applied to agent deployment context.

## See also

- [S-749 · Agent-Native CI/CD](s749-agent-native-ci-cd-the-deployment-pipeline-that-prompts-and-models-need.md) — the broader deployment pipeline that makes tool facades necessary
- [S-584 · Agent Versioned Release Bundles](s584-agent-versioned-release-bundles.md) — what you bundle and promote as a unit
- [S-305 · Agent Trajectory Assertions](s305-agent-trajectory-assertions.md) — tool intercept for eval harness (different use case: harness instrumentation)
