# S-2690 · The Agentic Harness Anatomy Stack

Your agent scores 96.9% on SWE-bench Verified. You ship it. Monday morning, it starts routing invoices incorrectly — systematically, plausibly, with no error logs, no alerts, and no indication that anything is wrong. The benchmark wasn't lying. It was measuring the model. The failure was in everything around it.

**Agent = Model + Harness.** If you are not the model, you are the harness. A solid model with a great harness beats a great model with a bad harness — and in 2026, this is no longer a controversial claim. Both Anthropic and OpenAI have published that infrastructure improvements outperformed model improvements for production reliability. The EU AI Act's high-risk obligations landed on August 2, 2026, making formal harness accountability legally mandatory for deployed agents.

The harness is the operating system of an AI agent. It is not the model, the prompt, the tool, or the framework. It is the structured runtime that turns a language model into a system that can be trusted, stopped, observed, and held accountable.

## Forces

- **The demo-to-production gap is a harness gap.** Every agent that fails in production with "it worked in testing" failed because the harness was not tested — only the model was. Tool registry mismatches, sandbox boundary violations, missing observability hooks, and ungoverned subagent spawning do not appear in eval suites.
- **The EU AI Act makes harness accountability mandatory from August 2026.** High-risk AI systems must demonstrate oversight mechanisms, traceability, and human-in-the-loop controls. "We didn't build a governance layer" is no longer an engineering choice — it is a compliance gap. MCP servers used by agents to take real-world actions are classified under Article 9 data governance requirements.
- **Most teams know the harness is important but don't have a taxonomy for it.** When you ask engineers "what makes your agent reliable?" you get vague answers about "good prompting" and "careful tool design." The harness has anatomy — ten distinct components that can each be designed, measured, and improved independently.
- **Framework choice is not harness design.** Picking LangGraph versus CrewAI versus writing a custom agent loop is the easy part. What actually determines production reliability is what sits inside the loop: the hooks, the sandbox, the permission model, the eval loop, the memory architecture. These are invisible in demos and fatal in production.
- **The Ratchet Principle: every line in the system prompt must trace to a past failure.** System prompts that contain generic instructions ("be careful with deletions") degrade over time. System prompts that contain specific, failure-derived rules ("never run `rm -rf` without a confirmation step") improve with every incident. The harness's system prompt layer is not documentation — it is compiled incident response.

## The Move

The harness has ten anatomy components. Each one decides whether your agent reliably delivers, can actually be stopped, and meets the obligations that apply from August 2026.

### The 10 Harness Components

| # | Component | What It Decides |
|---|-----------|----------------|
| 1 | **System prompt & skills** | Every text the model sees on every call. Every line traces to a past failure. |
| 2 | **Tool registry** | What the agent can do. Ten focused tools beat fifty overlapping ones — overlap causes mis-selection. |
| 3 | **Sandbox** | Where the agent operates. Subprocess isolation, container boundaries, and network egress rules. |
| 4 | **Memory architecture** | What the agent remembers. Episodic (per-run), semantic (across-runs), and working memory must be explicitly partitioned. |
| 5 | **Subagent policy** | When the agent spawns child agents. Without explicit criteria, subagent spawning is a cost and reliability multiplier in the wrong direction. |
| 6 | **Hook system** | What runs on lifecycle events. `on_failure`, `on_tool_error`, `on_loop_detected` — each failure type needs a named hook, not a generic retry. |
| 7 | **Observability layer** | What you can see. OTEL spans, trace annotation, and semantic correctness sampling — not just token counts and latency histograms. |
| 8 | **Eval loop** | What you measure. Three layers: final-answer pass/fail, trajectory quality, per-turn correctness. Offline benchmarks are necessary but insufficient. |
| 9 | **Permission model** | What the agent cannot do regardless of what the model decides. Deterministic permission enforcement at the harness layer — not in the prompt. |
| 10 | **Context manager** | How context is allocated, compressed, and prioritized. HOT/WARM/COLD context tiers, with explicit eviction policies. |

### Hook Pattern: Failure-Derived Rules in the Harness

The key insight: **AGENTS.md accumulates rot.** Writing "be careful with deletions" in a documentation file does not prevent the agent from deleting the wrong files on the next run. Writing a deterministic hook does.

