# S-2618 · The Provider Regression Detection Stack — When Your Agent Breaks Without a Commit

You shipped the agent on Tuesday. Your CI is green. Nothing changed in your code, your prompts, or your tool definitions. On Thursday, your error rate triples. Users are filing tickets. Your on-call engineer pulls up the dashboard and sees: no deploys, no config changes, no infrastructure incidents. The agent broke on its own.

It didn't. The model provider updated their weights on Wednesday night. The agent's behavior shifted — subtle enough that none of your metrics fired, but large enough that it started refusing tool calls it had handled reliably for 47 days. Your regression suite never fired because there was no commit. Your behavioral versioning stack (S-1033) captured nothing because the change was upstream, not in your stack. The agent broke without a diff.

This is the provider regression problem: AI agents depend on a black box that changes without notice, and your existing quality gates are designed for the wrong failure mode.

## Forces

- **Your regression suite is diff-triggered, but the most dangerous regressions don't come from diffs.** A provider-side model update — weight changes, system prompt modifications, fine-tune rollouts, or even hotfixes to the inference layer — arrives without a pull request. Your CI runs on commits. The provider's commit arrives as a production event.
- **Behavioral drift from upstream is invisible to traditional monitoring.** An error rate spike from a code bug is loud. A gradual shift in how the model interprets your tool descriptions is silent — it shows up as a slow degradation in task success rate, buried under natural variance. Most teams don't notice until customers complain.
- **The provider gives you no changelog.** OpenAI, Anthropic, and Google update models with minimal notice. The March 2023 vs June 2023 GPT-4 behavior shift (Stanford/Berkeley, Chen et al.) showed measurable degradation on identical tasks. This is not exceptional — it is the default state of production AI.
- **Canary deployments catch internal changes, not external ones.** Your traffic-split canary caught the prompt change you made last sprint. It will never catch the provider updating the model that serves both canary and baseline identically.

## The Move

The fix is a behavioral regression harness that runs continuously on production traffic — not on diffs, not on a schedule, but on every meaningful sample of live behavior. Three layers:

**Layer 1: Continuous Evaluation on Production Traffic**

Sample a percentage of production conversations (typically 1–5%) and route them through a golden dataset — a curated set of known-good inputs with verified expected outputs. An LLM judge grades each sample on the same rubric you'd use for an offline eval. Track the pass rate over time, not just per-run.

```python
import opentelemetry.trace as trace
import openai

def grade_conversation(conversation: list[dict], golden_entry: dict) -> float:
    """Grade a sampled production conversation against its golden reference."""
    rubric = golden_entry["rubric"]
    expected_behavior = golden_entry["expected_outcome"]
    
    grade_prompt = f"""Grade this agent conversation.
    
    RUBRIC: {rubric}
    EXPECTED: {expected_behavior}
    
    CONVERSATION:
    {format_conversation(conversation)}
    
    Score 0.0–1.0 with brief justification."""
    
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": grade_prompt}],
        temperature=0,
    )
    
    try:
        score = float(response.choices[0].message.content.split("\n")[0])
        return max(0.0, min(1.0, score))
    except (ValueError, IndexError):
        return 0.5  # Unknown — flag for human review

class RegressionHarness:
    def __init__(self, golden_dataset: list[dict], alert_threshold: float = 0.05):
        self.golden = {g["id"]: g for g in golden_dataset}
        self.alert_threshold = alert_threshold
        self.weekly_scores: dict[str, list[float]] = {}
    
    def sample_and_grade(self, conversation: list[dict], conversation_id: str) -> float:
        """Called per sampled production conversation."""
        # Find matching golden entry by task type, not by exact match
        task_type = classify_task(conversation)
        if task_type not in self.golden:
            return None  # No golden entry for this task type
        
        score = grade_conversation(conversation, self.golden[task_type])
        
        # Accumulate weekly scores per task type
        if task_type not in self.weekly_scores:
            self.weekly_scores[task_type] = []
        self.weekly_scores[task_type].append(score)
        
        return score
    
    def check_regression(self, task_type: str) -> bool:
        """Fire if this week's pass rate dropped significantly."""
        scores = self.weekly_scores.get(task_type, [])
        if len(scores) < 20:
            return False  # Not enough samples yet
        
        this_week_pass_rate = sum(1 for s in scores if s >= 0.8) / len(scores)
        baseline = self.baseline_pass_rate.get(task_type, this_week_pass_rate)
        
        # Alert if drop exceeds threshold
        if this_week_pass_rate < baseline - self.alert_threshold:
            return True
        return False
    
    def update_baseline(self, task_type: str):
        """Called weekly: recalibrate baseline from recent confirmed-good period."""
        scores = self.weekly_scores.get(task_type, [])
        self.baseline_pass_rate[task_type] = (
            sum(1 for s in scores if s >= 0.8) / len(scores)
        )
```

