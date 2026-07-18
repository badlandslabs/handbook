# S-1268 · The Agent Longevity Stack — When Your Agent Is Fine on Monday and Broken by Friday

Your agent scored 85% on its evaluation suite. You deployed it Monday. By Friday it was hallucinating tool calls. By the following Monday your on-call engineer had manually intervened six times. By day 14, accuracy had dropped to 60%, and nobody could explain why. The model hadn't changed. The agent had. This is the agent longevity problem — environmental poisoning of long-running AI agents — and it is the most underreported failure mode in production deployments.

## Forces

- **Agents accumulate environment, not just context.** Every session adds to the agent's memory store, tool catalog, and interaction history. None of this is bad in isolation — but the cumulative state slowly poisons decision quality in ways that never trigger an error log
- **The agent has no awareness of its own degradation.** A microservice that starts returning wrong answers is visible in dashboards. An agent that gradually gets worse at task resolution has no self-diagnostic signal — it reports high confidence while producing low-quality output
- **Long-running deployments amplify every small flaw.** A credential expiring in 30 days is a non-event in a 1-hour task. In a 6-week agent session, it's a silent failure that corrupts every downstream tool call. Time is the multiplier on every latent defect
- **Evaluation suites certify the agent at launch, not in week 3.** Benchmarks measure a snapshot. They say nothing about what the agent looks like after accumulating 50,000 tasks, three memory compaction cycles, and two tool API updates
- **The operating environment changes faster than the agent adapts.** Tool schemas evolve, credentials rotate, user query distributions shift, and RAG indices update — all without the agent knowing its assumptions are stale

## The move

### The four axes of environmental poisoning

**1. Memory accumulation and compaction corruption**

Agents that maintain persistent memory undergo periodic compaction — condensing older, lower-priority memories to free context space. Each compaction run risks losing critical context: safety constraints, task-relevant history, and learned patterns. Over weeks, memory becomes a degraded map of what the agent used to know, not what it needs to know.

**Signal:** Agent starts failing on task types it handled correctly in week 1. Tasks that share no surface similarity with earlier failures, but that depend on knowledge from the compacted memory.

**2. Credential and permission drift**

API credentials, OAuth tokens, and permission scopes expire or rotate. Long-running agents hold stale credentials long after rotation events, leading to silent failures: tool calls that return 401s the agent never reports, permissions that quietly restrict access to data the agent assumes it can read.

**Signal:** Tool calls succeed but return empty or partial data. Agent compensates by hallucinating填补 — filling gaps with plausible but incorrect values rather than surfacing the access error.

**3. Tool API and schema drift**

External tools evolve. A payment API changes a field name. A search API updates its response schema. A Slack MCP server ships a breaking change. The agent's tool descriptions were frozen at deployment time; the live tool is a different version.

**Signal:** Agent produces tool call arguments that match the old schema but fail against the new one. Retry loops that never succeed because the agent keeps calling with stale parameters.

**4. Interaction pattern pollution**

When the agent serves diverse users, it gradually trains on its own outputs embedded in downstream contexts. Previous agent responses become part of retrieval context, which feeds future responses. Without provenance tracking, the agent amplifies its own errors forward.

### The longevity monitoring stack

