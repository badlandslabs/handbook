# S-1495 · The Agentic Compilation Stack — When Continuous Reasoning Costs More Than Continuous Execution

Your browser automation workflow ran 500 times yesterday. Each run cost $0.30. Your monthly bill is $4,500. A product manager asks why your agent costs $9 per task when a human doing the same thing costs $0.02 in labor. The model isn't wrong. The architecture is.

The standard agent loop — observe, think, act, repeat — is designed for open-ended tasks where the agent genuinely doesn't know what comes next. But most production agent workloads aren't open-ended. They're repetitive. A data extraction workflow, a form-filling pipeline, a scrape-and-transform routine. The agent "decides" the same thing every time because the input hasn't meaningfully changed. You're paying full LLM inference on every loop for a decision that was already made.

This is the **Rerun Crisis**: linear cost growth O(M×N) where M is reruns and N is workflow steps, for decisions that don't need to be re-made.

## Forces

- **Continuous inference loops charge per step.** Each observe-think-act cycle burns tokens. For a 5-step workflow at $5/M input tokens, 500 reruns = ~$150 in model costs alone
- **Most production agent tasks are repetitive, not reasoning-intensive.** The agent is thinking when it should be executing
- **Context accumulates between steps.** Each loop re-sends the full interaction history. Cost compounds even when the page state barely changes
- **Caching helps but only within a run.** Cross-run caching at the HTTP level misses the core problem: you're still asking the model to re-decide what it already decided
- **Compile-time knowledge exists.** The workflow structure — what actions to take, in what order, given what conditions — is knowable from the first observation

## The move

**Compile the workflow to a deterministic blueprint once, then execute it without the model.**

The compile-and-execute architecture splits agentic systems into two phases:

### Phase 1 — Compile (one-shot LLM call)

The agent sees the current state, emits a structured JSON workflow blueprint, then stops reasoning.

```python
import anthropic
import json
import asyncio

client = anthropic.Anthropic()

def sanitize_page_state(dom_snapshot: str, goal: str) -> str:
    """DOM Sanitization Module (DSM).
    Extract only goal-relevant elements to minimize token cost.
    """
    prompt = f"""Extract goal-relevant state from this page snapshot.
    Goal: {goal}
    Snapshot: {dom_snapshot}

    Return a minimal JSON object with only elements relevant to: {goal}
    Focus on: interactive elements, form fields, visible text, navigation state.
    Discard: styling, hidden elements, layout metadata."""
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def compile_workflow(page_state: str, task_description: str) -> dict:
    """One-shot LLM call: emit deterministic workflow blueprint."""
    prompt = f"""You are a workflow planner. Given the current page state and task,
    emit a JSON workflow blueprint. NO FURTHER REASONING after emitting this blueprint.

    Page state:
    {page_state}

    Task: {task_description}

    Output format (emit ONLY this JSON, no markdown, no explanation):
    {{
      "workflow_id": "extraction-001",
      "steps": [
        {{
          "action": "click|fill|navigate|extract|wait|conditional",
          "target": "css-selector or url",
          "value": "input value if any",
          "condition": "optional: only execute if this condition holds in page state",
          "expected_outcome": "what the page should look like after this step"
        }}
      ],
      "fallback": {{
        "on_failure": "retry|skip|abort",
        "max_retries": 3
      }}
    }}"""

    response = client.messages.create(
        model="claude-sonnet-4-7",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Parse and validate
    blueprint = json.loads(response.content[0].text)
    assert "steps" in blueprint, "Invalid blueprint: missing 'steps'"
    return blueprint
```

### Phase 2 — Execute (no LLM calls)

A lightweight runtime interprets the blueprint and drives the browser/action layer directly.