**Layer 2: Canary with Behavioral Assertions**

Unlike a traditional canary that watches error rates and latency, add behavioral assertions: define a set of probe conversations that must produce specific trajectories (tool call sequence, output schema, key phrases). Route 5–10% of traffic through the probe set on both baseline and candidate. Divergence in behavioral assertions fires before divergence in outcome metrics.

```python
def run_behavioral_canary(traffic_split: float = 0.05) -> bool:
    """
    Canary probe: identical inputs to baseline vs current model.
    Returns True if behavioral divergence detected (regression possible).
    """
    probes = load_probe_set("probes/behavioral_probes.json")
    
    regressions = []
    for probe in probes:
        baseline_output = probe["baseline_output"]  # captured at known-good state
        current_output = call_agent(probe["input"], model="current")
        
        divergence = semantic_similarity(baseline_output, current_output)
        if divergence < probe["similarity_threshold"]:
            regressions.append({
                "probe_id": probe["id"],
                "baseline": baseline_output[:200],
                "current": current_output[:200],
                "divergence_score": divergence,
            })
    
    if regressions:
        alert_on_call(f"Behavioral canary: {len(regressions)}/{len(probes)} probes regressed")
        return True
    return False
```

**Layer 3: Provider-Change Attribution Gate**

When a regression fires, attribute it. If no internal change correlates with the behavioral shift (no deploy in the window, no prompt edit, no tool change), treat the provider as the suspected cause. Route to a pinned model version for the affected task type while you investigate.

```python
def attribute_regression(regression_event: dict, deploy_log: list[dict]) -> str:
    """
    Returns: 'internal' | 'provider' | 'unknown'
    """
    regression_time = regression_event["detected_at"]
    window = timedelta(hours=48)
    
    # Check for internal changes in the window before regression
    for deploy in deploy_log:
        deploy_time = deploy["timestamp"]
        if abs(regression_time - deploy_time) < window:
            if deploy["changed_artifacts"] & {"prompt", "tool_def", "model", "code"}:
                return "internal"
    
    # No internal change found — likely provider
    return "provider"

def respond_to_provider_regression(regression: dict, attribution: str):
    if attribution == "provider":
        # Pin to stable model version for affected task
        pin_model_version(
            task_type=regression["task_type"],
            model=regression.get("stable_model_version"),
            reason="provider_regression_detected",
        )
        alert_channel(
            f"Provider regression suspected on {regression['task_type']}. "
            f"Pinned to stable version pending investigation. "
            f"Score dropped {regression['drop_pct']:.1f}% over {regression['window_hrs']}h."
        )
```

## When to Reach for This

- You run agents in production on a schedule that matters
- Your CI gates run on commits — and you've had an incident caused by a model update, not a code change
- You have no way to distinguish "the agent broke" from "the provider broke" when something goes wrong
- You need to qualify a model migration before rolling it out

## See also

- [S-1033 · The Behavioral Version Stack](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — The four independently-evolving layers that make AI versioning non-traditional
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — The broader SRE discipline for agentic systems, of which regression detection is a component
- [S-1010 · The Agent Eval Stack](s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — Building eval pipelines you can trust, including the golden dataset discipline
- [R-16 · Agent Harness Sensitivity](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — Why your benchmark score belongs to the scaffold, not just the model
