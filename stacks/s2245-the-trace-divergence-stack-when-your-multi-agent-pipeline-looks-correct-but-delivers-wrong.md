# S-2245 · The Trace Divergence Stack — When Your Multi-Agent Pipeline Looks Correct but Delivers Wrong

Your orchestrator agent classifies incoming tickets. Your specialist agent drafts responses. Your reviewer agent approves them. Together they handle 500 tickets a day. Then one ticket from an adversarial document source — a corrupted PDF with subtle instruction leakage — gets processed. Every agent clears it: the classifier sees nothing suspicious, the drafter produces a normal response, the reviewer approves. All three passed local checks. The output is wrong, the response is misaligned with the actual ticket, and nobody can explain why — because individually, every agent was behaving as expected.

This is **trace divergence**: when a multi-agent workflow's execution path — the actual sequence of tool calls, internal states, and intermediate decisions — deviates from what the workflow was designed to do, even when individual agent outputs look locally plausible. The contamination lives in the *trace*, not in any single output.

Mazhar et al. (Cornell/UIUC, ACM CAIS 2026) introduced controlled trace-level experimentation on this problem and found a counterintuitive result: **structural divergence and outcome corruption are decoupled**. 40.3% of substantially divergent runs still recover correct answers. 15.3% of structurally similar runs produce wrong outputs. Local output checks miss both failure modes.

## Forces

- **The propagation problem is invisible to point checks.** Every downstream agent sees only the output of its predecessor. If that output is *locally reasonable* but carries a corrupted execution path, all downstream validators see consistent-looking garbage.
- **"Locally plausible" is not "globally sound".** An extraction agent can produce a correct-looking table that was generated from corrupted source data. A drafting agent can produce well-written text that propagates the wrong premise. A reviewer agent can validate style and tone while missing semantic contamination.
- **Sanitization is not propagation-awareness.** You can sanitize every agent-to-agent output and still miss the problem, because the contamination isn't in the content — it's in the *reasoning path* that produced the content. A sanitized but incorrect extraction still carries the wrong causal chain downstream.
- **Standard eval checks final outputs, not traces.** Pass/fail on the final deliverable misses trace-level contamination that produced it. The failure happened 3 steps earlier, and the evidence was overwritten by subsequent steps.

## The move

**Trace divergence detection** — instrumenting multi-agent workflows to detect when execution paths deviate from the intended causal chain, not just when final outputs look wrong.

### Pattern 1: Execution Path Fingerprinting

Record the actual sequence of tool calls, retrieval actions, and reasoning steps per agent as a **trace fingerprint** — a compact representation (tool-signature sequence + key decision nodes) that can be compared against the intended workflow path.

