# S-1128 · The Agent Washing Stack — When Your Vendor Calls It an Agent But It's Just a `while True` Loop

You signed a contract for an "AI agent" that costs $2.40 per task. Your team later discovers it makes 8–15 internal API calls per task — all billable — and the "autonomous decision-making" is a hardcoded if/else tree with a GPT wrapper. The vendor's ROI deck showed 40% cost reduction. Your actual invoices show a 4x increase over the scripted automation it replaced. This is Agent Washing: the practice of rebranding existing automation as an AI agent to justify premium pricing, without delivering genuine autonomous capabilities.

## Forces

- **The capability gap is invisible from the outside.** Without a diagnostic framework, a 50-line Python script calling GPT-4 and a production-grade autonomous agent look identical in a vendor demo. Both take input, call a model, return output.
- **The price-to-capability mismatch is catastrophic.** Real agents cost $0.30–8.00/task due to multi-step reasoning, tool orchestration, and memory. Fake agents often cost more than the scripts they replaced — because every internal LLM call in the loop is billable.
- **Enterprise buyers are buying marketing, not architecture.** Gartner estimates only ~130 of thousands of vendors claiming agentic capabilities actually build genuinely autonomous systems. 40%+ of agentic projects will be cancelled by end of 2027 — not because agents fail, but because the systems deployed were never agents to begin with.
- **The failure mode is discovered post-deployment.** The RAND finding that 80–90% of "AI agent projects" fail is largely explained by agent washing: teams built pipelines and expected agents, then couldn't figure out why the system couldn't handle novel situations.

## The move

**Distinguish pipelines from agents at the architecture level, not the marketing level.**

### The five-axis diagnostic

A real AI agent has a **closed loop** containing all five:

1. **Perception** — reads environment state (DB, APIs, file system, user input). Not just user input.
2. **Reasoning** — decides what to do next, including when to stop. Not a fixed sequence.
3. **Action** — executes tools with real side effects. Not just text output.
4. **Memory** — persists context across invocations. Not stateless per-request.
5. **Autonomy** — operates without human input for routine decisions. Not a human-in-the-loop for every step.

```
# Pipeline (NOT an agent)
def pipeline(user_input):
    prompt = system_prompt + user_input
    return gpt4.call(prompt)

# Agent (architecture check — does it have all five?)
class Agent:
    def __init__(self):
        self.memory = MemoryStore()          # 4. Memory
        self.tools = ToolRegistry()           # 3. Action
    
    def step(self, env_state):               # 1. Perception
        ctx = self.memory.read()
        decision = self.reason(ctx, env_state)  # 2. Reasoning
        if not decision.should_act():
            return HALT                       # 2. Reasoning (knows when to stop)
        result = self.tools.act(decision)    # 3. Action
        self.memory.write(result)            # 4. Memory
        return result                         # 5. Autonomy (no human gate per step)
```

### The six question diagnostic

Before signing any agent contract or building any agent project, answer:

| # | Question | Real Agent Answer | Fake Agent Answer |
|---|----------|-------------------|-------------------|
| 1 | Does the system perceive environment state beyond the user's current message? | Yes — reads DB, APIs, files | No — only user input |
| 2 | Can it make a different decision on the same input depending on prior context? | Yes — memory affects reasoning | No — stateless |
| 3 | Does it decide when to stop without being told? | Yes — goal-achieved detection | No — fixed turn count |
| 4 | Can it recover from a tool failure and try alternatives? | Yes — replan loop | No — crashes or returns error |
| 5 | Does it execute actions with side effects beyond text? | Yes — writes, sends, updates | No — only text output |
| 6 | Does its cost scale with the complexity of the goal, not just token count? | Yes — step budget ≠ fixed cost | No — fixed cost per run |

### The cost sanity check

If a vendor quotes a flat per-task price but the system internally makes 8–15 model calls, the actual cost model is exposed: each internal call is billable. Run the task manually and count the internal calls. Compare against the cost of a well-scoped script.

```
# Quick internal call counter (via proxy: log every LLM invocation)
import functools

original_call = openai.ChatCompletion.create
call_count = 0

def counting_call(*args, **kwargs):
    global call_count
    call_count += 1
    return original_call(*args, **kwargs)

openai.ChatCompletion.create = counting_call

# Run 10 tasks
for task in task_set:
    agent.run(task)
    
print(f"Internal calls per task: {call_count / 10}")
print(f"Estimated cost per task at $0.03/1K input + $0.06/1K output: ${estimate()}")
```

### The build-vs-buy signal

Genuine agents require: durable state management, tool orchestration, error recovery, memory partitioning, autonomy governance, and observability across a reasoning trace. If a vendor can't explain how they handle these — not just that they do — the system is likely a scripted loop.

**Rule:** If you can't name what each component does in one short sentence, the system is probably a pipeline pretending to be an agent.

## Receipt

> Verified 2026-07-15 — Source: OpenClaw Research "Agent Washing in AI" (March 2026), Particula Tech "Agent Washing: Why 95% of AI Agents Are Just Expensive Chatbots" (March 2026), The Daily Agent DEV community post (March 2026), Gartner agentic AI market analysis (2025–2026), RAND study on AI agent project failure rates. 130 genuine agentic vendors out of thousands claiming agent status confirmed by multiple independent sources. 40%+ cancellation rate attributed in part to capability mismatch rather than fundamental agent limitations. The diagnostic framework is synthesized from the five-axis agent definition and six-question checklist from three independent sources.

## See also
- [S-285 · The MCP Compound Probability Stack](stacks/s285-the-mcp-compound-probability-stack-when-7-servers-become-a-command-chain.md) — tool integration risk (related: agent tool execution surface)
- [S-09 · Memory Systems](stacks/s09-memory-systems.md) — memory as a distinguishing axis (absence of memory = fake agent)
- [S-614 · The Authorized Intent Chain Stack](stacks/s614-the-authorized-intent-chain-when-agents-bypass-every-security-control.md) — what genuine agentic capability means for security boundaries
