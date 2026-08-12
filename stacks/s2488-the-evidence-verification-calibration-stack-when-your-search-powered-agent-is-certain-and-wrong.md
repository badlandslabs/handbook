# S-2488 · The Evidence–Verification Calibration Stack — When Your Search-Powered Agent Is Certain and Wrong

Your agent just ran a web search, read five results, and returned a confident answer. It's wrong. The top search result contained a statistic from a retracted paper. The model read it, incorporated it, and expressed high confidence — because it had *evidence*. But evidence ≠ accuracy. The ACL 2026 finding is unambiguous: evidence tools (web search, RAG) systematically induce severe overconfidence in agents, while verification tools (code interpreters, test runners) ground reasoning and produce well-calibrated confidence. The same agent, same model, radically different calibration — entirely determined by tool type. The fix is not a better prompt. It's a calibration-aware tool routing architecture.

## Forces

- **RLHF rewards fluency, not epistemic accuracy.** RLHF shapes confidence expressions toward outputs that *sound* authoritative. A confident answer backed by a plausible-sounding citation gets higher ratings than a hedged answer — even when the citation is fabricated.
- **Evidence tools amplify noise as signal.** Web search returns ranked-but-unverified information. RAG retrieves chunks with no provenance guarantee. The model treats retrieved text as "given" and builds confidence on top of it — compounding error with certainty.
- **Verification tools provide deterministic grounding.** A code interpreter returns a result that either compiles or doesn't. A test runner tells you whether your code passes. This binary feedback is what the model lacks — and it is the only calibration signal that actually reflects ground truth.
- **Agents cannot self-diagnose miscalibration.** A model that is overconfident on evidence-tool outputs cannot use its own internal uncertainty estimate to detect this. The miscalibration is structural, not a reasoning error.
- **Evidence tools are the default.** Most production agent pipelines lean heavily on search and RAG for knowledge-intensive tasks. The tool types that produce the worst calibration are the most commonly deployed.

## The move

**1. Classify every tool by calibration type.**
Map your tool inventory into two buckets: **evidence tools** (search, RAG, web fetch, document retrieval) and **verification tools** (code interpreter, calculator, test runner, SQL executor, deterministic API with schema validation). Most agent toolkits are 80%+ evidence tools. This is the root of the problem.

**2. Inject verification-tool alternatives wherever evidence tools dominate.**
For every knowledge-intensive task, add at least one verification path:
- Instead of relying on a RAG answer, also run a targeted code query against the authoritative source
- Instead of accepting a web search result as fact, verify it against a structured data endpoint or execution trace
- Route statistical claims through a calculator or code interpreter rather than text extraction

**3. Treat confidence scores as tool-type-conditional.**
Do not compare confidence scores across different tool types. A 0.9 confidence from a search-backed reasoning chain is not comparable to a 0.9 from a code-execution-backed chain. Route downstream decisions (escalation, tool selection, abstention) through tool-type-specific thresholds.

**4. Use verification tools as calibration anchors.**
When an evidence tool and a verification tool can both answer the same question, the verification answer is the ground truth for calibrating the evidence answer. Log both. Track whether evidence-tool outputs agree with verification-tool outputs. When they diverge, that is a calibration failure signal.

**5. Add tool-type as a feature in confidence post-processing.**
After the model produces a confidence score, apply a tool-type correction multiplier. Evidence tools get a decay factor (e.g., multiply by 0.7) unless a verification tool has independently confirmed the output. This is a simple, deployable version of the RL fine-tuning approach described in the ACL 2026 paper — it requires no model changes.

**6. Route abstention to verification, not human review.**
When confidence is below threshold on an evidence-tool task, the instinct is to escalate to a human. The better move is to route to a verification-tool path first — run the computation, execute the test, query the authoritative API. Most evidence-tool low-confidence cases can be resolved by switching tool type, not by human intervention.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ToolType:
    calibration_class: Literal["evidence", "verification"]
    trust_multiplier: float  # applied to model confidence

TOOL_CALIBRATION = {
    "web_search":   ToolType("evidence",      0.7),
    "rag_retrieve": ToolType("evidence",      0.7),
    "web_fetch":   ToolType("evidence",      0.7),
    "sql_query":   ToolType("verification",  1.0),
    "code_exec":   ToolType("verification",  1.0),
    "calc":        ToolType("verification",  1.0),
    "test_run":    ToolType("verification",  1.0),
}

def calibrated_confidence(tool_name: str, raw_confidence: float) -> float:
    """Apply tool-type-specific calibration to model confidence."""
    tool_type = TOOL_CALIBRATION.get(tool_name, ToolType("evidence", 0.7))
    calibrated = raw_confidence * tool_type.trust_multiplier
    return max(calibrated, 0.0)

def route_task(task: dict, raw_confidence: float) -> str:
    """Route based on calibrated confidence, preferring verification tools."""
    calibrated = calibrated_confidence(task["tool_used"], raw_confidence)
    if calibrated >= 0.8:
        return "accept"
    elif task["tool_used"] == "evidence_tool":
        # Evidence tool below threshold: try verification path before human
        return "verify_first"
    else:
        return "escalate"
```

## Receipt

> Verified 2026-08-11 — Primary source: "The Confidence Dichotomy: Analyzing and Mitigating Miscalibration in Tool-Use Agents" (Xuan et al., ACL 2026, arXiv:2026.acl-long.520). Key findings: (1) evidence tools induce severe overconfidence due to retrieved noise; (2) verification tools ground reasoning via deterministic feedback; (3) RL fine-tuning jointly optimizing accuracy and calibration outperforms accuracy-only training. Tool-type classification and confidence decay multiplier are original architectural patterns derived from the core finding. Confidence thresholds (0.8/0.7) are illustrative; calibrate against your task distribution.

## See also

- [S-1793 · The Calibration Gate Stack](s1793-the-calibration-gate-stack-when-your-agent-knows-nothing-but-acts-like-it-knows-everything.md) — general calibration gates; this entry is the tool-type-specific complement
- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — how unverified inter-agent outputs propagate; evidence-tool overconfidence is the input to this cascade
- [S-100 · Live Data Freshness Contracts](s100-live-data-freshness-contracts.md) — data staleness in evidence tools; verification tools provide freshness-independent ground truth