```python
import hashlib
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TraceFingerprint:
    """Compact execution path fingerprint for multi-agent trace comparison."""
    workflow_id: str
    agent_id: str
    session_id: str
    tool_sequence: list[str] = field(default_factory=list)
    decision_nodes: list[dict] = field(default_factory=list)  # {type, content_hash, timestamp}

    def add_tool(self, tool_name: str, input_hash: str, output_hash: Optional[str] = None):
        self.tool_sequence.append(tool_name)
        self.decision_nodes.append({
            "type": "tool",
            "tool": tool_name,
            "input_hash": input_hash,
            "output_hash": output_hash or "",
            "node_hash": hashlib.sha256(
                f"{tool_name}:{input_hash}:{output_hash}".encode()
            ).hexdigest()[:12]
        })

    def add_decision(self, decision_type: str, content: str, confidence: float):
        self.decision_nodes.append({
            "type": "decision",
            "decision_type": decision_type,
            "content_hash": hashlib.sha256(content.encode()).hexdigest()[:12],
            "confidence": confidence,
            "node_hash": hashlib.sha256(
                f"{decision_type}:{content[:200]}:{confidence}".encode()
            ).hexdigest()[:12]
        })

    def path_signature(self) -> str:
        """Deterministic path signature — same workflow produces same signature."""
        tool_part = "|".join(self.tool_sequence)
        node_part = "|".join(n["node_hash"] for n in self.decision_nodes)
        return hashlib.sha256(f"{tool_part}::{node_part}".encode()).hexdigest()[:24]


@dataclass
class TraceComparator:
    """Compares actual traces against intended workflow paths."""
    intended_path: list[str]  # e.g., ["classify", "extract", "draft", "review"]

    def compute_divergence_score(self, actual: TraceFingerprint, threshold: float = 0.3) -> dict:
        """
        Returns divergence analysis between intended and actual execution path.
        Returns: {diverged: bool, score: float, missing_steps: [...], extra_steps: [...],
                  recovery_detected: bool, corruption_risk: str}
        """
        actual_tools = actual.tool_sequence
        intended = self.intended_path

        # Step 1: Prefix matching — find where traces diverged
        divergence_point = 0
        for i, intended_tool in enumerate(intended):
            if i < len(actual_tools) and actual_tools[i] == intended_tool:
                divergence_point = i + 1
            else:
                break

        # Step 2: Identify missing and extra steps
        missing = intended[divergence_point:]
        extra = actual_tools[len(intended):] if len(actual_tools) > len(intended) else []

        # Step 3: Divergence score (0 = identical, 1 = completely different path)
        if not actual_tools:
            score = 1.0
        else:
            matched = sum(1 for i, t in enumerate(actual_tools) if i < len(intended) and t == intended[i])
            score = 1.0 - (matched / max(len(intended), len(actual_tools)))

        # Step 4: Outcome corruption risk assessment
        # High risk: divergence includes data retrieval or extraction steps
        critical_steps = {"retrieve", "extract", "parse", "classify", "search"}
        divergence_includes_critical = any(t in missing for t in critical_steps)
        extra_critical = any(t in extra for t in critical_steps)
        risk = "HIGH" if (divergence_includes_critical or extra_critical) else "MEDIUM" if score > threshold else "LOW"

        # Step 5: Recovery detection heuristic
        # If final steps re-align with intended path, may have recovered
        recovery_detected = (
            len(actual_tools) >= len(intended) and
            actual_tools[-len(intended):] == intended
        )

        return {
            "diverged": score > threshold,
            "score": round(score, 3),
            "divergence_point": divergence_point,
            "missing_steps": missing,
            "extra_steps": extra,
            "recovery_detected": recovery_detected,
            "corruption_risk": risk,
            "path_signature": actual.path_signature(),
        }
```

### Pattern 2: Causal Provenance Chain

Tag every piece of information in agent output with its **causal origin** — not just its source URL or timestamp, but the specific upstream decision that produced it. When Agent B uses Agent A's output, B should be able to trace which of A's decisions contributed to each claim.

