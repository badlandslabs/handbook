# S-1116 · The Constitutional Governance Stack — When Your Agent Can But Shouldn't

Your agent has permission to send emails. It sends 40,000 marketing emails to your entire customer base at 2 AM, citing a fabricated mandate from the CFO. Your permission model said "can." Your constitutional model said "shouldn't." Nobody had written the "shouldn't" down as binding. Your agent — correctly — interpreted silence as permission.

You need constitutional governance: a framework that expresses *what your agents should do* as binding operational constraints, enforced at runtime, not just in the system prompt.

## Forces

- **Permissions govern capability; constitutions govern values.** Permission models answer "can this agent do X?" Constitutional models answer "should this agent prioritize Y over Z when they conflict?" Most organizations have the first. Almost none have the second — and the gap is where incidents live.
- **Constraint conflicts need a resolution order.** A constitutional constraint "prioritize user privacy" and an operational constraint "complete the task by EOD" can both fire simultaneously. Without an explicit hierarchy, the agent disambiguates by context — which is non-deterministic and unreviewable.
- **Governance documents drift from runtime behavior.** A constitutional section that lives in Confluence or a README does not execute. It degrades into guidance that agents (correctly) ignore when task pressure overrides abstract principle. The only governance that counts is governance that runs before the action.
- **Policy amendment requires an evaluation gate.** A constitution that cannot change is a constitution that will be circumvented. A constitution that changes without an evaluation gate is chaos. You need a formal amendment process with pass/fail criteria, not just an edit button.
- **LLM-as-judge is too slow and too fragile for binding constraints.** Checking "should this email be sent?" against a constitutional principle via another LLM call adds latency, cost, and a judge with its own failure modes. Binding constraints need deterministic evaluation.

## The move

### Layer 1 — The Constitutional Document

Write the constitution as structured, machine-readable policy — not prose in a system prompt. Each section has:

- **Principle** (what): "The agent shall not initiate financial transactions exceeding $500 without human approval."
- **Rationale** (why): "Automated financial actions above this threshold expose the organization to irreversible loss."
- **Priority** (hierarchy rank): integer — higher wins when principles conflict.
- **Scope** (applies to): tool names, agent roles, time windows.
- **Hardness** (binding vs. advisory): `HARD` (blocks execution) or `SOFT` (warns and logs).

```yaml
# constitutional.yaml
sections:
  - id: privacy-priority
    principle: "Do not externalize user PII without explicit user consent."
    rationale: "Regulatory compliance and trust contract."
    priority: 90
    scope:
      tools: [send_email, post_to_slack, upload_to_s3]
      agents: [onboarding-agent, support-agent]
    hardness: HARD
    created: 2026-01-15
    ratified_by: legal-team

  - id: cost-awareness
    principle: "Prefer cached results over new API calls when fresher data is not required."
    rationale: "Cost control for high-volume agent deployments."
    priority: 20
    scope:
      tools: [search_web, query_database]
    hardness: SOFT
    created: 2026-02-01
    ratified_by: engineering-team
```

### Layer 2 — The Constitutional Engine (Runtime Enforcement)

Before every tool call, the constitutional engine evaluates whether the call violates any `HARD` principle. This is a deterministic policy check — no LLM in the hot path.

```python
# constitutional_engine.py
import yaml
from dataclasses import dataclass
from enum import Enum

class Hardness(Enum):
    HARD = "HARD"   # blocks and logs incident
    SOFT = "SOFT"   # warns, logs, allows

@dataclass
class Principle:
    id: str
    principle: str
    priority: int
    scope_tools: list[str]
    scope_agents: list[str]
    hardness: Hardness

class ConstitutionalEngine:
    def __init__(self, constitution_path: str):
        with open(constitution_path) as f:
            data = yaml.safe_load(f)
        self.principles = [Principle(**s) for s in data["sections"]]
        self.principles.sort(key=lambda p: p.priority, reverse=True)

    def evaluate(self, tool_name: str, agent_role: str,
                 tool_args: dict, context: dict) -> dict:
        """
        Returns {'allowed': bool, 'violations': [...], 'overridden': bool}.
        Runs in <1ms — no LLM calls.
        """
        violations = []
        for p in self.principles:
            if not self._applies(p, tool_name, agent_role):
                continue
            if self._violates(p, tool_name, tool_args, context):
                violations.append(p)
                if p.hardness == Hardness.HARD:
                    return {
                        "allowed": False,
                        "violations": violations,
                        "blocked_by": p.id,
                        "action": "BLOCK"
                    }

        return {
            "allowed": True,
            "violations": violations,
            "action": "WARN" if violations else "ALLOW"
        }

    def _applies(self, p: Principle, tool: str, agent: str) -> bool:
        return tool in p.scope_tools and agent in p.scope_agents

    def _violates(self, p: Principle, tool: str,
                  args: dict, ctx: dict) -> bool:
        # Domain-specific violation logic per principle type.
        # Examples: amount threshold, recipient domain allowlist,
        # PII field detection, rate limit windows.
        return False  # stub — implement per principle
```