```python
import time
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class LongevityMetrics:
    session_age_days: float
    task_count: int
    memory_compaction_cycles: int
    tool_api_version: str          # tracked at deploy time
    credential_expiry_hours: float # time until nearest expiry
    hallucination_rate: float      # per 100 tasks (judge-verified)
    error_rate: float              # tool call failures
    accuracy_trend: float          # rolling 7-day vs 30-day delta

    def health_score(self) -> float:
        """Composite score. Below 0.7 = investigate immediately."""
        age_penalty = min(self.session_age_days / 30, 1.0) * 0.2
        cred_penalty = max(0, 1 - self.credential_expiry_hours / 720) * 0.15  # 30-day warning
        halluc_penalty = min(self.hallucination_rate / 10, 1.0) * 0.25
        accuracy_penalty = max(0, -self.accuracy_trend) * 0.3
        compaction_penalty = min(self.memory_compaction_cycles / 5, 1.0) * 0.1
        return 1.0 - (age_penalty + cred_penalty + halluc_penalty +
                      accuracy_penalty + compaction_penalty)

    def should_snapshot(self) -> bool:
        """Agent is degrading — capture trajectory for post-mortem."""
        return (
            self.health_score() < 0.7
            or self.accuracy_trend < -0.05   # 5% accuracy drop vs 30-day baseline
            or self.hallucination_rate > 5.0 # 5+ hallucinations per 100 tasks
            or self.credential_expiry_hours < 168  # < 7 days
        )

@dataclass
class LongevityMonitor:
    baseline_accuracy: float           # established in first 7 days
    tool_versions: dict[str, str]     # tool_name → version hash at deploy
    credential_expiry: dict[str, float]  # cred_id → expiry unixtime

    def check_environment(self, agent_fn: Callable) -> LongevityMetrics:
        now = time.time()
        age_days = (now - self.deploy_time) / 86400

        # Detect tool schema drift
        schema_drift = []
        for tool, original_version in self.tool_versions.items():
            current = agent_fn.get_tool_version(tool)
            if current != original_version:
                schema_drift.append(tool)

        # Detect credential expiry
        creds_near_expiry = [
            (cid, (exp - now) / 3600)  # hours remaining
            for cid, exp in self.credential_expiry.items()
            if exp - now < 30 * 86400  # < 30 days
        ]

        return LongevityMetrics(
            session_age_days=age_days,
            task_count=self.tasks_processed,
            memory_compaction_cycles=self.compaction_count,
            tool_api_version="; ".join(schema_drift) if schema_drift else "stable",
            credential_expiry_hours=min(h for _, h in creds_near_expiry) if creds_near_expiry else float('inf'),
            hallucination_rate=self.rolling_hallucination_rate(),
            error_rate=self.rolling_error_rate(),
            accuracy_trend=self.accuracy_trend_30d(),
        )

    def snapshot_and_reset(self, agent_fn: Callable):
        """Capture degraded state and reset to known-good baseline."""
        trajectory = agent_fn.export_trajectory()   # full session trace
        memory_dump = agent_fn.export_memory()       # current memory state
        self.deploy_time = time.time()
        self.compaction_count = 0
        # Re-fetch tool versions, re-authenticate credentials
        self.tool_versions = {t: agent_fn.get_tool_version(t) for t in agent_fn.available_tools()}
        self.credential_expiry = agent_fn.refresh_credentials()
        return {"trajectory": trajectory, "memory": memory_dump}
```

### The recovery protocol

1. **Daily health check.** Run `LongevityMonitor.check_environment()` on every agent session. Surface the health score as a first-class metric — not buried in logs
2. **Snapshot on degradation.** When `should_snapshot()` fires, capture the full trajectory and memory state before attempting recovery. The snapshot is your post-mortem data
3. **Reset, don't patch.** Don't try to surgically fix degraded memory. Reset to a known-good baseline and replay the agent's critical knowledge as fresh context. This is faster and more reliable than memory surgery
4. **Lock tool versions.** Pin tool API versions at deployment. Don't let external API updates silently break your agent mid-session
5. **Rotate credentials before 30-day expiry.** Proactive refresh beats reactive troubleshooting

## Receipt

> Verified 2026-07-17 — AgentMarketCap (Apr 2026) documents multi-week accuracy drops from 85% to 60% in unmonitored production agents. arXiv:2601.04170 (*Agent Drift: Quantifying Behavioral Degradation in Multi-Agent LLM Systems*, Jan 2026) establishes the foundational methodology. Stanford/UC Berkeley documented GPT-4 accuracy dropping from 84% to 51% between March and June 2023 with no version change. Zylos Research (Apr 2026) recommends longitudinal evaluation as the standard for production agent monitoring.

## See also

- [S-846 · The Reliability Surface Stack](s846-the-reliability-surface-stack-when-90-percent-passes-are-lying-to-you.md) — R(k,ε,λ) evaluation framework
- [S-370 · Agent Chaos Engineering](s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection for production hardening
- [S-541 · Agent Drift Detection](s541-agent-drift-detection.md) — behavioral regression detection
- [S-1002 · Memory Consolidation Debt](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — memory compaction failure modes