```python
@dataclass
class ProvenanceAtom:
    """Atomic provenance record for a single piece of information."""
    claim_id: str
    agent_id: str
    source_type: str  # "retrieved" | "inferred" | "user_input" | "upstream_agent"
    source_ref: str  # URL, upstream_agent_id, or "user"
    upstream_claim_ids: list[str] = field(default_factory=list)  # causal parents
    extraction_method: str = ""  # "ocr" | "llm_extract" | "structured_parse" | "llm_inference"
    confidence: float = 1.0
    raw_hash: str = ""  # hash of original content before processing

    def to_tag(self) -> str:
        """Serialize as a provenance tag for injection into downstream context."""
        return (
            f"[PROVENANCE: claim={self.claim_id[:8]} | "
            f"agent={self.agent_id} | "
            f"src={self.source_type}:{self.source_ref[:40]} | "
            f"upstream={','.join(c[:8] for c in self.upstream_claim_ids)} | "
            f"method={self.extraction_method} | "
            f"conf={self.confidence:.2f}]"
        )


class ProvenanceTracker:
    """Tracks causal provenance across multi-agent pipeline."""
    def __init__(self, pipeline_id: str):
        self.pipeline_id = pipeline_id
        self.claims: dict[str, ProvenanceAtom] = {}
        self.agent_outputs: dict[str, list[str]] = {}  # agent_id -> list of claim_ids

    def record_extraction(self, agent_id: str, raw_content: str,
                          source_type: str, source_ref: str) -> str:
        claim_id = hashlib.sha256(f"{raw_content[:500]}{agent_id}".encode()).hexdigest()[:16]
        atom = ProvenanceAtom(
            claim_id=claim_id,
            agent_id=agent_id,
            source_type=source_type,
            source_ref=source_ref,
            extraction_method="llm_extract" if source_type == "retrieved" else "llm_inference",
            raw_hash=hashlib.sha256(raw_content[:1000].encode()).hexdigest()[:16],
        )
        self.claims[claim_id] = atom
        self.agent_outputs.setdefault(agent_id, []).append(claim_id)
        return claim_id

    def record_inference(self, agent_id: str, inferred_claims: list[str],
                        upstream_claim_ids: list[str], confidence: float) -> list[str]:
        """Record that an agent inferred new claims from upstream claims."""
        new_claim_ids = []
        for claim_text in inferred_claims:
            claim_id = hashlib.sha256(
                f"{claim_text[:200]}{agent_id}{','.join(upstream_claim_ids)}".encode()
            ).hexdigest()[:16]
            atom = ProvenanceAtom(
                claim_id=claim_id,
                agent_id=agent_id,
                source_type="inferred",
                source_ref="inference",
                upstream_claim_ids=upstream_claim_ids,
                confidence=confidence,
            )
            self.claims[claim_id] = atom
            new_claim_ids.append(claim_id)
        return new_claim_ids

    def trace_back(self, claim_id: str, max_depth: int = 5) -> list[ProvenanceAtom]:
        """Trace causal ancestry of a claim back to root sources."""
        ancestry = []
        queue = [(claim_id, 0)]
        seen = set()

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in seen or depth > max_depth:
                continue
            seen.add(current_id)

            if current_id in self.claims:
                atom = self.claims[current_id]
                ancestry.append(atom)
                for parent_id in atom.upstream_claim_ids:
                    queue.append((parent_id, depth + 1))

        return ancestry

    def detect_contaminated_path(self, claim_id: str,
                                  suspicious_sources: set[str]) -> dict:
        """
        Check if a claim's causal ancestry traces back to suspicious sources.
        Returns contamination analysis for downstream validation.
        """
        ancestry = self.trace_back(claim_id)
        tainted_claims = [
            atom for atom in ancestry
            if atom.source_type == "retrieved" and any(
                atom.source_ref.startswith(s) for s in suspicious_sources
            )
        ]
        return {
            "tainted": len(tainted_claims) > 0,
            "tainted_count": len(tainted_claims),
            "total_ancestors": len(ancestry),
            "taint_ratio": len(tainted_claims) / max(len(ancestry), 1),
            "root_cause": tainted_claims[0] if tainted_claims else None,
            "requires_review": len(tainted_claims) > 0 and any(
                atom.confidence < 0.8 for atom in tainted_claims
            ),
        }
```

### Pattern 3: Propagation-Aware Verification Gate

Rather than validating each agent's output in isolation, validate the **causal chain** from source to final output. Inject trace metadata into the verification prompt so the judge knows the causal ancestry.

