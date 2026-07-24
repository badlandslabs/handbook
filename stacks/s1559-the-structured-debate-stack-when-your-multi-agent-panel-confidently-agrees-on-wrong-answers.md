# S-1559 · The Structured Debate Stack — When Your Multi-Agent Panel Confidently Agrees on Wrong Answers

Multi-agent debate sounds like a solution: three agents review a plan, vote, and the majority wins. But if the agents share a model, a context window, or a retrieval source — and they almost always do — the vote is noise dressed as consensus. The failure mode is invisible: the panel looks rigorous, each agent sounds confident, and the agreed-upon answer is subtly, consistently wrong. The Structured Debate Stack is the protocol design that makes debate actually earn its confidence.

## Forces

- **Naive voting amplifies shared blind spots.** Three agents on the same base model fail on the same inputs, the same way. Majority vote doesn't average errors — it concentrates them into a confident consensus.
- **Visibility kills independence.** Once Agent A's answer is visible to B and C, their votes are no longer independent. LLMs exhibit conformity bias even without pressure — a stated majority tilts the holdouts.
- **Debate without structure is performance.** Unstructured "discuss until you agree" converges on whichever agent speaks most persuasively, not whichever answer is correct.
- **Correct answers don't always win.** An agent with the right minority view gets overridden by a confidently wrong majority. Standard voting has no mechanism to weight confidence or track which agent was right in similar past cases.
- **Classical consensus fails.** Paxos and Raft assume deterministic state machines. LLM agents are stochastic, context-sensitive, and capable of reasoning about the debate itself — which breaks the assumptions of traditional distributed consensus.

## The move

Structured debate imposes explicit protocol stages that preserve independence until the final aggregation, and weights votes by calibrated confidence rather than raw assertion.

### Stage 1 — Independent Thesis (no visibility)

Each agent produces an answer **without seeing other agents' outputs**. Arguments are sealed. This preserves statistical independence of errors — the core requirement that S-29's false consensus destroys.

```
def stage1_independent_thesis(agents: list[Agent], prompt: str) -> list[AgentOutput]:
    outputs = []
    for agent in agents:
        # No cross-pollination. Agent sees only the prompt + its own system prompt.
        result = agent.run(prompt, context=agent.private_context)
        outputs.append({
            "agent_id": agent.id,
            "answer": result.answer,
            "confidence": result.confidence,  # 0.0–1.0, calibrated
            "argument": result.reasoning_trace,
            "key_assumptions": result.assumptions,
            "sealed_at": timestamp()
        })
    return outputs
```

### Stage 2 — Sealed Cross-Examination

Each agent receives **summaries** of other agents' arguments (not their final answers). They must identify the weakest assumption in each and respond. This surfaces disagreement vectors without revealing which answer "won."

```
def stage2_cross_examination(agent_outputs: list[AgentOutput], agents: list[Agent]) -> list[Critique]:
    critiques = []
    for agent in agents:
        other_arguments = [a["argument"] for a in agent_outputs if a["agent_id"] != agent.id]
        critique_prompt = (
            f"Your answer was: {agent.private_answer}\n\n"
            f"Other agents argued:\n" + "\n".join(other_arguments) + "\n\n"
            f"Identify the weakest assumption in each argument and explain why it might be wrong."
        )
        result = agent.run(critique_prompt)
        critiques.append({"agent_id": agent.id, "critique": result.critique})
    return critiques
```

### Stage 3 — Confidence-Weighted Revote

Agents re-answer with their critique knowledge, but votes are weighted by **calibrated confidence** (not assertion confidence). Use a reference set to calibrate: "How often were you right when you said 70% confidence?" Without calibration, high-confidence wrong answers dominate.

```
def stage3_confidence_weighted_vote(agent_outputs: list[AgentOutput], critiques: list[Critique]) -> Decision:
    # Calibration: each agent has a reliability_score from a reference eval set
    weighted_votes = defaultdict(float)
    for output, critique in zip(agent_outputs, critiques):
        # Confidence weighted by historical reliability on similar question types
        weight = calibrate_confidence(output.confidence, output.agent_reliability)
        weighted_votes[output.answer] += weight

    final_answer = max(weighted_votes, key=weighted_votes.get)
    confidence = weighted_votes[final_answer] / sum(weighted_votes.values())
    return Decision(answer=final_answer, confidence=confidence, vote_distribution=dict(weighted_votes))
```

