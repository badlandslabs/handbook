# S-1308 · The Trace-to-Skill Stack — When Your Agent Learns From Production But Cannot Tell You What It Learned

Your agent runs 500 times a day in production. It gets things right more often now than it did three months ago. Nobody changed the prompt. Nobody fine-tuned the model. The model vendor shipped three updates in that time. So what changed? The answer is buried in your trace storage: the agent discovered behavioral patterns from repeated execution and implicit feedback, but that knowledge evaporates at every model upgrade. The trace exists. The learning doesn't survive. The Trace-to-Skill stack converts that buried learning into structured, reusable in-context skills that load at runtime — model weights stay frozen, but behavioral knowledge compounds across runs.

## Forces

- **Foundation models ship monthly. Fine-tuning takes weeks.** The standard "traces as training data" workflow ends with a fine-tune, which means your improvement cycle is perpetually outpaced by the model's own evolution. Every fine-tune locks you into the model version it was built for. When the model upgrades, you re-fine-tune. The migration treadmill consumes the gains.

- **Behavioral patterns in traces are real but latent.** Successful production traces encode implicit problem-solving strategies — which tool sequence worked, which error was recoverable versus fatal, when to escalate versus retry. These patterns are real improvements in task completion rate, but they exist only in the trace store, invisible to future runs on the same model or any other model.

- **In-context skills survive model upgrades. Fine-tuned weights don't.** The key insight: extract the *behavior* (the skill), not the *weight adjustment* (the fine-tune). Skills load into context at inference time. They work on Claude 4, Claude 5, and the model you haven't chosen yet. Pattern density — the concentration of reusable behaviors per trace — is the unit of improvement.

- **Not all traces teach.** Random successful traces are noise. The signal is in the *structurally surprising* success: the task that should have failed, the edge case that required a non-obvious tool sequence, the recovery from a near-miss. Distinguishing signal from noise requires outcome metadata — what happened, not just what was logged.

## The move

**1. Instrument outcome metadata into trace capture.** Every trace needs more than tool calls and responses. Tag each with: task outcome (success / partial / failure), error category if applicable, task type, and whether the trace required an unusual strategy. Without outcome tags, clustering produces noise clusters. The metadata is the training signal.

**2. Cluster traces by behavioral pattern, not by task type.** Task type clustering groups by what was done. Behavioral clustering groups by how it was done. A "file processing" task that uses a fallback-and-retry strategy belongs with a "data extraction" task that uses the same strategy, not with other "file processing" tasks. Use tool-call sequence signatures as the clustering dimension — two traces with the same tool-call signature are behaviorally equivalent even if the domain differs.

**3. Extract the skill as a structured artifact.** A skill is: a trigger condition (what situations activate this), a behavioral sequence (the tool-call pattern), a success criterion (what a good outcome looks like), and an anti-pattern (what to avoid). The skill is a text artifact that loads into the system prompt at session start. It does not modify model weights.

**4. Validate skills against held-out traces before deploying.** Run each candidate skill against a test set of traces it wasn't extracted from. A skill that improves 3+ held-out traces with p < 0.05 is production-ready. A skill that only works on its extraction set is an overfit pattern — discard it.

**5. Version and age skills.** Skills extracted from June 2026 traces may encode a tool API that changed in August. Skills have a TTL: if the underlying tool schema or environment changes, the skill expires. Track which tool versions each skill was validated against.

```python
import json
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class Trace:
    trace_id: str
    tool_sequence: list[str]  # e.g. ["search", "fetch", "parse", "write"]
    outcome: str  # "success" | "partial" | "failure"
    error_category: str | None = None
    task_type: str = ""

@dataclass
class Skill:
    skill_id: str
    trigger_condition: str
    tool_sequence: list[str]
    success_criterion: str
    anti_pattern: str
    extraction_timestamp: str
    validated_tool_versions: list[str] = field(default_factory=list)
    hit_count: int = 0
    improvement_rate: float = 0.0  # delta in success rate on held-out traces


def extract_skills(traces: list[Trace], min_hits: int = 3) -> list[Skill]:
    """
    Cluster traces by tool-call sequence signature.
    Only successful traces with unexpected strategies become skills.
    """
    # Group by tool sequence
    by_signature = defaultdict(list)
    for t in traces:
        key = tuple(t.tool_sequence)
        by_signature[key].append(t)

    skills = []
    for sig, group in by_signature.items():
        successes = [t for t in group if t.outcome == "success"]
        if len(successes) < min_hits:
            continue

        # Compute how "surprising" this strategy is
        # vs the most common strategy for this task type
        task_type = successes[0].task_type
        total_for_task = [t for t in traces if t.task_type == task_type]
        common_strategies = defaultdict(int)
        for t in total_for_task:
            common_strategies[tuple(t.tool_sequence)] += 1
        most_common = max(common_strategies.values())
        surprisingness = len(successes) / max(most_common, 1)

        # Only extract if the strategy is non-obvious (surprising successes)
        if surprisingness < 1.5:
            continue  # too common, not a skill-worthy pattern

        skill = Skill(
            skill_id=f"skill_{'_'.join(sig)}_{len(skills)+1}",
            trigger_condition=f"Task type: {task_type}",
            tool_sequence=list(sig),
            success_criterion=f"Succeeded in {len(successes)}/{len(group)} runs",
            anti_pattern="Falls back to generic loop on common strategies",
            extraction_timestamp=successes[0].trace_id[:10],  # YYYY-MM-DD from trace
            validated_tool_versions=["current"],
        )
        skills.append(skill)

    return skills


def validate_skill(
    skill: Skill,
    test_traces: list[Trace],
    baseline_success_rate: float,
) -> float:
    """
    Run a candidate skill against held-out traces.
    Returns delta in success rate vs baseline.
    """
    matching = [
        t for t in test_traces
        if t.task_type in skill.trigger_condition
        and tuple(t.tool_sequence) == tuple(skill.tool_sequence)
    ]
    if not matching:
        return 0.0
    skill_rate = sum(1 for t in matching if t.outcome == "success") / len(matching)
    return skill_rate - baseline_success_rate


# Example: extract 12 skills from 1,000 production traces
skills = extract_skills(production_traces)
validated = [s for s in skills if validate_skill(s, test_set, baseline=0.72) > 0.05]
print(f"Extracted {len(skills)} candidate skills, {len(validated)} passed validation")
# → Extracted 12 candidate skills, 7 passed validation
```

## Receipt

> Receipt pending — 2026-07-18. Run against: 1,000 traces from a production code-review agent (3-week window), k=3 clustering threshold, 20% held-out validation set. Measure: delta in success rate for validated skills. Expected outcome: 5–10% absolute improvement in task completion rate. Trace overhead: ~2% additional tokens per session for skills loaded into system prompt.

## See also

- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — behavioral specialization across agents; this entry covers behavioral extraction within a single agent's traces
- [S-1073 · The Agent Distillation Stack](s1073-the-agent-distillation-stack-when-your-frontier-agent-becomes-your-production-cost.md) — model-level distillation (weights); this entry covers behavior-level distillation (context)
- [S-1102 · The Causal-Temporal Event Graph Stack](s1102-the-causal-temporal-event-graph-stack-when-your-multi-agent-trace-is-a-pile-of-fragments.md) — trace structure; this entry covers what to extract from traces after they're structured
- [S-1043 · The Dreaming Pattern](s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — memory consolidation between sessions; this entry covers behavioral learning without explicit memory writes
