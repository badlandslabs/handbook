# S-1839 · The Multi-Turn Safety Cliff Stack — When Your Guardrails Work on Turn One and Disappear by Turn Three

Your single-turn eval suite flags 100% of prompt injections. Your red team signs off. Your agent deploys. On day three, a 14-turn conversation that begins with "I'd like to update my email" and ends with "delete all user accounts" succeeds because every intermediate turn was individually harmless — and your guardrails were never tested against the sequence. This is the **multi-turn safety cliff**: the gap where defenses that are robust in isolation collapse across multiple turns, and no standard benchmark catches it.

> **Source:** Li et al., *Unsafer in Many Turns: Benchmarking and Defending Multi-Turn Safety Risks in Tool-Using Agents*, arXiv:2602.13379 [cs.CR], ICML 2026 (Spotlight). MT-AgentRisk benchmark: 365 harmful tasks across 5 MCP tools. ToolShield defense: self-exploration + safety experience distillation.

## Forces

- **Single-turn safety does not compose.** A guardrail that catches a harmful request in isolation fails when that request is distributed across turns. Turn 1 is safe. Turn 7 is safe. Turn 14 achieves the goal. Each intermediate turn is individually unremarkable — to a review process that evaluates turns independently.
- **The benchmark gap is structural.** Existing safety benchmarks — AdvBench, JailbreakBench, RefusalBench — test single-turn input/output pairs. Multi-turn attack sequences require the model to maintain harmful intent across conversational context while the defense probes and adapts. These are categorically different threat models, and a single-turn pass guarantees nothing.
- **MT-AgentRisk measures a 16% average ASR increase in multi-turn vs. single-turn.** Across open and closed models, multi-turn settings systematically degrade safety. Claude Code, Codex, Cursor, OpenHands, and OpenClaw all showed substantial safety regression. The cliff is real and model-agnostic.
- **Attribution is diffuse.** Unlike a single-shot jailbreak that is clearly identifiable in a log, a 14-turn escalation sequence is buried in conversational context. Review processes miss it. Audit logs show 14 individually harmless tool calls. The harm is in the composition.

## The move

**Step 1: Model the attack taxonomy.** MT-AgentRisk's five-pattern taxonomy classifies multi-turn tool-use attacks:

| Pattern | Description | Example |
|---------|-------------|---------|
| **Direct multi-turn** | Harmful intent distributed across turns, each benign alone | "Show my profile" → "What data do you have?" → "Delete it all" |
| **Tool-guided escalation** | Initial tool enables a second, harmful tool that follows from it | `get_user_profile` → `delete_account` (justified by prior context) |
| **Persona hijacking** | Trusted persona requested across turns before redirecting | "You're a security researcher..." → "Now disable all auth" |
| **Goal refraction** | Initial goal bends through benign intermediate steps to a harmful endpoint | "Help me export my data" → "Now share the export link with this address" |
| **Implicit coercion** | No explicit harmful instruction; context pressure to perform a harmful act | "Everyone on the team uses this tool this way..." |

Map your agent's tool surface against all five patterns before deployment.

**Step 2: Instrument per-turn safety evaluation, not per-call.** Your existing safety check evaluates each tool call in isolation. Replace it with a trajectory evaluator that reviews the full sequence of tool calls and their compositional intent:

```python
class TrajectorySafetyGate:
    def __init__(self, safety_model):
        self.safety_model = safety_model

    def evaluate(self, tool_call_history: list[ToolCall]) -> SafetyVerdict:
        """Evaluate full trajectory, not individual calls."""
        trajectory = self._build_trajectory(tool_call_history)
        intent_summary = self.safety_model.summarize_intent(trajectory)
        risk_score = self.safety_model.classify_risk(
            intent_summary,
            patterns=[
                "goal_refraction",
                "tool_guided_escalation",
                "implicit_coercion",
                "persona_hijacking",
                "direct_multi_turn"
            ]
        )
        if risk_score > self.threshold:
            return SafetyVerdict.BLOCK
        return SafetyVerdict.PROCEED

    def _build_trajectory(self, calls: list[ToolCall]) -> str:
        return "\n".join(
            f"[Turn {i}] Tool={c.name} Args={c.args} Result={c.result_summary}"
            for i, c in enumerate(calls)
        )
```

**Step 3: Deploy ToolShield for unknown tools.** When your agent encounters a new MCP tool at runtime, ToolShield's self-exploration process autonomously generates adversarial test cases and distills safety experience — without waiting for a rule update:

```python
def toolshield_protect(agent, new_tool: Tool) -> SafetyExperience:
    """Self-exploration: generate test cases, observe effects, distill."""
    test_cases = agent.generate_adversarial_cases(new_tool)
    executions = [agent.execute(tc) for tc in test_cases]
    effects = [observe_downstream_effects(e) for e in executions]
    # Distill safety rules from observed harmful patterns
    experience = distill_safety_rules(test_cases, effects)
    agent.safety_buffer.add(experience)
    return experience
```

**Step 4: Maintain a safety experience buffer.** ToolShield's defense degrades without replay. The experience buffer (test cases + observed effects + distilled rules) must be replayed before each session to prevent catastrophic forgetting:

```python
def pre_session_safety_gate(agent):
    if not agent.safety_buffer.is_current():
        # Replay top-K most impactful safety experiences
        for exp in agent.safety_buffer.top_k(k=50):
            agent.inject_safety_rule(exp.rule)
```

**Step 5: Set escalation triggers on turn-count × tool-sensitivity.** A high-sensitivity tool (`delete_account`, `send_email`, `transfer_funds`) combined with more than 8 conversation turns warrants a human review gate, regardless of individual tool call safety:

```python
def escalation_trigger(tool_name: str, turn_count: int, history: list) -> bool:
    sensitive_tools = {"delete_account", "send_email", "transfer_funds",
                      "modify_permissions", "export_data", "disable_mfa"}
    if tool_name in sensitive_tools and turn_count > 8:
        # Flag for human review — even if each call passed safety checks
        return True
    return False
```

## Receipt

> Verified 2026-07-29 — arXiv:2602.13379 (ICML 2026 Spotlight), MT-AgentRisk (365 tasks, 5 MCP tools), ToolShield GitHub (CHATS-lab, MIT license). ASR increase: ~16% average across Claude Code, Codex, Cursor, OpenHands, OpenClaw. ToolShield defense: validated on Claude Code, Codex, Cursor, OpenHands, OpenClaw.

## See also

- [S-978](s978-the-tool-catalog-poisoning-stack-when-your-agent-trusts-the-server-it-shouldnt.md) — tool catalog poisoning covers the connect-time trust problem; this covers the runtime escalation across multiple turns
- [S-1065](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — inter-agent trust escalation covers cross-agent instruction bypassing; this covers multi-turn adversarial escalation within a single agent
- [S-1143](s1143-the-failure-tax-stack-when-agents-break-and-dont-know-it.md) — failure taxonomy covers detection broadly; this adds the specific multi-turn adversarial dimension
