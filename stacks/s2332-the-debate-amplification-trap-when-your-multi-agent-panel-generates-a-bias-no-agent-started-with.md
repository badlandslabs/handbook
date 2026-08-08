# S-2332 · The Debate Amplification Trap — When Your Multi-Agent Panel Generates a Bias No Agent Started With

Your two-agent debate system for code review is working beautifully. Agent A proposes, Agent B critiques, they converge, and the final answer has survived adversarial scrutiny. You ship it with high confidence. Then a human reviewer notices the debate consistently underestimates cost for GPU-intensive operations — not because either agent has this bias, but because the debate protocol itself systematically suppresses the topic. Neither agent held the bias before they met each other. The debate created it.

This is the debate amplification trap: multi-agent debate doesn't just aggregate existing biases — it can generate new ones through interaction dynamics that neither agent exhibited independently. The panel sounds rigorous. The confidence is earned by the structure, not warranted by the outcome.

## Forces

- **Debate interaction amplifies biases that individual agents don't hold.** ICML 2026 (Okawa) found that multi-agent LLM debates produce collective biases — including discriminatory norms — that were not present in any single agent's prior responses. The interaction creates the bias; the debate is the mechanism.
- **Naive voting amplifies shared blind spots, not just individual ones.** Three agents on the same base model fail on the same inputs the same way. Majority vote concentrates those shared failures into confident consensus. S-1559 covers the design fix; this entry covers the structural mechanism that makes naive debate actively dangerous.
- **The "survivor confidence" problem.** Debate panels tend to produce one surviving answer — whichever position survived the last exchange. Survivors look confident because dissent was resolved, not because the answer is correct. The mechanism that makes debate feel rigorous (dissent resolution) is the same one that suppresses minority-truth signals.
- **Cost-accuracy tradeoff is non-obvious.** Kaesberg et al. (ACL Findings 2025) found that for 7-8B models, structured debate's accuracy gains don't justify the token cost compared to isolated self-correction. Teams deploy debate expecting "better than single agent" but measuring reveals the delta is small and the failure mode is different in kind, not just degree.

## The move

**Never trust a debate outcome without measuring what was suppressed.** Run the same decision through isolated single-agent deliberation before the debate. If the debate result diverges significantly from the isolated result, investigate which minority positions were suppressed and why.

### The suppression detection pattern

```python
# The debate amplification trap detector
# Run every debate decision through a dissent audit before committing

def dissent_audit(debate_result: DebateOutcome, original_proposals: list[Proposal]) -> DissentReport:
    """
    Detects whether the debate suppressed a minority truth.
    Compare: what did each agent propose BEFORE seeing others?
    vs what survived AFTER debate concluded.
    """
    suppressed = []
    for agent, original in original_proposals.items():
        # Extract the agent's pre-debate position on the key decision axis
        pre_position = extract_decision_axis(original.answer, debate_result.decision_dimension)
        post_position = extract_decision_axis(debate_result.final_answer, debate_result.decision_dimension)
        
        if pre_position != post_position and agent != debate_result.winner:
            # This agent's position was overridden — flag it
            suppression = SuppressionEvent(
                agent=agent,
                pre=pre_position,
                post=post_position,
                reason=debate_result.justification_for_winner,
                confidence_delta=original.confidence - debate_result.winner_confidence
            )
            suppressed.append(suppression)
    
    # Key signal: was the suppression on the basis of reasoning quality,
    # or was it a confidence/positioning effect?
    for s in suppressed:
        if s.confidence_delta < 0.05 and abs(s.pre - s.post) > 0.3:
            # Low-confidence agent had a significantly different position
            # AND their confidence wasn't much lower — possible suppression
            s.flag = "WEAK_SUPPRESSION_RISK"
    
    return DissentReport(
        suppressed_positions=suppressed,
        amplification_risk=len(suppressed) > 0,
        confidence_convergence=debate_result.winner_confidence - max(s.confidence for s in suppressed) if suppressed else 0
    )


def safe_debate_decision(proposals: list[Proposal], context: DecisionContext) -> Decision:
    # Step 1: Isolated deliberation — each agent decides WITHOUT seeing others
    isolated_results = {agent: isolated_deliberate(agent, context) for agent in agents}
    
    # Step 2: Debated decision
    debate_result = structured_debate(proposals, context)
    
    # Step 3: Dissent audit — did debate suppress minority truth?
    report = dissent_audit(debate_result, isolated_results)
    
    # Step 4: Suppression gate — if risk detected, escalate to human review
    if report.amplification_risk and report.confidence_convergence > 0.4:
        return Decision(
            outcome=debate_result.final_answer,
            confidence=debate_result.winner_confidence * 0.6,  # Penalize suppression
            escalation="SUPPRESSION_RISK: review suppressed positions",
            dissent_report=report
        )
    
    return Decision(outcome=debate_result.final_answer, confidence=debate_result.winner_confidence)
```

### The evidence before deployment rule

Before deploying any debate-based agent system:

1. **Inject adversarially-biased test cases** — known areas where debate is prone to amplification (cost underestimation, demographic proxies, confidence calibration). If the debate system amplifies the bias, the system is not production-ready regardless of general accuracy metrics.
2. **Measure the isolated vs. debated divergence rate.** On 500 test decisions, how often does the debated result differ significantly from the isolated majority? A >15% divergence rate is a red flag.
3. **Use model diversity as the primary bias mitigation.** Kaesberg et al. showed that answer diversity — achieved through independent drafting with limited communication — substantially boosts accuracy. The fix is not more debate rounds; it is more model diversity and earlier commitment to positions before seeing others.

## Receipt

> Verified 2026-08-08 — ICML 2026 (Okawa, "Emergence of Biased Consensus in Multi-Agent LLM Debates", Poster #3112) confirms debate interaction creates collective biases not present in individual agents. Kaesberg et al. (ACL Findings 2025, "Voting or Consensus? Decision-Making in Multi-Agent Debate") shows voting benefits reasoning tasks while consensus benefits knowledge tasks, with isolated self-correction offering better cost-accuracy tradeoff for 7-8B models. Tian Pan (April 10, 2026, tianpan.co) on temperature=0 non-determinism confirming 80 distinct completions from 1000 identical runs on Qwen3-235B — confirming that "converged" debate answers are themselves probabilistic. Deduplication: S-1559 (structured debate design) covers the protocol-level fix for naive voting; S-1351 (amplification trap) covers error amplification in multi-agent pipelines; neither covers the specific mechanism of debate creating emergent biases that no agent held independently.

## See also

- [S-1559 · The Structured Debate Stack](s1559-the-structured-debate-stack-when-your-multi-agent-panel-confidently-agrees-on-wrong-answers.md) — protocol design that makes debate earn its confidence
- [S-1351 · The Multi-Agent Amplification Trap](s1351-the-multi-agent-amplification-trap-when-adding-agents-makes-your-system-less-reliable.md) — error amplification in pipelines; related but distinct mechanism
- [S-1061 · The Generator-Evaluator Stack](s1061-the-generator-evaluator-stack-when-your-agent-runs-too-long-and-loses-the-plot.md) — evaluator bias as a distinct failure mode
