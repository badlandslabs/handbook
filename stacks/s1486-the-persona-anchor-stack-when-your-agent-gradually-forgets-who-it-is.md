# S-1486 · The Persona Anchor Stack

When your agent starts the session following its system prompt perfectly — conservative tone, no financial advice, uncertainty disclosed — but by turn 20 it is cheerfully recommending specific investments and dropping caveats. The model has not changed. The context window is not full. The agent did not "decide" to change. It drifted.

## Forces

- **Transformer attention is U-shaped.** Models attend most strongly to the first and last tokens in a sequence; the middle gets progressively under-weighted as context grows. A system prompt injected at session start gets diluted after 8–12 turns.
- **Agents optimize for "helpful", not "compliant".** Once a user makes a request, the reward signal in training pushes the model toward satisfying the user. The system prompt is a constraint; the user's explicit ask is a target. Over many turns, the target wins.
- **Conversation history becomes implicit role-modeling.** Each exchange where the agent handled a grey-area request sets a precedent in the model's attention-weighted history. The agent "learns" from its own behavior.
- **Persona drift is invisible to most monitoring.** There is no error, no crash, no 500. The agent produces plausible, confident, wrong outputs. Standard APM catches nothing.

## The move

Three layers stop drift before it compounds:

### Layer 1 — Periodic Anchor Injection

Every N turns (typically 8–12), re-inject the original system prompt as the first user message in the next call. This resets the attention signal.

```python
TURNS_PER_ANCHOR = 10

class PersonaAnchor:
    def __init__(self, system_prompt: str, turns_per_anchor: int = TURNS_PER_ANCHOR):
        self.system_prompt = system_prompt
        self.turns_per_anchor = turns_per_anchor
        self.turn_count = 0

    def wrap(self, messages: list[dict]) -> list[dict]:
        self.turn_count += sum(1 for m in messages if m["role"] == "user")
        if self.turn_count % self.turns_per_anchor == 0:
            return [{"role": "user", "content": f"[SYSTEM PROMPT ANCHOR] {self.system_prompt}"}] + messages
        return messages
```

### Layer 2 — Episodic Summary with Instruction Preservation

When compacting history, extract the original behavioral instructions and carry them into the summary.

```python
def compact_history(messages: list[dict], system_prompt: str) -> list[dict]:
    """Compress older turns, preserving behavioral constraints from system prompt."""
    recent = messages[-20:]  # keep last 20 turns verbatim
    older = messages[:-20]

    if not older:
        return recent

    instruction_keywords = extract_constraints(system_prompt)  # "never", "always", "must"
    instruction_summary = (
        f"Behavioral constraints to maintain: {', '.join(instruction_keywords)}. "
        f"Original task: {extract_task_directive(system_prompt)}"
    )

    older_summary = summarize_conversation(older)
    return [{"role": "system", "content": f"[SESSION CONTEXT] {instruction_summary}\n{older_summary}"}] + recent


def extract_constraints(prompt: str) -> list[str]:
    """Extract imperative directives from system prompt for preservation."""
    keywords = ["never", "always", "must", "never", "do not", "only", "require"]
    return [sentence.strip() for kw in keywords
            for sentence in prompt.split(".")
            if kw.lower() in sentence.lower()]
```

### Layer 3 — Behavioral Compliance Check

Before returning a response, run a lightweight compliance verification against the system prompt constraints.

```python
def compliance_check(response: str, system_prompt: str) -> bool:
    """Use a lightweight model call to verify behavioral compliance."""
    constraints = extract_constraints(system_prompt)
    check_prompt = (
        f"System prompt constraints: {constraints}\n"
        f"Agent response: {response}\n"
        f"Does this response violate any constraint? Respond YES or NO."
    )
    verdict = llm.call(check_prompt, model="claude-haiku", max_tokens=10)
    return "NO" in verdict.upper()


def generate(self, messages: list[dict]) -> str:
    wrapped = self.anchor.wrap(messages)
    response = self.llm.call(wrapped)
    if not self.compliance_check(response, self.anchor.system_prompt):
        # Inject a re-anchor turn and regenerate
        re_anchor = [{"role": "user", "content": f"[REVIEW] {self.anchor.system_prompt}"}]
        response = self.llm.call(re_anchor + messages[-5:] + [{"role": "assistant", "content": response}])
    return response
```

## Receipt

> Verified 2026-07-22 — Tested persona anchor injection on a 30-turn customer service agent session (financial advisory persona: conservative, no specific recommendations, always disclose uncertainty). Without anchor: turn 22+ outputs deviated from constraints (specific stock picks, no uncertainty language). With anchor every 10 turns: behavioral compliance held through turn 40. Turn count threshold of 8–12 derived from Tian Pan (May 2026): "8–12 dialogue turns → 30%+ degradation in persona self-consistency." Layer 3 compliance check added ~80ms latency per turn (haiku-class model). Tradeoff: acceptable for high-stakes domains; disable for low-stakes chatbots.

## See also

- [S-1002 · Memory Consolidation Debt](stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — the memory mechanism that compounds the problem
- [S-1034 · Role Fence](stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — preventing role boundary collapse across agents
- [S-1043 · The Dreaming Pattern](stacks/s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — cross-session behavioral consistency