### Stage 4 — Dissenting Agent Review

Before committing, the agent with the lowest weighted vote (the dissent) reviews the majority answer and explicitly flags any remaining concerns. This is the human-in-the-loop analog: minority opinion gets a mandatory hearing.

```
def stage4_dissent_review(majority_answer: str, dissenting_agents: list[Agent], context: dict) -> ReviewResult:
    concerns = []
    for agent in dissenting_agents:
        result = agent.run(
            f"Review this answer for remaining errors, edge cases, or risks.\n"
            f"Answer: {majority_answer}\nContext: {context}"
        )
        concerns.append(result.concerns)
    return ReviewResult(concerns=concerns, approved=len(concerns) == 0)
```

### Byzantine Fault Tolerance for Agents

If ≥N agents can produce "Byzantine" (arbitrary, including adversarial) outputs, use a Byzantine fault-tolerant variant: require 2N+1 agents minimum, and accept the answer that N+1 agents agree on regardless of other agents' behavior.

```
def byzantine_consensus(agents: list[Agent], prompt: str, f: int) -> Decision:
    # f = number of potentially faulty (Byzantine) agents
    # Need at least 3f+1 agents total
    require(len(agents) >= 3*f + 1, f"Need {3*f+1} agents for f={f} Byzantine agents")

    outputs = [agent.run(prompt) for agent in agents]  # Stage 1, parallel

    # Find the answer with ≥ f+1 agreement (Byzantine-resilient majority)
    from collections import Counter
    answer_counts = Counter(o.answer for o in outputs)

    for answer, count in answer_counts.most_common():
        if count >= f + 1:
            return Decision(answer=answer, byzantine_tolerant=True, votes=count)
    return Decision(answer=None, byzantine_tolerant=False, error="No Byzantine-resilient consensus")
```

## When to use it

- **High-stakes decisions**: anything that writes data, sends messages, makes financial calculations, or affects security policies
- **When agents share a base model** (almost always): independence is an illusion without protocol enforcement
- **When correctness is measurable**: structured debate is expensive (2–4× LLM calls per agent). Use it where the cost of wrong answers exceeds the compute cost.
- **Not for**: fast, low-stakes decisions where a single agent's answer is sufficient

## Tradeoffs

- **4–8× the LLM calls** of a single agent for a full debate cycle. Budget accordingly.
- **Calibration drift**: confidence scores drift over time as the model changes. Re-calibrate weekly against a reference set.
- **Agents can collude** in Stage 2 if the critique prompt is weak. Keep critiques focused on assumptions, not on persuading others toward an answer.
- **Byzantine tolerance requires 3f+1 agents**, which is often operationally impractical. Use it for adversarial multi-tenant settings, not internal tooling.

## See also

- [S-29 · False Consensus](s29-false-consensus.md) — the diagnosis of why naive voting fails; this is the protocol that fixes it
- [S-24 · Self-Consistency](s24-self-consistency.md) — majority voting over multiple reasoning paths from a single agent
- [S-1558 · Multi-Agent Reliability Divide](s1558-the-multi-agent-reliability-divide-stack-when-adding-agents-makes-your-system-less-reliable.md) — the reliability math that makes multi-agent systems harder to operate
- [S-153 · Cascade Stack](s153-the-cascade-stack-when-atomic-falsehood-propagates-through-your-multi-agent-pipeline.md) — how false facts propagate through multi-agent pipelines
- [Zylos Research — Consensus Protocols for Multi-Agent Decision Making](https://zylos.ai/en/research/2026-03-19-consensus-protocols-multi-agent-decision-making)

## Receipt

> Verified 2026-07-23 — Source: Zylos Research (zylos.ai/en/research/2026-03-19-consensus-protocols-multi-agent-decision-making, 2026-03-19); sudoall.com multi-agent coordination playbook (2026); Callsphere consensus algorithms blog (callsphere.ai, 2026-03-16). Structured debate stages adapted from Zylos cross-examination protocol. Byzantine variant based on PBFT-inspired agent consensus from Callsphere's BFT pattern. Python examples are working pseudocode based on documented APIs. Stage 1–4 flow confirmed against Zylos research. Byzantine section verified against Callsphere BFT implementation pattern.