```python
# Hook system: every failure type gets a named handler
class AgentHarness:
    def __init__(self, model, config):
        self.model = model
        self.tools = ToolRegistry(config.tools).compile()
        self.sandbox = Sandbox(config.sandbox_policy)
        self.hooks = HookRegistry()
        self._register_lifecycle_hooks()

    def _register_lifecycle_hooks(self):
        # These are not prompts — they are runtime handlers
        self.hooks.register("on_destructive_tool", self._block_destructive)
        self.hooks.register("on_tool_arg_validation_fail", self._quarantine_tool)
        self.hooks.register("on_loop_detected", self._halt_and_escalate)
        self.hooks.register("on_context_overflow", self._compact_and_retry)
        self.hooks.register("on_permission_denied", self._log_and_inject_skill)

    def _block_destructive(self, event):
        # Deterministic: runs before the tool executes
        if event.tool in DESTRUCTIVE_TOOLS:
            raise PermissionViolation(
                f"Tool {event.tool} requires user confirmation — "
                f"harness rule derived from incident {event.incident_id}"
            )
        return event  # Pass through

    def _quarantine_tool(self, event):
        # Tool with bad schema: remove from registry, flag for review
        self.tools.disable(event.tool)
        self.hooks.emit("tool_quarantined", {"tool": event.tool, "reason": event.error})

    def _halt_and_escalate(self, event):
        # Loop detected: do not retry, do not continue
        self.hooks.emit("incident_logged", {
            "type": "loop",
            "tool_sequence": event.sequence,
            "steps": len(event.sequence)
        })
        raise LoopDetected(f"Agent looped {len(event.sequence)} times")
```

### Tool Registry: Focused Beats Comprehensive

Tool explosion — giving the agent access to everything it *might* need — is the most common harness antipattern. Each overlapping tool in the registry increases the probability of mis-selection, especially under token pressure when the tool descriptions get truncated.

```python
# Tool registry: curated, non-overlapping, versioned
class ToolRegistry:
    def __init__(self, capabilities: list[ToolDefinition]):
        self._tools = self._deduplicate_and_rank(capabilities)

    def _deduplicate_and_rank(self, capabilities):
        # Cluster by action type, pick the best tool per cluster
        clusters = defaultdict(list)
        for tool in capabilities:
            clusters[tool.action_type].append(tool)
        return [
            max(cluster, key=lambda t: t.reliability_score)
            for cluster in clusters.values()
        ]

    def compile(self) -> list[dict]:
        # Returns the minimal tool manifest for the agent's system prompt
        return [t.manifest for t in self._tools if t.is_production_ready]
```

### Permission Model: Enforced, Not Prompted

Prompt-level permissions ("do not delete records without confirmation") degrade under adversarial input. The harness permission model is deterministic enforcement at the infrastructure layer.

```python
# Permission model: deterministic gate, not prompt instruction
class PermissionModel:
    def __init__(self, policy: PolicyDefinition):
        self.rules = self._compile_rules(policy)  # [(action, condition) → verdict]

    def check(self, proposed_action: Action) -> Verdict:
        for rule in self.rules:
            if rule.matches(proposed_action):
                return rule.apply(proposed_action)
        return Verdict.ALLOW  # Default-deny only where defined

    def _compile_rules(self, policy):
        rules = []
        for clause in policy.deny:
            rules.append(DenyRule(clause.action, clause.condition))
        return rules
```

### EU AI Act Harness Accountability (from August 2, 2026)

For agents deployed in or affecting EU users, the harness must provide:

1. **Article 50 — Transparency records**: Every agent decision that produces a consequential action must be traceable — tool call, input args, output, and rationale logged.
2. **Article 9 — Data governance**: MCP servers that access EU personal data must enforce purpose limitation and data minimization at the harness layer, not in the prompt.
3. **High-risk classification** (Annex III): Agents used in employment decisions, credit decisions, or critical infrastructure require conformity assessment before deployment — the harness must support human oversight checkpoints.

## Receipt

> Verified 2026-08-15 — EU AI Act high-risk obligations took effect August 2, 2026 (13 days ago). MCP protocol reached de facto standard status in mid-2026 per multiple sources (47billion.com, futureagi.com). innobu.com published the 10-component harness anatomy framework in 2026. AgentMarketCap confirmed the SWE-bench validity crisis — 50% of benchmark-passing patches rejected by real maintainers (METR, March 2026). The sota.io EU AI Act compliance guide for MCP server developers (June 2026) maps the regulatory roles to MCP architecture components, confirming that harness-level accountability is now a compliance obligation, not an optional best practice.

## See also

- [S-1174 · The Scaffold Convergence Problem](stacks/s1174-the-scaffold-convergence-problem-when-frontier-models-cluster-within-1-point-and-the-real-engineering-is-in-the-harness.md) — model convergence means the real engineering is in the harness
- [S-1147 · The Hook-Injection Pattern](stacks/s1147-the-hook-injection-pattern-when-your-agent-learns-from-every-failure-and-never-makes-the-same-mistake-twice.md) — making harness failures compound into permanent improvements
- [S-2669 · The Reliability Surface Stack](stacks/s2669-the-reliability-surface-stack-when-your-agent-scores-97-percent-and-fails-one-third-of-the-time-in-production.md) — why single-run pass rates lie and what the reliability surface actually looks like
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the operational discipline that governs the harness in production
