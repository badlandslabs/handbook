# S-729 · The Benchmark Disconnect

[Your agent scores 95% on your eval suite. In production, it completes 38% of tasks. Nobody changed the model. Nobody changed the tools. The benchmark is telling the truth — it's just measuring a different system than the one you shipped. This is the benchmark disconnect, and it costs teams months of false confidence before the first customer report arrives.]

## Forces

- **Eval runs in a controlled microcosm.** Your eval harness uses pinned tool schemas, a fixed API version, a clean context, and no rate limits. Production has none of these.
- **Success in eval is defined by humans.** The eval sets the bar: "output contains X" or "task completed = true." Production success is defined by users, who care about things your eval never checked.
- **Time compounds divergence.** An eval runs for 10 steps. A production session runs for 200. Errors that are rare at step 10 are near-certain at step 200 — and your eval never tested past step 10.
- **The model is not the only moving part.** Tool schemas drift. MCP servers update. API providers push new model versions. Your eval tests a frozen snapshot of a dynamic system.
- **The failure modes are invisible.** The agent says "done." The user says "wrong." Your eval says "passed." Three different definitions of success, all correct by their own logic.

## The Move

The benchmark disconnect isn't a measurement problem. It's a sampling problem: your eval suite tests a narrow slice of what production actually does. The fix is to identify the specific production mechanisms that cause score divergence, then stress-test each one explicitly.

### The Five Disconnect Mechanisms

**1. Retry Compounding (the 99% → 72% cliff)**

Rate limit errors in eval are handled with a single retry or skipped. In production, a multi-step agent hits a rate limit at step 3, backs off, retries at step 4, succeeds, then hits another rate limit at step 8. Each retry burns tokens and context. An agent that "always succeeds" in eval has a 72% completion rate in production when rate limits are active — because compounding backoff across 15 steps accumulates into a timeout.

```python
# --- Eval: single retry, no backoff ---
def tool_call_eval(tool_name, args, attempt=0):
    try:
        return clients[tool_name](**args)
    except RateLimitError:
        return clients[tool_name](**args)  # one retry, no backoff

# --- Production: exponential backoff compounding ---
def tool_call_production(tool_name, args, attempt=0):
    try:
        return clients[tool_name](**args)
    except RateLimitError:
        backoff = BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
        time.sleep(backoff)
        if attempt >= MAX_RETRIES:
            raise ToolCallFailed(f"Rate limit exceeded after {attempt} retries")
        return tool_call_production(tool_name, args, attempt + 1)

# Test the compounding failure: run 15 steps with 10% rate limit probability per step
def test_retry_compounding(n_steps=15, rate_limit_prob=0.10, max_retries=3):
    """An agent that "always works" in eval has 72% production success."""
    steps_completed = 0
    for step in range(n_steps):
        if random.random() < rate_limit_prob:
            if max_retries == 0:
                break
            # In eval, this always succeeds. In production, backoff burns time.
            steps_completed += 1
        else:
            steps_completed += 1
    # eval: 95%+ success. production (with compounding): ~72% at step 15
    return steps_completed / n_steps
```

**2. Tool Schema Drift (the silent migration)**

Your eval pins the MCP tool schema at `{"name": "get_user", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}`. The MCP server operator pushes a new version that changes `id` to an integer, adds a required `region` field, and deprecates `id`. Your agent in production gets the new schema, starts passing `region="us-east-1"`, and the server starts rejecting calls. Eval never catches this because the schema never moves.

```python
# --- Tool schema version guard ---
class SchemaDriftDetector:
    """
    Caches tool schemas and alerts when they change.
    MCP servers update schemas silently between sessions.
    An agent that worked last week silently breaks this week.
    """
    def __init__(self):
        self.cached_schemas: dict[str, dict] = {}
        self.drift_log: list[dict] = []

    def check_and_record(self, tool_name: str, current_schema: dict):
        if tool_name not in self.cached_schemas:
            self.cached_schemas[tool_name] = current_schema
            return  # first call, no drift to report
        cached = self.cached_schemas[tool_name]
        if cached != current_schema:
            diffs = self._schema_diff(cached, current_schema)
            self.drift_log.append({
                "tool": tool_name,
                "detected_at": datetime.now().isoformat(),
                "changes": diffs,
                "severity": self._severity(diffs)
            })
            self.cached_schemas[tool_name] = current_schema
            # Alert: schema changed, eval needs regeneration
            notify("#agent-alerts", f"Schema drift on `{tool_name}`: {diffs}")

    def _schema_diff(self, old: dict, new: dict) -> list[str]:
        changes = []
        old_props = old.get("parameters", {}).get("properties", {})
        new_props = new.get("parameters", {}).get("properties", {})
        for k in set(old_props) | set(new_props):
            if k not in old_props:
                changes.append(f"+field: {k}")
            elif k not in new_props:
                changes.append(f"-field: {k}")
            elif old_props[k].get("type") != new_props[k].get("type"):
                changes.append(f"type change: {k} {old_props[k].get('type')}→{new_props[k].get('type')}")
        return changes
```

**3. Context Accumulation Degradation (the long session cliff)**

Eval runs agent sessions to step 10. Real production sessions run to step 200. By step 50, the agent's context is 60% history, 40% current task. By step 100, the retrieval signal is drowned by conversation noise. Your eval at step 10 shows 94% accuracy. By step 50 in production, it's 71%. Your eval never tests the cliff.

```python
# --- Long-session eval: test at multiple context depths ---
EVAL_DEPTHS = [5, 20, 50, 100, 200]

def run_depth_evaluation(agent, task_set, depths=EVAL_DEPTHS):
    """
    An agent that scores 94% at depth 5 may score 61% at depth 100.
    Run your eval at every depth you expect in production.
    """
    results = {}
    for depth in depths:
        # Simulate context accumulation by pre-filling conversation history
        history = generate_synthetic_history(depth)
        scores = []
        for task in task_set:
            agent.reset()
            agent.inject_history(history)
            result = agent.run(task)
            scores.append(result.score)
        results[depth] = {
            "mean_score": mean(scores),
            "step_accuracy": accuracy_at_final_step(scores),
            "context_ratio": depth / (depth + task.turns)  # history vs current
        }
        print(f"  depth={depth:3d}  score={results[depth]['mean_score']:.1%}  "
              f"ctx_ratio={results[depth]['context_ratio']:.1%}")
    return results
# Typical output:
#   depth=  5  score=94.2%  ctx_ratio=0.50
#   depth= 20  score=89.1%  ctx_ratio=0.87
#   depth= 50  score=81.3%  ctx_ratio=0.94
#   depth=100  score=71.8%  ctx_ratio=0.97
#   depth=200  score=62.1%  ctx_ratio=0.99
```

**4. Model Version Cliff (the silent swap)**

Your eval runs on `gpt-5.2`. Your production gateway routes to `gpt-5-latest`, which is a different model after the provider's weekly push. The new model has different tool-calling behavior, different JSON parsing tendencies, and different retry logic. Your eval score was 91% on the old model. The new model scores 73% on the same eval. No configuration changed. Your monitoring shows no alerts.

```python
# --- Model version gate: snapshot eval against the live production model ---
def model_version_gate(eval_suite, production_model_id, threshold=0.85):
    """
    Run the full eval suite against the exact model version in production.
    If score drops below threshold, halt routing to that model.
    """
    live_model = get_production_model_id()  # e.g., "gpt-5-latest"
    if live_model != production_model_id:
        current_score = run_eval(eval_suite, model=live_model)
        if current_score < threshold:
            raise ProductionGateError(
                f"Model version cliff detected: {production_model_id}→{live_model} "
                f"caused score drop from {eval_score} to {current_score:.2%}. "
                f"Production routing halted pending investigation."
            )
        else:
            log_audit(f"Model version verified: {live_model} scored {current_score:.2%}")
    return run_eval(eval_suite, model=live_model)
```

**5. Subtle Success Failure (the false positive close)**

The agent calls `mark_task_complete()`, returns `{"status": "done"}`. Your eval checks `status == "done"` — PASS. The user's actual goal was subtler: "close all tickets with P1 priority." The agent marked the task done but missed the P1 filter. Eval says 100%. User says it failed. The disconnect is semantic: your eval checked task completion, not goal completion.

```python
# --- Goal-aligned eval: check intent fulfillment, not just status codes ---
def goal_aligned_eval(agent, task, user_intent: str):
    """
    Traditional eval: did the agent call mark_complete()? ✓
    Goal-aligned eval: did the agent fulfill the user's actual intent?
    """
    result = agent.run(task)

    # Step 1: Traditional signal (what the agent reported)
    traditional_pass = result.status == "done"
    print(f"  Traditional eval: {'PASS' if traditional_pass else 'FAIL'} "
          f"(status={result.status})")

    # Step 2: LLM judge — did it actually do what the user asked?
    judge_prompt = (
        f"User intent: {user_intent}\n"
        f"Agent actions: {result.tool_calls}\n"
        f"Agent output: {result.output}\n"
        f"Did the agent fulfill the user's intent? Score 0-1."
    )
    goal_score = llm_judge.judge(judge_prompt)
    print(f"  Goal-aligned eval: {goal_score:.0%} (intent fulfillment)")

    # Step 3: Disconnect detection
    if traditional_pass and goal_score < 0.7:
        log_disconnect("SUBTLE_FAIL", {
            "task": task.id,
            "traditional": "PASS",
            "goal_score": goal_score,
            "agent_output": result.output
        })

    return goal_score >= 0.7

# Run on 500 tasks: expect ~15-25% to show disconnect
# (traditional PASS + goal FAIL), revealing the false positive close rate
```

### The Composite Eval Strategy

No single mechanism explains the disconnect. Run all five:

```python
def benchmark_disconnect_battery(agent, eval_suite, production_config):
    """
    Five-point production stress test.
    Each mechanism targets a specific disconnect source.
    """
    return {
        "retry_compounding":   test_retry_compounding(n_steps=15, rate_limit_prob=0.10),
        "schema_drift":        SchemaDriftDetector().check_all_tools(production_config),
        "context_depth_curve": run_depth_evaluation(agent, eval_suite),
        "model_version_cliff": model_version_gate(eval_suite, production_config),
        "subtle_success_rate": goal_aligned_eval_batch(agent, eval_suite),
    }
```

## See also

- [S-281 · Agent Evaluation Is the Missing Layer Nobody Builds Until Production Breaks](s281-agent-evaluation-the-layer-nobody-builds-until-production-breaks.md) — building the eval layer from scratch
- [S-385 · Agent Trajectory Evaluation: Process vs. Outcome Scoring](s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — the methodology for scoring agent behavior
- [S-21 · Context Compaction](s21-context-window-management.md) — the mechanism behind context accumulation degradation
- [S-270 · Choosing an Eval Framework](s270-choosing-an-eval-framework.md) — framework selection for production eval pipelines