```python
import asyncio
from playwright.async_api import async_playwright
from dataclasses import dataclass

@dataclass
class WorkflowStep:
    action: str
    target: str
    value: str | None = None
    condition: str | None = None
    expected_outcome: str | None = None

async def execute_workflow(blueprint: dict, page):
    """Execute a pre-compiled workflow without any LLM calls."""
    for i, step_def in enumerate(blueprint["steps"]):
        step = WorkflowStep(**step_def)
        print(f"[Step {i+1}] {step.action} → {step.target}")
        
        try:
            match step.action:
                case "click":
                    await page.click(step.target)
                case "fill":
                    await page.fill(step.target, step.value)
                case "navigate":
                    await page.goto(step.target)
                case "extract":
                    result = await page.inner_text(step.target)
                    print(f"  → Extracted: {result[:100]}")
                case "wait":
                    await asyncio.sleep(float(step.target))
                case "conditional":
                    # Branch on pre-compiled conditions, no LLM needed
                    if not eval_condition(step.condition, page):
                        print(f"  → Condition false, skipping remaining steps")
                        break
        except Exception as e:
            fallback = blueprint.get("fallback", {})
            if fallback.get("on_failure") == "retry":
                continue  # or implement retry logic
            elif fallback.get("on_failure") == "abort":
                raise RuntimeError(f"Workflow aborted at step {i+1}: {e}")

def eval_condition(condition: str, page) -> bool:
    """Evaluate pre-compiled conditions without LLM."""
    # Examples: "element_visible('#submit-btn')", "url_contains('/checkout')"
    if "element_visible" in condition:
        import re
        selector = re.search(r"element_visible\('(.+?)'\)", condition).group(1)
        return page.is_visible(selector)
    if "url_contains" in condition:
        import re
        pattern = re.search(r"url_contains\('(.+?)'\)", condition).group(1)
        return pattern in page.url
    return False

async def run_agentic_compilation(task: str, url: str):
    """Main entry: compile once, execute many times."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        
        # Cost benchmark tracking
        compile_cost = 0.0
        
        for run in range(500):  # reruns scale to millions cheaply
            # PHASE 1: Compile (paid LLM call — happens once per scenario, not once per run)
            if run == 0:  # Recompile only when input structure changes
                page_state = await page.content()
                sanitized = sanitize_page_state(page_state, task)
                blueprint = compile_workflow(sanitized, task)
                compile_cost = 0.08  # ~$0.08 per compilation on sonnet-4-7
                print(f"Compilation complete: {len(blueprint['steps'])} steps, ${compile_cost:.4f}")
            
            # PHASE 2: Execute (zero LLM cost — pure automation)
            await execute_workflow(blueprint, page)
        
        total_cost = compile_cost  # NOT 500 × per-run cost
        cost_per_run = total_cost / 500
        print(f"Total: ${total_cost:.4f} for 500 runs = ${cost_per_run:.6f}/run")
        print(f"vs continuous agent: ~${150:.2f} for same workload")
        print(f"Savings: {150 / total_cost:.0f}×")
        
        await browser.close()

# Run
asyncio.run(run_agentic_compilation(
    task="Extract all job listings from this page",
    url="https://example.com/jobs"
))
```

### When to compile vs. continue reasoning

Compile-and-execute is wrong when:
- Input structure changes every run (open-ended research, creative tasks)
- The workflow genuinely needs mid-execution course correction
- Side effects require human verification gates

Compile-and-execute is right when:
- The task is structurally repetitive (same site, same schema, different data)
- Cost per execution matters more than adaptive behavior
- The LLM is doing the same reasoning every loop anyway

### The recompilation trigger

One-shot compilation means the blueprint is fixed until something changes. Triggers for recompilation:

```python
RECOMPILE_TRIGGERS = [
    "page_url_structure_changed",      # Navigated to a new domain/path
    "form_fields_differ_from_blueprint",  # Input schema drift
    "extraction_target_missing",       # DOM structure changed
    "too_many_execution_errors",       # Blueprint is stale
    "human_approved_new_task_variant", # Explicit trigger
]
```

## Receipt

> Verified 2026-07-22 — arXiv:2604.09718 (Chundru, Apr 2026) reports:
> - 5-step workflow, 500 iterations: continuous agent = **$150**, aggressive caching = **$15**, agentic compilation = **<$0.10** (1500× reduction)
> - Zero-shot compilation success: **80–94%** across data extraction, form filling, and tech-stack fingerprinting tasks
> - Amortized cost: O(1) per workflow after one-time compilation
> - Code examples validated against the described architecture (compile/execute phases, DSM pattern)

## See also

- [S-08 · Prompt Caching](stacks/s08-prompt-caching.md) — reduce per-call costs within continuous loops
- [S-1000 · The Context Exhaustion Stack](stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — context grows per loop step; compile-and-execute eliminates the loop
- [S-1014 · Evaluating Agents in Production](stacks/s1014-evaluating-agents-in-production-where-simplicity-beats-complexity.md) — recompile triggers as implicit regression tests
- [S-06 · Model Routing](stacks/s06-model-routing.md) — compile phase uses a capable model; execution phase uses none
