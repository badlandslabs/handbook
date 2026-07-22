# S-1497 · The Lucky Recovery Stack — When Your Agent Gets Credit for a Wrong Path

Your agent's weekly quality dashboard shows 94% task completion. Your eval suite shows 89% pass rate. Both numbers are lies. The agent has been taking wrong tool-call paths, landing on accidentally-correct answers through a chain of errors that canceled out — and neither your dashboard nor your eval suite caught it. These are lucky recoveries: the most dangerous signal in agentic systems, and the highest-value seeds for your evaluation dataset.

## Forces

- **Healthy production hides the most valuable data.** When a run succeeds, you log it as a win and move on. But a success achieved through wrong reasoning is not a win — it's a masked failure. Every lucky recovery is a gap in your eval coverage that your users are absorbing without telling you.
- **Eval datasets decay faster than you build them.** Production traffic distribution shifts daily. The edge cases you wrote into your eval set three months ago are a biased sample of yesterday's traffic. You need a pipeline that converts today's production failures and near-misses into tomorrow's eval seeds — continuously.
- **Boundary conditions are the rarest and most valuable eval data.** The cases that stress-test your agent are exactly the cases that appear once in a thousand runs. Mining production for these requires more than a pass/fail filter — it requires trajectory analysis that flags structural anomalies, not just outcome errors.
- **Lucky recoveries are invisible to outcome-only monitoring.** If you only log "did the agent complete the task?", a lucky recovery looks identical to a clean run. You need to inspect the trajectory — the exact tool call sequence, the reasoning steps, the intermediate state — to detect that the path was wrong even though the destination was right.

## The move

**Mine production traces for masked failures, then convert those failures into eval seeds.** This is a three-stage pipeline:

### Stage 1 — Lucky Recovery Detector

Run a trajectory classifier over successful production traces. Flag traces where the tool call sequence deviated from the expected canonical path, even though the final outcome was correct.

```python
import json
from anthropic import Anthropic
from collections import Counter

client = Anthropic()

def detect_lucky_recovery(trace: dict, canonical_path: list[str]) -> dict:
    """
    Given a successful trace and the canonical tool path,
    returns a LuckyRecoveryReport if the trace took a wrong detour.
    """
    actual_path = [step["tool"] for step in trace["tool_calls"]]
    
    # A lucky recovery: same outcome via different path
    # "different path" = sequence differs, not just reordered
    if actual_path == canonical_path:
        return {"lucky": False, "reason": "canonical_path"}
    
    # Check if the deviation involved a detour
    detour_tools = set(actual_path) - set(canonical_path)
    skipped_tools = set(canonical_path) - set(actual_path)
    
    if detour_tools or skipped_tools:
        return {
            "lucky": True,
            "reason": "path_divergence",
            "detour_tools": list(detour_tools),
            "skipped_tools": list(skipped_tools),
            "original_path": canonical_path,
            "actual_path": actual_path,
            "trace_id": trace["trace_id"],
            "task_id": trace["task_id"],
            # The critical field: don't throw this away
            "eval_seed": True,
        }
    
    return {"lucky": False, "reason": "minor_variance"}


def batch_mine_lucky_recoveries(
    traces: list[dict],
    canonical_paths: dict[str, list[str]],
) -> list[dict]:
    """
    Scan a batch of production traces for lucky recoveries.
    These become your eval seeds — they represent edge cases
    your agent solved wrong but got credit for.
    """
    seeds = []
    for trace in traces:
        task_type = trace.get("task_type", "default")
        canonical = canonical_paths.get(task_type, [])
        
        report = detect_lucky_recovery(trace, canonical)
        if report.get("eval_seed"):
            seeds.append({
                "seed_type": "lucky_recovery",
                "trace_id": trace["trace_id"],
                "input": trace["input"],
                "output": trace["output"],
                "canonical_path": canonical,
                "actual_path": report["actual_path"],
                "deviation": {
                    "detour": report["detour_tools"],
                    "skipped": report["skipped_tools"],
                },
                "why_wrong": _classify_deviation_reason(trace),
            })
    return seeds


def _classify_deviation_reason(trace: dict) -> str:
    """
    Use a small model to classify WHY the deviation happened.
    This becomes the eval label — the failure mode category.
    """
    tool_sequence = " -> ".join(
        f"{s['tool']}({s.get('args', {}).keys()})" 
        for s in trace["tool_calls"]
    )
    prompt = f"""\
Classify the tool-call deviation in this trace:

Sequence: {tool_sequence}
Outcome: {trace['outcome']}

Deviation types:
- WRONG_TOOL: called a tool that should not have been used
- MISSING_TOOL: skipped a required tool in the sequence
- HALLUCINATED_ARG: called right tool with fabricated arguments
- LOOP_DETOUR: called extra tools before finding the right path
- SILENT_FAILURE: tool call failed but agent continued

Respond with only the deviation type."""
    
    response = client.messages.create(
        model="claude-haiku-4",
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
```

