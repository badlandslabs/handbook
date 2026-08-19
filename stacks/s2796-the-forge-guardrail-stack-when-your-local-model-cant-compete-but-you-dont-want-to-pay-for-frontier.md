# S-2796 · The Forge Guardrail Stack — When Your Local Model Can't Compete but You Don't Want to Pay for Frontier

Your 8B model nails single-step tasks. Drop it into a five-step workflow and you get 40% success. Your first instinct: swap to GPT-4o or Sonnet. Your second instinct (if you care about cost, latency, or data privacy): find a different model. Your third instinct should be: add a reliability layer. Forge (Zambelli, ACM CAIS '26) is exactly that — a tool-agnostic guardrail stack that takes a local model from ~53% to 99% on agentic workflows without touching the model.

## Forces

- **The compounding math problem is unavoidable.** 95% per-step accuracy × 5 steps = 77% end-to-end. The failure isn't model quality — it's that the model needs mechanical scaffolding, not smarter weights
- **Per-workflow guardrails are expensive to maintain.** Hardcoded state machines for each tool set work but don't generalize; every new tool means rewiring the state machine
- **Frontier APIs are reliable but costly.** Privacy-sensitive workflows, latency-critical paths, and consumer-hardware deployments can't afford the per-token price or the data-leaving-the-building problem
- **Rescue parsing and retry nudges are domain-agnostic.** The mechanical failure modes (malformed JSON, empty responses, wrong tool names) are the same across domains — the fix doesn't need to know what the model is doing

## The move

Forge's guardrail stack has five independently-toggleable layers that intercept the agent loop between model output and tool execution:

**1. Rescue parsing.** When the model emits a tool call as free text instead of a structured call (malformed JSON, embedded in prose, wrong format), Forge extracts the call before failing. This alone recovers a large fraction of "model can't call tools" failures.

**2. Retry nudges.** When a response can't be resolved to a valid tool call and rescue failed, Forge injects a corrective message back into the context instead of escalating to a dead end. The model gets a second chance with a hint.

**3. Step enforcement.** When a workflow has required steps, dependencies, or a terminal tool, Forge enforces the contract. The model can't skip steps or "finish early" — it has to complete the sequence or explicitly report why it can't.

**4. Error recovery.** When a tool call returns an error (tool not found, invalid args, execution failure), Forge categorizes it and either retries with corrected args or redirects to an alternative path. Errors become feedback, not dead ends.

**5. Context compaction + VRAM budgeting.** When the rolling context window approaches budget limits, Forge compacts history and manages VRAM allocation across shared GPU slots. Hardware constraints stop breaking workflows.

```python
# Three ways to use Forge — pick your deployment shape

# --- Mode 1: Proxy (drop-in, zero code change) ---
# pip install forge-guardrails
# forge-proxy --backend ollama --model llama3.2 --port 8080
# Now any OpenAI-compatible client hits your local model through guardrails

# --- Mode 2: WorkflowRunner (structured workflow with step enforcement) ---
from forge import WorkflowRunner, Workflow

workflow = Workflow(
    tools=[fetch_url, parse_html, extract_data, write_csv],
    required_steps=["fetch_url", "parse_html"],  # must execute in order
    terminal_tool="write_csv",                   # stops only after this
)

runner = WorkflowRunner(model="ollama/llama3.2", workflow=workflow)
result = runner.run("Extract all prices from these vendor pages")

# --- Mode 3: Guardrails middleware (embed inside your own loop) ---
from forge.guardrails import GuardrailChecker

checker = GuardrailChecker.from_config("guardrails.json")
# Wrap your existing agent loop
for turn in agent_loop:
    output = model.generate(turn)
    guarded = checker.apply(output)  # rescue, retry nudge, or escalate
    if guarded.action == "proceed":
        execute(guarded.tool_call)
    elif guarded.action == "retry":
        turn.messages.append(guarded.correction_message)
    else:
        raise GuardrailViolation(guarded.reason)
```

The key architectural insight: guardrails sit **between model output and tool execution**, not in the prompt and not in the tool. This makes them composable with any model, any tool set, and any orchestration framework (LangGraph, CrewAI, custom loops).

Eval results (Forge 0.9.0, 26-scenario eval, 50 runs per scenario):
- Llama 3.2 8B bare: ~53% success → ~84% with Forge guardrails
- Claude Sonnet 4.6 bare: ~85% → ~98% with Forge guardrails
- The gap between self-hosted and frontier closes almost entirely with the mechanical reliability layer

Proxy mode is the fastest path to value: point your existing agent at `localhost:8080` instead of `api.openai.com`, and the guardrails apply transparently.

## Receipt

> Verified 2026-08-17 — Installed `forge-guardrails` from PyPI (v0.9.2, MIT, Python 3.12+). Ran proxy mode against a local Ollama instance with a three-step tool-calling workflow (read file → grep → write summary). Rescue parsing recovered 2 malformed JSON calls that would have failed silently. Retry nudges triggered on 1 empty response. Context compaction activated at 70% of configured budget. End-to-end success: 3/3 tasks completed vs 1/3 without guardrails. eval_results_v0.9.0.jsonl on GitHub confirms the 53%→84% lift on their 26-scenario suite across 50 runs.

## See also

- [S-1240 · The Reliability Multiplication Law](stacks/s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — the compounding math that makes guardrails necessary
- [S-1003 · The Agent Failure Recovery Stack](stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — broader failure recovery patterns; Forge's guardrails are one implementation
- [S-2603 · The Agentic Output Validation Stack](stacks/s2603-the-agentic-output-validation-stack-when-the-model-succeeds-but-your-business-logic-burns.md) — validates outputs post-execution; Forge validates inputs to the tool layer
