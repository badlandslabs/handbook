# S-2697 · The Library Drift Stack — When Your Self-Evolving Agent Gets Dumber as Its Skill Library Grows

Self-evolving skill libraries (Voyager et al.) let frozen LLM agents accumulate reusable procedural knowledge without weight updates. The promise is compounding: each solved task deposits a skill that accelerates future tasks. After 100 tasks your agent should be dramatically faster and more capable. After 100 tasks your agent's held-out pass@1 has plateaued at +0.0pp over no-skill. Meanwhile the library has 847 skills, the retrieval step takes 3 seconds, and nobody noticed because nothing failed — nothing succeeded either.

## Forces

- **Skills self-accumulate with no retirement.** Voyager-style systems author and inject new skills after each solved task. Nobody removes them. The library grows unboundedly: 50 tasks → 50 skills, 100 tasks → 100 skills, 847 tasks → 847 skills.
- **LLM-authored skills look reasonable in isolation but degrade the aggregate.** SkillsBench (Li et al. 2026) found LLM-authored skills deliver +0.0pp over no-skill baselines; human-curated ones deliver +16.2pp. The gap isn't bad individual skills — it's the combinatorial effect of retrieval degradation, false-positive injections, and performance stagnation from the aggregate.
- **Library drift is invisible until it's catastrophic.** Individual skills pass acceptance tests. Task success rate on the training distribution looks fine. You only detect drift with a held-out evaluation suite (SkillsBench) run at regular intervals. Without it, you ship a growing library that silently stalls your agent's capability ceiling.
- **Lifecycle management is the missing layer.** A survey of 20+ self-evolving systems found that versioning, conflict detection, and deprecation are "largely neglected." Most teams build the skill author → injection loop and never build the retirement loop.

## The move

**Track outcome-driven lifecycle metadata and enforce skill retirement.** Three mechanisms: outcome tracking, retirement policy, and governance audits.

### Outcome Tracker

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SkillRecord:
    skill_id: str
    description: str
    outcome_history: list[float] = field(default_factory=list)
    status: str = "active"
    retire_after_rounds: int = 5
    efficacy_threshold: float = 0.05  # minimum +pp gain to stay active
    added_at: datetime = field(default_factory=datetime.now)

    @property
    def rolling_gain(self) -> float:
        """Change in held-out pass@1 attributable to this skill."""
        if len(self.outcome_history) < 2:
            return 0.0
        return self.outcome_history[-1] - self.outcome_history[0]

    def should_retire(self) -> bool:
        return (
            len(self.outcome_history) >= self.retire_after_rounds
            and self.rolling_gain < self.efficacy_threshold
        )


class SkillLibrary:
    def __init__(self):
        self.skills: dict[str, SkillRecord] = {}
        self.removed: dict[str, SkillRecord] = {}  # graveyard for audit

    def add(self, skill_id: str, description: str) -> None:
        self.skills[skill_id] = SkillRecord(skill_id=skill_id, description=description)
        print(f"[+skill] {skill_id} added (total active: {len(self.skills)})")

    def log_outcome(self, skill_id: str, held_out_pass_at_k: float) -> None:
        if skill_id not in self.skills:
            return
        s = self.skills[skill_id]
        s.outcome_history.append(held_out_pass_at_k)
        if s.should_retire():
            self._retire(skill_id)

    def _retire(self, skill_id: str) -> None:
        s = self.skills.pop(skill_id)
        s.status = "retired"
        self.removed[skill_id] = s
        print(f"[-skill] {skill_id} retired — rolling_gain={s.rolling_gain:.3f} "
              f"(threshold={s.efficacy_threshold})")

    def governance_audit(self) -> dict:
        """Run periodic health check on the entire library."""
        retiring = [sid for sid, s in self.skills.items() if s.should_retire()]
        total_gain = sum(s.rolling_gain for s in self.skills.values())
        return {
            "total_active": len(self.skills),
            "total_retired": len(self.removed),
            "library_health": "degraded" if len(retiring) > len(self.skills) * 0.2 else "healthy",
            "flagged_for_retirement": retiring,
            "aggregate_rolling_gain": total_gain,
        }

    def get_active(self) -> list[str]:
        return [sid for sid, s in self.skills.items() if s.status == "active"]
```

### Usage

```python
library = SkillLibrary()

# Simulate a skill that provides real value
library.add("skill_fetch_auth_token", "Extract and reuse auth tokens across sessions")
for pass_at_k in [0.258, 0.291, 0.334, 0.412, 0.486, 0.531]:
    library.log_outcome("skill_fetch_auth_token", pass_at_k)
# rolling_gain = 0.531 - 0.258 = +0.273 → stays active ✓

# Simulate a skill that looks plausible but doesn't help
library.add("skill_parse_yaml_comments", "Extract comments from YAML as hints")
for pass_at_k in [0.258, 0.261, 0.259, 0.262, 0.258, 0.260]:
    library.log_outcome("skill_parse_yaml_comments", pass_at_k)
# rolling_gain = +0.002 → below threshold → retired ✓

audit = library.governance_audit()
print(f"Active skills: {library.get_active()}")
print(f"Library health: {audit['library_health']}")
```

### Governance Loop

Run `governance_audit()` on a schedule (daily or per N tasks):

| Signal | Action |
|--------|--------|
| Skill rolling_gain < 0.05pp over N rounds | Flag → retirement queue |
| Library health = degraded (>20% flagged) | Full audit + trigger held-out re-evaluation |
| Aggregate gain declining | Freeze new skill injection until root cause found |
| Skill conflict detected (overlapping triggers) | Deprecate older, keep newer |

## Receipt

> Verified 2026-08-15 — Concept from arXiv:2605.19576 (AWS GenAI Innovation Center + HSBC, 2026). Code is minimal but structurally faithful: outcome tracking, rolling gain, retirement policy, and audit. The paper's eight-ablation decomposition of governance mechanisms confirms that disabling injection creates a flat floor (+0.002pp) and premature retirement creates a ceiling — the right policy sits between the two.

## See also

- [S-2479 · The Cascade Radius Stack](s2479-the-cascade-radius-stack-when-your-multi-agent-system-succeeds-but-one-hop-away-it-breaks.md) — reliability compounding across hops
- [S-2531 · The Mis-Specified Verifier Stack](s2531-the-mis-specified-verifier-stack-when-your-rlvr-training-silently-teaches-the-wrong-thing.md) — verification failures that look correct
- [S-1029 · The Evaluator Stack](s1029-the-evaluator-stack-when-your-agent-quality-measurement-is-the-real-failure-mode.md) — why your measurement is your real bottleneck
