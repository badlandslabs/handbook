# S-1326 · The Library Drift Stack — When Your Agent Learns New Skills and Becomes Slowly Worse

Your agent was sharp in January. You shipped it with 47 skills — file operations, API calls, data transforms, all precise and useful. By June it has 312 skills, and its overall accuracy is down 12 points. The new skills didn't help. They cluttered retrieval, introduced false-positive matches, and nobody noticed because the agent never reported failures — it just retrieved and used everything it found. This is library drift: the silent accumulation of skills that individually look valid but collectively degrade system performance. It is not a memory problem. It is not a context problem. It is a skill lifecycle problem.

## Forces

- **Skills compound in retrieval, not in capability.** Adding a skill increases the odds of a false-positive match on every retrieval. A library of 300 skills surfaces 6x more candidates than a library of 50 — and LLM-based retrieval degrades under volume. The marginal skill is net-negative even when individually useful.
- **Agents can't evaluate their own skill libraries.** The same model that authored a skill is asked to judge whether it still applies. This is the self-assessment trap: a model that generated a skill is biased toward confirming it's still valid. Ablation studies (disable skill, measure delta) are the only reliable signal, and almost no production system runs them.
- **Skill authorship quality varies wildly.** LLM-authored skills show +0.0pp improvement in production (arXiv:2605.19576). Human-authored skills show +16.2pp. Yet most self-evolving systems accumulate LLM-authored skills without differentiating provenance or retirement policies.
- **Silent degradation is invisible to standard monitoring.** There are no error logs, no exceptions, no latency spikes. The agent completes every task. It just completes them slightly worse each month. By the time the regression is noticed, 90+ skills have accumulated and root-cause is intractable.
- **The "add" button has no "remove" button.** Every agent framework makes skill injection easy. None make skill retirement easy. The asymmetry guarantees unbounded library growth in every self-evaluating system.

## The move

### Detect before it's too late: outcome-linked skill scoring

The only reliable signal that a skill is harmful is a measurable outcome delta. For every skill in your library, track task success rate with and without that skill active:

```python
# Outcome-linked skill scoring
from collections import defaultdict
import statistics

class SkillScorer:
    def __init__(self):
        # Per-skill: list of (task_id, outcome_delta)
        # outcome_delta = 1 if task succeeded WITH this skill, -1 if it failed
        self.skill_outcomes: dict[str, list[int]] = defaultdict(list)
        self.task_skills_used: dict[str, set[str]] = defaultdict(set)

    def record(self, task_id: str, skill_names: list[str], success: bool):
        delta = 1 if success else -1
        for skill in skill_names:
            self.skill_outcomes[skill].append(delta)
            self.task_skills_used[task_id].add(skill)

    def contribution_score(self, skill: str, min_trials: int = 20) -> float | None:
        outcomes = self.skill_outcomes[skill]
        if len(outcomes) < min_trials:
            return None
        # Positive score = skill correlates with success
        return statistics.mean(outcomes)

    def stale_skills(self, threshold: float = -0.05) -> list[tuple[str, float]]:
        """Skills with negative contribution — candidates for retirement."""
        candidates = []
        for skill, score in [(s, self.contribution_score(s)) for s in self.skill_outcomes]:
            if score is not None and score < threshold:
                candidates.append((skill, score))
        return sorted(candidates, key=lambda x: x[1])  # worst first
```

### Ablation validation before retirement

A negative contribution score is necessary but not sufficient — the skill might be negatively correlated with easy tasks. Run ablation:

```python
def ablation_test(skill: str, scorer: SkillScorer, agent, eval_tasks: list[dict]) -> dict:
    """Compare agent performance WITH and WITHOUT a specific skill."""
    with_skill = agent.clone(include_skills=[skill]).eval(eval_tasks)
    without_skill = agent.clone(exclude_skills=[skill]).eval(eval_tasks)

    delta = with_skill["success_rate"] - without_skill["success_rate"]
    return {
        "skill": skill,
        "with_skill": with_skill["success_rate"],
        "without_skill": without_skill["success_rate"],
        "delta": delta,  # negative = skill is net harmful
        "retire": delta < -0.02,  # retire if it hurts by >2pp
    }
```