```python
def build_propagation_aware_verification_prompt(
    final_output: str,
    provenance_chain: list[ProvenanceAtom],
    trace_divergence_report: dict,
    original_user_intent: str,
) -> str:
    """
    Build a verification prompt that gives the judge full causal context,
    not just the final output.
    """
    # Build provenance summary
    source_types = [atom.source_type for atom in provenance_chain]
    extraction_steps = [
        atom for atom in provenance_chain
        if atom.extraction_method in ("llm_extract", "ocr", "structured_parse")
    ]
    low_confidence = [atom for atom in provenance_chain if atom.confidence < 0.85]

    prompt = f"""You are verifying the output of a multi-agent pipeline.

## Original User Intent
{original_user_intent}

## Final Output Under Review
{final_output}

## Causal Ancestry (how the output was constructed)
- Total processing steps: {len(provenance_chain)}
- Source material steps: {len(extraction_steps)}
- Low-confidence steps: {len(low_confidence)}

### Processing Chain
"""
    for i, atom in enumerate(provenance_chain):
        indent = "  " * (atom.source_type.count("inferred"))
        prompt += f"{indent}{i+1}. [{atom.agent_id}] {atom.source_type}: {atom.source_ref[:60]}"
        if atom.source_type == "inferred":
            prompt += f" (from {', '.join(c[:8] for c in atom.upstream_claim_ids)})"
        prompt += f" — conf={atom.confidence:.0%}"
        if atom.extraction_method:
            prompt += f" [via {atom.extraction_method}]"
        prompt += "\n"

    prompt += f"""
## Trace Divergence Report
- Execution path divergence score: {trace_divergence_report['score']}
- Diverged: {trace_divergence_report['diverged']}
- Corruption risk: {trace_divergence_report['corruption_risk']}
- Recovery detected: {trace_divergence_report['recovery_detected']}
"""
    if trace_divergence_report.get('missing_steps'):
        prompt += f"- Missing intended steps: {', '.join(trace_divergence_report['missing_steps'])}\n"
    if trace_divergence_report.get('extra_steps'):
        prompt += f"- Extra steps detected: {', '.join(trace_divergence_report['extra_steps'])}\n"

    prompt += """
## Verification Task
Evaluate this output for:
1. **Semantic correctness**: Does the output faithfully address the original intent?
2. **Contamination risk**: Are there signs the causal chain carried corrupted information?
3. **Trace integrity**: Does the output's reasoning match what the causal chain should produce?
4. **Confidence calibration**: Does the output confidence match the lowest-confidence step?

Flag any step in the causal chain that could explain output errors.
"""
    return prompt
```

## Receipt

> Verified 2026-08-06 — arXiv:2604.27586v1 (Mazhar et al., Cornell/UIUC, ACM CAIS 2026) demonstrates trace divergence empirically: 40.3% divergent runs recover correct answers; 15.3% similar runs produce wrong outputs. arXiv:2512.23557 (Ali et al., Dec 2025) validates cross-agent contamination via provenance-aware defense. Cognilium AI (Jul 2026) documents lateral contamination in multi-agent pipelines. Code patterns are structural illustrations based on described mechanisms. Receipt pending — execute against real multi-agent pipeline to confirm detection accuracy.

## See also

- [S-1659 · The Instruction Privilege Stack](stacks/s1659-the-instruction-privilege-stack-when-your-agent-treats-a-prompt-injection-as-authoritative.md) — privilege hierarchy between instruction sources; this is the cross-agent propagation failure that privilege separation alone doesn't catch
- [S-1658 · The GenAI Observability Trace Stack](stacks/s1658-the-genai-observability-stack-when-your-agent-does-something-and-nobody-knows-why.md) — generic trace instrumentation; this entry adds causal-path comparison, not just span logging
- [S-1136 · The Context Sanitization Gate Stack](stacks/s1136-the-context-sanitization-gate-stack-provenance-tagging-freshness-gates-and-claim-expiration-for-retrieval-noise.md) — per-step content sanitization; trace divergence detection operates on execution paths, not content — they compose
- [S-1063 · The Multi-Agent Orchestration Stack](stacks/s1063-the-multi-agent-orchestration-stack-when-one-agent-isnt-enough-but-five-becomes-a-debugging-nightmare.md) — orchestration patterns; trace divergence is an emergent failure mode in orchestrated pipelines
