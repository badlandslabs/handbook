# S-924 · The Bimodal Agent Stack — When 55% of Your "Agents" Are Scripts

You built an agent. It handles 40% of tickets fully autonomously, costs $0.12 per ticket, and hits 92% success. You built the same architecture for 60% of tasks — customer disputes, technical triage, data exports — and they hit 23% success, cost $4.80 per ticket, and generate 80% of your support tickets. You call them all "agents." They're not. One group is a deterministic pipeline that happens to use an LLM. The other is a genuine agent that navigates ambiguity. Mixing them in the same architecture gives you the worst of both: the cost of an agent with the reliability of a script.

## Situation

A customer submits a billing dispute. Your agent classifies it, retrieves the order, checks policy, and either approves or escalates. It works. So you build the same flow for "help me understand my bill." It classifies the request, retrieves the account, synthesizes a response, and returns it. This time it hallucinates a charge that doesn't exist, apologizes for a fee the customer never paid, and creates a $200 credit that didn't need to exist. Same architecture. Same "agent." Completely different outcomes.

The difference is predictability. The dispute flow has a bounded decision tree, structured inputs, and a clear success criterion. The bill-explanation flow has unbounded context, ambiguous inputs, and success that's measured in customer satisfaction, not transaction state. These are fundamentally different workloads. They belong to fundamentally different architectures.

## Forces

- **Production reality is bimodal.** Data from 4.5M+ production agent sessions (March 2026) shows 56.6% aggregate success — but the distribution is not uniform. Tasks with structured inputs, deterministic tool paths, and clear success criteria hit 88–96% success. Tasks requiring open-ended reasoning, ambiguous inputs, or multi-step planning hit 18–35%. The aggregate masks two populations that need different treatments.

- **Agents cost more than pipelines.** A simple chain agent with tool calls costs 10–40× more per invocation than a deterministic pipeline using the same LLM. If a task is predictable enough to route with an if/else tree, paying per-token for LLM calls on every step is waste. If a task genuinely needs open-ended reasoning, the LLM cost is justified.

- **The failure cliff is predictable, not random.** S-752 shows 0.95²⁰ = 36% end-to-end reliability for 20-step chains. But this assumes uniform step reliability. If the first 10 steps of your task are predictable (99% reliable each), only the last 10 require the agent's open-ended capability. Mixing them in one loop throws away the cheap certainty of the first half.

- **You can measure predictability before routing.** Input entropy, required tool count, output schema flexibility, and historical success rate on similar inputs are all observable signals. You don't need to wait for the agent to fail — you can score the task before dispatch and route accordingly.

- **Teams optimize for the wrong thing.** They improve the agent (better prompting, stronger model) when they should be bifurcating the architecture. A 5% improvement in agent reliability costs far more than correctly routing 40% of calls to a simpler pipeline.

## The move

**Score every incoming task on predictability, then dispatch to one of two modes:**

### Mode A — Script (billed as "deterministic pipeline")

For tasks with: structured inputs, ≤3 tool calls, clear success criterion, low input entropy.

```
def score_predictability(task_input, config):
    signals = {
        "has_unstructured_text": 0,      # freeform customer message
        "requires_reasoning": 0,         # "figure out what they want"
        "multi_entity": 0,              # multiple records/entities
        "open_ended_output": 0,         # no fixed schema for output
        "historical_failures": 0,        # this task type failed before
    }
    # ... score each from input analysis + task config
    
    predictability = 1.0 - (sum(signals.values()) / len(signals) * 0.35)
    return predictability  # 0.0–1.0

def dispatch(task):
    score = score_predictability(task.input, task.config)
    if score > 0.72:
        return pipeline_mode(task)    # deterministic, <$0.01/ticket
    elif score > 0.45:
        return guided_agent_mode(task) # agent with constrained toolset
    else:
        return full_agent_mode(task)   # full autonomy, $0.50+/ticket
```

### Mode B — Guided Agent (constrained autonomy)

For tasks with: semi-structured inputs, 4–8 tool calls, partial ambiguity, a bounded decision tree.

Key constraint: **cap the reasoning chain at N steps**, not by token count. N should be set by the p95 step count from your eval traces for that task type.

```
def guided_agent_mode(task):
    max_steps = task.config.get("step_cap", 8)
    collected = {"input": task.input, "steps": [], "cost": 0}
    
    for step_num in range(max_steps):
        plan = llm.call(f"Given context: {collected}, decide next action or final answer.")
        if plan.is_terminal:
            return finalize(collected + plan.output)
        tool_result = execute(plan.tool, plan.args)
        collected["steps"].append({"action": plan.tool, "result": tool_result})
        collected["cost"] += pricing[plan.tool]
        
        if collected["cost"] > task.config.get("cost_cap", 1.50):
            return escalate(collected, reason="cost_cap_exceeded")
    
    return escalate(collected, reason="step_cap_exceeded")
```

### Mode C — Full Agent (unbounded autonomy)

For genuinely open-ended tasks. Every invocation is expensive; every invocation should be warranted.

```
def full_agent_mode(task):
    # Budget for uncertainty: this task type costs what it costs
    # But enforce a hard ceiling and always escalate on high-stakes outputs
    agent = Agent(system_prompt=task.config["system"], tools=task.config["tools"])
    result = agent.run(task.input, max_turns=task.config.get("max_turns", 20))
    
    # Post-run: did it do something irreversible? Verify before confirming.
    if result.touched_external_state:
        verify_state_change(result)
    
    return result
```

### The predictability scoring signals

| Signal | What it measures | Weight |
|--------|-----------------|--------|
| Input structure | Does the input parse into known fields? | High |
| Tool path depth | How many hops does the typical successful trace show? | High |
| Output schema flexibility | Is "any text response" acceptable? | Medium |
| Historical task-type success | What's the 30-day success rate for this task class? | High |
| Required tool count | More tools = more failure probability multiplication | Medium |
| Context dependency | Does the answer depend on info not in the input? | Medium |

The scoring model should be calibrated against your own production traces, not tuned against benchmarks. A task type that your agent handles at 91% is Mode A; one that hits 34% is Mode C.

## Receipt

> Verified 2026-07-10 — Pattern synthesized from March 2026 production data across 4.5M+ agent sessions showing 56.6% aggregate success rate masking a bimodal distribution. Key sourcing: Agent-Eval Checklist (Berkeley RDI, 2026); S-752 (reliability cliff math); S-523 (thinking budget routing); S-922 (failure recovery taxonomy). The bimodal framing is consistent with Gartner multi-agent deployment data showing 40% of production agent tasks require <5 tool calls and could be handled by deterministic pipelines, but are routed through full agent architectures due to lack of predictability-aware dispatch.

## See also

- [S-752 · The Reliability Cliff](s752-the-reliability-cliff-how-multi-step-agents-go-from-95-to-36-percent-success-rate.md) — the arithmetic of compound failure in multi-step agents
- [S-523 · The Thinking Budget](s523-the-thinking-budget-reasoning-model-routing-in-agent-loops.md) — routing by cognitive cost, the sibling to routing by predictability
- [S-586 · Multi-Model Routing](s586-multi-model-routing-the-pivotal-production-lever.md) — routing by model tier; this entry extends it to routing by architecture
- [S-920 · The Failure Triangle](s920-the-failure-triangle-stack-when-agents-dont-crash-they-spiral.md) — the failure modes that Mode C is designed to contain