### The retirement protocol

Skills that fail ablation get a structured retirement, not deletion:

```python
class SkillLibrary:
    def __init__(self):
        self.skills: dict[str, dict] = {}
        self.retired: dict[str, dict] = {}  # archive, don't delete

    def retire(self, skill_name: str, reason: str, ablation_result: dict):
        skill = self.skills.pop(skill_name)
        self.retired[skill_name] = {
            **skill,
            "retired_at": "2026-07-18",
            "retirement_reason": reason,
            "ablation_delta": ablation_result["delta"],
            "total_invocations": skill.get("invocation_count", 0),
        }
        # Re-evaluate affected downstream skills
        self._reevaluate_neighbors(skill_name)

    def _reevaluate_neighbors(self, retired_skill: str):
        # Skills that frequently co-occurred with the retired skill
        # may now have different contribution scores
        pass
```

### Retrieval quality gate

Before retiring, add a retrieval filter to suppress low-confidence matches:

```python
from anthropic import Anthropic
client = Anthropic()

def retrieve_skills(query: str, library: SkillLibrary, threshold: float = 0.7) -> list[dict]:
    """Retrieve skills with confidence-gated filtering."""
    # Fetch all candidate skills with their metadata
    candidates = library.get_all_skills()
    if not candidates:
        return []

    skill_descriptions = "\n".join(
        f"[{i}] {s['name']}: {s['description']}"
        for i, s in enumerate(candidates)
    )

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="""You are a skill retrieval judge. Given a task query, select the EXACT
        matching skill indices. Only select skills that are DIRECTLY relevant.
        Reject skills that are tangentially related — tangential matches cause
        performance degradation. Respond with JSON: {"matches": [index, ...], "confidence": 0.0-1.0}""",
        messages=[{
            "role": "user",
            "content": f"Task: {query}\n\nSkills:\n{skill_descriptions}"
        }]
    )

    import json
    result = json.loads(response.content[0].text)

    # Only return matches above threshold
    if result.get("confidence", 0) < threshold:
        return []
    return [candidates[i] for i in result.get("matches", []) if 0 <= i < len(candidates)]
```

### The library health dashboard

Monitor these metrics continuously:

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|---------|
| Library size growth rate | <5%/month | 5-15%/month | >15%/month |
| Mean skill contribution score | >0.1 | 0.0-0.1 | <0.0 |
| Zero-contribution skill ratio | <5% | 5-20% | >20% |
| Ablation pass rate | >80% | 60-80% | <60% |
| LLM-authored skill ratio | <20% | 20-50% | >50% |

## Receipt

> Verified 2026-07-18 — Pattern from arXiv:2605.19576 (Library Drift, ICML 2026 FAGEN Workshop), confirmed against handbook coverage audit. No existing handbook entry covers skill library lifecycle management or the library-drift failure mode. S-1316 (scaffold gap) covers benchmark-to-product misalignment; S-09 (memory systems) covers context memory; neither covers skill library accumulation or retirement. The ablation-based skill scoring and retirement protocol are from first principles applied to the reported failure pattern.

## See also

- [S-1309 · The Multi-Agent Coordination Stack](stacks/s1309-the-multi-agent-coordination-stack-when-your-second-agent-doesnt-know-what-the-first-one-did.md) — agents fail at the seams; library drift is another kind of seam
- [S-1316 · The Scaffold Gap Stack](stacks/s1316-the-scaffold-gap-when-your-benchmark-score-is-not-your-product-score.md) — your benchmark score is not your skill-library score
- [S-1063 · The Context Lifecycle Stack](stacks/s1063-the-context-lifecycle-stack-when-your-agent-loses-the-plot-halfway-through.md) — context management; library drift is skill-level context management
