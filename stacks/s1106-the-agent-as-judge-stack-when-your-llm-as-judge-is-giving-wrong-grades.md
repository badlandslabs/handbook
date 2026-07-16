# S-1106 · The Agent-as-Judge Stack — When Your LLM-as-Judge Is Giving Wrong Grades

Your agent scores 4.2/5 on your evaluation harness. A week later it ships a regression that causes data loss in production. Your LLM-as-judge was scoring the wrong thing — a well-formatted wrong answer. You need evaluation that plans, inspects intermediate states, and scores the trajectory, not just the final output. You need an agent to judge an agent.

## Forces

- **LLM-as-Judge is a single-pass reader, not an investigator.** A single call that rates "looks good" cannot see the hallucinated tool call on step 3, the redundant API call on step 7, or the corrupted state passed from an upstream agent. It scores the output, not the process.
- **Bias compounds in static judging.** Length bias (longer answers score higher), position bias (first item sets the anchor), and self-preference bias (the judge model prefers outputs similar to its own style) all survive single-pass evaluation. A static judge will consistently reward verbosity over correctness.
- **Agentic evaluands require agentic evaluators.** An agent that browses the web, calls APIs, writes code, and reflects on its own reasoning cannot be rated with a multiple-choice rubric. The evaluation needs to mirror the agent's agency — planning its investigation, using tools, gathering evidence, and deliberating before scoring.
- **Trajectory scoring catches what output scoring misses.** A correct answer achieved through three unnecessary tool calls and a hallucinated intermediate state should not score the same as a clean, efficient run. Only trace-level evaluation distinguishes these.

## The move

**Agent-as-Judge** (Zhuge et al., ICML 2025) replaces the single-pass judge with an autonomous evaluator agent that can plan, act, inspect intermediate states, verify claims, and deliberate before scoring.

### The judge agent architecture

```python
# Agent-as-Judge evaluation loop
# Based on: zhuge25a "Agent-as-a-Judge" (ICML 2025, PMLR 267)
# GitHub: github.com/metauto-ai/agent-as-a-judge

from dataclasses import dataclass
from enum import Enum
from typing import Any

class Verdict(Enum):
    PASS = "pass"
    CONDITIONAL_PASS = "conditional_pass"
    FAIL = "fail"

@dataclass
class RequirementResult:
    requirement_id: str
    requirement_text: str
    verdict: Verdict
    evidence: list[str]       # traces, citations, tool outputs
    reasoning: str            # deliberation chain
    score: float              # 0.0-1.0

class AgentJudge:
    """
    An evaluator agent that plans, investigates, and judges
    another agent's trajectory — not just its output.
    """
    def __init__(self, model, benchmark: "DevAI | OpenWiki | custom"):
        self.model = model
        self.benchmark = benchmark
        self.requirements = benchmark.requirements  # hierarchical requirements

    def plan_evaluation(self, agent_trajectory: dict) -> list[str]:
        """Phase 1: The judge plans its investigation."""
        prompt = f"""
        You are an expert evaluator. Given the agent trajectory below,
        plan which requirements to check and in what order.
        Prioritize: safety > correctness > efficiency > style.
        
        Trajectory length: {len(agent_trajectory.get('steps', []))} steps
        Tools used: {agent_trajectory.get('tools_used', [])}
        
        Plan your investigation steps.
        """
        plan = self.model.generate(prompt)
        return plan.decomposition

    def gather_evidence(
        self,
        requirement: str,
        trajectory: dict
    ) -> list[str]:
        """Phase 2: Inspect the trajectory for evidence."""
        relevant_steps = [
            step for step in trajectory["steps"]
            if requirement.lower() in str(step.get("output", "")).lower()
            or requirement.lower() in str(step.get("tool_call", "")).lower()
        ]
        return [step["output"] for step in relevant_steps]

    def verify_claim(
        self,
        claim: str,
        evidence: list[str]
    ) -> bool:
        """Phase 3: Fact-check claims against evidence or live retrieval."""
        verify_prompt = f"""
        Claim: {claim}
        Evidence: {evidence}
        Is the claim supported, contradicted, or unverified?
        """
        return self.model.generate(verify_prompt).supported

    def deliberate_and_score(
        self,
        requirement: str,
        evidence: list[str],
        trajectory: dict
    ) -> RequirementResult:
        """Phase 4: Deliberate and issue a verdict with reasoning."""
        deliberation = self.model.generate(f"""
        Requirement: {requirement}
        Evidence: {evidence}
        Trajectory context: {trajectory.get('metadata', {})}
        
        Deliberate: What did the agent do right? What did it miss?
        What could have gone wrong silently?
        Score from 0.0 (completely fails) to 1.0 (fully satisfies).
        """)
        return RequirementResult(
            requirement_id=requirement["id"],
            requirement_text=requirement["text"],
            verdict=self._verdict(deliberation.score),
            evidence=evidence,
            reasoning=deliberation.chain_of_thought,
            score=deliberation.score,
        )

    def judge(self, agent_trajectory: dict) -> dict[str, RequirementResult]:
        plan = self.plan_evaluation(agent_trajectory)
        results = {}
        for req in self.requirements:
            evidence = self.gather_evidence(req["text"], agent_trajectory)
            # Filter out hallucinated claims before scoring
            verified_evidence = [
                e for e in evidence
                if self.verify_claim(e, agent_trajectory["source_docs"])
            ]
            results[req["id"]] = self.deliberate_and_score(
                req, verified_evidence, agent_trajectory
            )
        return results

# DevAI benchmark: 55 realistic AI development tasks, 365 hierarchical requirements
# Available at: huggingface.co/DEVAI-benchmark
```