### Stage 2 — Failure Seed Expansion

A lucky recovery is one instance. A failure mode is a distribution. Use the seed to generate a family of similar edge cases — variations that stress-test the same failure pattern.

```python
def expand_failure_seeds(
    lucky_recovery: dict,
    num_variants: int = 20,
) -> list[dict]:
    """
    Given one lucky recovery seed, generate N variants
    that test the same failure mode in different contexts.
    """
    base_prompt = f"""\
Generate {num_variants} variations of this agent input that would
trigger the same tool-call deviation: {lucky_recovery['deviation']}.

Original input: {lucky_recovery['input']}

Each variation should:
- Change the surface details (entities, numbers, phrasing)
- Preserve the structural property that caused the detour
- Be realistic and plausible as a production input

Output a JSON array of {num_variants} input strings."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": base_prompt}],
    )
    
    variants = json.loads(response.content[0].text)
    return [
        {
            "input": v,
            "seed_source": lucky_recovery["trace_id"],
            "failure_mode": lucky_recovery["why_wrong"],
            "expected_path": lucky_recovery["canonical_path"],
            "expected_failure": lucky_recovery["deviation"],
        }
        for v in variants
    ]


def build_eval_dataset(seeds: list[dict]) -> list[dict]:
    """
    Convert lucky recovery seeds into labeled eval examples.
    Each entry: input + expected_correct_path + expected_failure.
    """
    dataset = []
    for seed in seeds:
        variants = expand_failure_seeds(seed)
        for variant in variants:
            dataset.append({
                "id": f"lr-{seed['trace_id']}-{len(dataset)}",
                "input": variant["input"],
                "expected_tool_path": variant["expected_path"],
                "failure_mode": variant["failure_mode"],
                "source": "lucky_recovery_mining",
                "labels": {
                    "correct_outcome": False,  # agent should NOT reach correct answer
                    "correct_path": False,     # agent should NOT take this path
                },
                "metadata": {
                    "source_trace": seed["trace_id"],
                    "actual_deviation": seed["deviation"],
                },
            })
    return dataset
```

### Stage 3 — Continuous Eval Pipeline

```yaml
# eval-pipeline.yaml — runs on every production trace batch
stages:
  - name: mine_lucky_recoveries
    input: production_traces/latest_1h/
    canonical_paths: canonical_paths.yaml
    output: seeds/lucky_recoveries/

  - name: expand_failure_seeds
    input: seeds/lucky_recoveries/
    variants_per_seed: 20
    output: seeds/expanded/

  - name: run_eval_on_seeds
    input: seeds/expanded/
    eval_suite: agent_eval_v2
    threshold:
      correct_path_rate: 0.95    # agent must take correct path
      correct_outcome_rate: 0.90  # agent should reach correct outcome

  - name: update_eval_dataset
    # Auto-inject new seeds into the pinned eval set
    # if they fail the threshold (proving they test a real gap)
    input: seeds/expanded/failures/
    output: datasets/agent_eval_v3.yaml
    trigger: pr_review_required  # human gates new eval entries
```

The key gate: a lucky recovery seed only enters the pinned eval set if the expanded variants fail against the current agent — proving the seed tests a genuine gap, not a noise case.

## Receipt

> Verified 2026-07-22 — Pattern confirmed via tianpan.co (AgentReplay, April 2026), Zylos Research (Longitudinal Evaluation, April 2026), and jobsbyculture.com (AI Agent Debugging Playbook, June 2026). All three sources independently identify lucky recovery detection as a critical but underserved signal: tianpan.co flags "wrong tool, correct answer" traces as high-value replay targets; Zylos identifies masked failures as the primary source of eval dataset staleness; the jobsbyculture playbook explicitly names trajectory-level inspection as the only way to surface wrong-path successes. Code above is an illustrative pipeline design based on patterns described in these sources. Not run against live production traces in this entry.

## See also

- [S-1013 · The Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — when to replay a captured production trace
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — eval layers, trajectory scoring, cost axes
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — why production quality degrades without changes
