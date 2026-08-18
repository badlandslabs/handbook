# S-2811 · The State-Grounded Synthetic Data Stack — When Your Training Data Has More Tool-Call Hallucinations Than Your Agent

When you fine-tune a domain-specific agent and it gets worse — same hallucinations, new vector. The culprit is almost always the training data: synthetic trajectories generated without authoritative state ground-truth produce tool-call hallucinations that the agent learns, then replicates in production. You trained the error in.

## Forces

- **Tool-call hallucination is the dominant failure mode in tool-augmented agents.** StateGen (PayPal, arXiv:2606.16307) found tool-call hallucination scores of 9.x/10 across 64,698 evaluated conversations on synthetic data generated without state grounding. The agent confidently calls `DELETE /users/123` — a table that doesn't exist. The training data said it did.
- **Naive synthetic generation reproduces the problem it aims to solve.** If you generate trajectories by letting an LLM simulate tool responses, the LLM simulates wrong tool responses. The agent learns the simulation's errors. Adding a judge helps but doesn't fix the root cause — the generator and the ground-truth are the same system.
- **Privacy and scale make human annotation impractical.** Production trajectories are privacy-constrained. Public benchmarks don't cover your domain. You need synthetic data that covers your actual tool schema, API contracts, and business logic — at scale.
- **The backend-is-truth invariant is the breakthrough.** If you can make the authoritative backend (the real API, the real database, the real tool) the ground-truth source during generation, tool-call hallucinations become structurally impossible — not just statistically unlikely.

## The move

Build a state-grounded synthetic data pipeline with four roles:

```
User Simulator → Agent Under Test → State Manager (authoritative) → Tool Simulator → Judge
```

### 1. Define the world-state schema

Before generating a single trajectory, define the authoritative state object for your domain:

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class BookingState:
    reservations: dict[str, dict] = field(default_factory=dict)
    refunds: dict[str, dict] = field(default_factory=dict)
    emails_sent: list[str] = field(default_factory=list)
    _lock: bool = False  # state serialization guard

    def apply(self, tool_name: str, args: dict, result: Any) -> bool:
        """Apply a verified tool call result to state. Returns False if
        the call was invalid (no-op rollback)."""
        if tool_name == "create_reservation":
            self.reservations[result["id"]] = result
            return True
        elif tool_name == "process_refund":
            if result["status"] == "success":
                self.refunds[result["refund_id"]] = result
            return True
        # ... etc
        return False
```

### 2. The four-role generation loop

```python
class StateGenPipeline:
    def __init__(self, state: BookingState, tool_registry: ToolRegistry):
        self.state = state
        self.tools = tool_registry
        self.user_sim = PersonaSimulator()
        self.judge = MultiAxisJudge()
        self.stats = {"tool_hallucinations": 0, "valid_calls": 0}

    def generate_trajectory(self, persona: str, task: str) -> Trajectory:
        messages = []
        self.state.reset()
        step = 0
        max_steps = 12

        while step < max_steps:
            # User turn: persona-conditioned simulator generates next sub-task
            user_msg = self.user_sim.next(persona, messages, self.state)
            messages.append({"role": "user", "content": user_msg})

            # Agent turn: LLM selects tool + args from context
            agent_response = self.agent.generate(messages)
            tool_call = parse_tool_call(agent_response)
            messages.append({"role": "assistant", "tool_call": tool_call})

            # Ground-truth execution: use REAL tool via state manager
            # NOT a simulated response from the LLM
            try:
                result = self.tools.execute(tool_call.name, tool_call.args)
                # CRITICAL: verify the call against authoritative state
                if not self.state.apply(tool_call.name, tool_call.args, result):
                    self.stats["tool_hallucinations"] += 1
                    # Flag: agent called a tool that would fail in real execution
                    result = {"error": "STATE_REJECTED", "reason": "invalid_state_transition"}
            except ToolNotFoundError:
                self.stats["tool_hallucinations"] += 1
                result = {"error": "TOOL_NOT_FOUND", "tool": tool_call.name}

            # Authoritative tool response (real, not simulated)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)})

            # Judge scores this step
            score = self.judge.score(messages[-3:], self.state)
            if score.is_terminal:
                break
            step += 1

        return Trajectory(messages=messages, score=self.judge.aggregate(), stats=self.stats)

    def generate_dataset(self, n: int = 10000) -> Dataset:
        """Generate n trajectories across persona × task matrix."""
        results = []
        for persona in PERSONAS:
            for task in TASKS:
                for _ in range(n // (len(PERSONAS) * len(TASKS))):
                    t = self.generate_trajectory(persona, task)
                    results.append(t)
        return Dataset(trajectories=results)
```

### 3. The hierarchical multi-agent extension

Declare sub-agents as tools — they share the same authoritative state object:

```python
# In tool_registry setup:
registry.register("refund_agent", RefundSubAgent(state_ref=booking_state))
registry.register("email_agent", EmailSubAgent(state_ref=booking_state))
# Both sub-agents can only see state that exists in the authoritative state object.
# If a sub-agent claims it sent an email, the state must have it in emails_sent.
```

### 4. Key metrics from StateGen results (PayPal, 64,698 conversations)

| Metric | Naive Synthetic | StateGen (state-grounded) |
|--------|---------------|---------------------------|
| Tool-call hallucination rate | ~9.x / 10 | ~1.x / 10 |
| Multi-turn coherence | low | high |
| State consistency at handoff | breaks often | invariant holds |
| Transfer to production | fragile | strong |

### Key signals to capture

- **Backend-is-truth execution** — always execute via real tool, never simulated LLM response
- **State apply/rollback** — every tool result gets applied to authoritative state; invalid calls get flagged, not silently discarded
- **Sub-agent state sharing** — hierarchical agents share the same state object, not copies
- **Multi-axis judge** — score tool correctness, trajectory efficiency, recovery quality, and goal adherence independently

## Receipt

> Verified 2026-08-18 — Researched arXiv:2606.16307 (Khedar et al., PayPal, June 2026), AgentMarketCap April 2026 synthetic data analysis, NVIDIA NeMo RL agent fine-tuning documentation. StateGen architecture confirmed: 4-role LLM loop (user simulator, agent under test, authoritative state manager, multi-axis judge) with backend-is-truth invariant. Key metric: tool-call hallucination scores reduced from ~9.x to ~1.x on 64,698 evaluated conversations. Pattern distilled: the generation system and ground-truth must be architecturally separate to avoid self-referential hallucination loops.

## See also

- [S-2807 · The Benchmark Contamination Stack](stacks/s2807-the-benchmark-contamination-stack-when-your-swe-bench-score-is-really-a-training-data-leak.md) — contamination in eval data; this entry covers contamination in *training* data
- [S-2775 · The False Success Stack](stacks/s2775-the-false-success-stack-when-your-agent-declares-victory-and-the-environment-disagrees.md) — false success is downstream of the same root: agents acting on non-verified state
- [R-16 · Agent Harness Sensitivity](stacks/r16-agent-harness-sensitivity.md) — what happens when your training distribution doesn't match your evaluation distribution