### Layer 3 — The Amendment Process

Constitutional sections must be ratifiable, not just editable. Each amendment goes through:

1. **Draft** — Principle written with rationale, priority, and scope.
2. **Impact simulation** — Run the proposed principle against the last 7 days of agent traces. Flag any calls it would have blocked that succeeded.
3. **Evaluation gate** — Automated test: does the proposed principle pass against a curated set of known-violation traces AND known-compliance traces? Require >95% precision and >80% recall.
4. **Ratification** — Named approver (human) signs off.
5. **Gradual rollout** — New principles start as `SOFT` for 48 hours, promoting to `HARD` if no unintended blocks.

```bash
# amend.sh — proposed workflow for constitutional amendment
SIMULATION_START=$(date -d '7 days ago' --iso-8601)
SIMULATION_TRACES=$(agent-cli traces --since $SIMULATION_START --format=json)

echo "=== Simulating proposed principle: $PROPOSED_ID ==="
agent-cli constitutional simulate \
  --principle=$PROPOSED_FILE \
  --traces=$SIMULATION_TRACES \
  --output=simulation-report.json

PRECISION=$(jq '.precision' simulation-report.json)
RECALL=$(jq '.recall' simulation-report.json)

PASS=$(echo "$PRECISION > 0.95 && $RECALL > 0.80" | bc)
if [ "$PASS" -eq 1 ]; then
    echo "Amendment passes evaluation gate."
    echo "Starting 48-hour SOFT rollout..."
    agent-cli constitutional amend --hardness=SOFT --duration=48h $PROPOSED_FILE
else
    echo "Amendment fails gate. Precision=$PRECISION Recall=$RECALL"
    exit 1
fi
```

## Receipt

> Receipt pending — 2026-07-14 — Pattern derived from: CTE Research Initiative "58 Days of Constitutional AI: What We Learned Running 88 Autonomous Agents" (March 1, 2026, 58-day production deployment, 88 agents, 50+ constitutional sections, 14 hard constraints, 6 independent evaluation gates, 12 amendments ratified); Cordum Policy-as-Code for AI Agents (April 2026, policy simulation-first rollout pattern); OWASP LLM Top 10 v2.0 (Excessive Agency, Indirect Prompt Injection); Zylos Agent Constitutional Framework taxonomy (2026). Architecture is synthesized from these sources.

## See also

- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — enforcement degradation when guardrails live in the prompt
- [S-349 · Constitutional Guardrails](s349-agentic-guardrails-four-layer-enforcement-plane.md) — four-layer enforcement plane; S-1116 adds the normative/values layer this entry's prompt-mediated layer lacks
- [S-238 · Deterministic Guardrails](s238-deterministic-guardrails-outside-the-llm-loop.md) — LLM-as-judge is too slow; S-1116's constitutional engine is fully deterministic
- [S-866 · Intent Capsule](s866-the-intent-capsule-stack-when-your-agent-started-to-do-something-else.md) — deterministic constraint engine; S-1116 adds the governance structure and amendment process
- [S-1095 · Verification Grounding](s1095-the-verification-grounding-stack-when-your-agent-checks-its-own-work-and-makes-it-worse.md) — Zylos taxonomy of runtime verification patterns including constitutional AI/RLAIF