### Evaluation design principles

- **Hierarchical requirements over flat rubrics.** Agent outputs are multi-dimensional. Flat scores collapse this into a single number that hides failure modes. Hierarchical scoring — safety, correctness, efficiency, style — lets you fail fast on what matters and pass conditionally on what doesn't.
- **Bias-aware shuffling.** Randomize the order of outputs being compared. Run the judge with blinded outputs (no model names). Control for self-preference bias by never letting the judge model evaluate its own outputs.
- **Pass-at-K with trajectory variance.** A single run is not a reliable signal. Run each task K times and track the trajectory variance — not just whether it passed, but how differently it passed. High variance means the agent is unreliable, even if K/N looks good.
- **Trajectory audit trail as first-class artifact.** The judge's reasoning chain is an RCA document. When an agent fails in production, the judge trace is often the fastest path to the root cause.

### The DevAI benchmark reference

DevAI (Zhuge et al., ICML 2025) provides 55 realistic AI development tasks with 365 hierarchical user requirements — each requirement is independently verifiable against the agent's trajectory. This is the reference benchmark for Agent-as-Judge evaluation.

## Receipt

> Verified 2026-07-14 — Agent-as-Judge (ICML 2025, PMLR 267:80569-80611), DevAI benchmark (HuggingFace), emergentmind.com synthesis. Deduplication: F-07 (Evaluation-Driven Development) covers LLM-as-judge and eval harness principles but not the multi-agent evaluator paradigm. I-042 (continuous eval) and I-048 cover eval infrastructure but not Agent-as-Judge specifically. No existing entry covers the judge-as-agent architecture with DevAI as the reference benchmark.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — trajectory scoring vs output scoring
- [F-07 · Evaluation-Driven Development](forward-deployed/f07-evaluation-driven-development.md) — LLM-as-judge, pre-commit evals, CI gates
- [S-1103 · The Agent Eval Stack — When Pass/Fail Tests Are a Lie](s1103-the-agent-eval-stack-when-passfail-tests-are-a-lie.md) — scoring axes, trajectory metrics
