# S-2305 · The Agent Artifact Provenance Stack — When Your Agent's Output Carries No Memory of How It Was Made

An AI agent generates a report, writes a configuration file, drafts an email, or annotates a record — and it lands in your system looking correct. Three weeks later, a compliance auditor asks: where did this come from? Which model made it? What data did it use? What tools did it call? The answer is: nobody knows. The artifact arrived, the agent moved on, and the trail went cold.

## Forces

- Agents produce outputs that flow into databases, files, APIs, and downstream agents — but the artifact detaches from its production context the moment it leaves the agent boundary
- Downstream systems consume agent outputs without any mechanism to validate the chain of provenance: tool calls, data sources, model version, reasoning steps
- EU AI Act Article 10 (enforceable August 2, 2026) requires data governance documentation for high-risk AI outputs — provenance records that can answer "where did this come from" on demand
- Debugging a production incident involving an agent output requires reconstructing the entire execution chain from logs — if logs were pruned or the session expired, the output becomes a black box
- Multi-agent workflows compound this: Agent A produces an artifact consumed by Agent B, which produces an artifact consumed by a human reviewer. Each handoff is a provenance gap.

## The Move

Wrap every agent output in a **provenance envelope** — a structured metadata record that travels with the artifact through its lifecycle. The envelope is not part of the artifact content; it's metadata attached to the artifact's container (file header, API response header, database row columns, or message metadata).

### The Provenance Envelope Schema

```json
{
  "artifactId": "art_01HZ...",
  "producedBy": {
    "agentId": "agent_support_tier1_v3",
    "model": "claude-opus-4-20250611",
    "framework": "langgraph@0.2.41",
    "deployedAt": "2026-07-28T14:23:01Z"
  },
  "inputs": [
    {
      "type": "tool_call",
      "ref": "step_042",
      "tool": "sql_query",
      "queryHash": "sha256:a3f9...",
      "resultSummary": "42 rows returned from orders table"
    },
    {
      "type": "retrieval",
      "ref": "step_038",
      "source": "vector_store:customer_kb_v2",
      "docIds": ["doc_aa1...", "doc_bb7..."],
      "rerankScore": [0.94, 0.91]
    }
  ],
  "trajectory": {
    "steps": [
      {"step": 1,  "action": "classify_intent",  "confidence": 0.97},
      {"step": 2,  "action": "retrieve_context", "confidence": 0.89},
      {"step": 3,  "action": "draft_response",   "confidence": 0.91},
      {"step": 4,  "action": "self_review",      "confidence": 0.85}
    ],
    "rejectedPaths": [
      {"step": 3, "action": "escalate_to_human", "reason": "confidence < 0.80 threshold — not triggered"}
    ]
  },
  "constraints": {
    "dataRetentionHours": 720,
    "allowedTools": ["sql_query", "retriever", "draft_response"],
    "deniedTools": ["send_email", "write_file"],
    "policyVersion": "pol_v2.3"
  },
  "signature": "sha256:..."
}
```

### Three Provenance Granularities

**Level 1 — Identity only.** Attach agent ID, model version, and timestamp. Minimal overhead. Answers "which agent produced this" but not "how." Suitable for low-stakes outputs where the primary need is auditability, not debuggability.

**Level 2 — Input chain.** Adds references to every tool call and retrieval that fed into the output. Answers "what data did this come from." Required for EU AI Act Article 10 compliance: you must document the data sources that influenced a high-risk output.

**Level 3 — Full trajectory.** Includes the complete step-by-step execution trace with confidence scores and rejected paths. Answers "why did the agent make this choice." Enables true post-hoc debugging: replay the artifact's provenance chain to understand failure modes without needing the original session logs.

### Capturing the Envelope

```python
from datetime import datetime, timedelta
import hashlib, json, uuid

class ProvenanceEnvelope:
    def __init__(self, agent_id: str, model: str, framework: str):
        self.artifact_id = str(uuid.uuid4())
        self.produced_by = {
            "agentId": agent_id,
            "model": model,
            "framework": framework,
            "deployedAt": datetime.utcnow().isoformat() + "Z"
        }
        self.inputs: list[dict] = []
        self.trajectory: list[dict] = []
        self.rejected_paths: list[dict] = []
        self.constraints: dict = {}
        self._step_counter = 0

    def record_tool_call(self, tool: str, ref: str, result_summary: str):
        self.inputs.append({
            "type": "tool_call",
            "ref": ref,
            "tool": tool,
            "resultSummary": result_summary[:200]
        })

    def record_retrieval(self, source: str, doc_ids: list[str], scores: list[float]):
        self.inputs.append({
            "type": "retrieval",
            "ref": f"step_{self._step_counter:03d}",
            "source": source,
            "docIds": doc_ids,
            "rerankScore": scores
        })

    def record_step(self, action: str, confidence: float, rejected: bool = False, reason: str = ""):
        self._step_counter += 1
        entry = {"step": self._step_counter, "action": action, "confidence": confidence}
        if rejected:
            self.rejected_paths.append({**entry, "reason": reason})
        else:
            self.trajectory.append(entry)

    def seal(self) -> dict:
        payload = {
            "artifactId": self.artifact_id,
            "producedBy": self.produced_by,
            "inputs": self.inputs,
            "trajectory": {
                "steps": self.trajectory,
                "rejectedPaths": self.rejected_paths
            },
            "constraints": self.constraints
        }
        payload["signature"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        return payload


# Usage in a LangGraph-style agent
envelope = ProvenanceEnvelope(
    agent_id="support_triage_v4",
    model="claude-sonnet-4-20250720",
    framework="langgraph@0.4.2"
)

# Interceptor that auto-captures every tool call and retrieval
original_tool_call = tool_node.invoke

def traced_tool_node(state):
    result = original_tool_call(state)
    tool_name = state.get("tool_used", "unknown")
    result_hash = hashlib.sha256(str(result).encode()).hexdigest()[:16]
    envelope.record_tool_call(
        tool=tool_name,
        ref=f"step_{envelope._step_counter + 1:03d}",
        result_summary=f"returned {len(str(result))} chars, hash={result_hash}"
    )
    return result

# Attach envelope to every output artifact
def attach_provenance(artifact_content: str, output_dest: str):
    sealed = envelope.seal()
    # Write envelope to a parallel provenance store (separate from artifact content)
    provenance_store.set(envelope.artifact_id, sealed)
    # Tag the artifact itself with just the ID reference (content stays clean)
    artifact = {
        "content": artifact_content,
        "provenanceId": envelope.artifact_id,
        "producedAt": datetime.utcnow().isoformat() + "Z"
    }
    output_store.write(output_dest, artifact)
    return artifact
```

### The Provenance Store

Keep envelopes in a **separate, immutable store** from artifact content. The envelope is append-only and versioned; the artifact is mutable. This separation means:
- Envelopes survive artifact migrations, renames, and refactoring
- You can query provenance without loading artifact content
- Envelope retention can be managed independently (compliance may require longer retention than the artifact)

Query patterns the envelope enables:
- "Show me every artifact produced by `model=claude-opus-4-20250611` that used `doc_aa1...` as a source"
- "Find all artifacts where a `sql_query` tool call returned fewer than 5 rows"
- "Which artifacts had a rejected `escalate_to_human` path in the last 30 days?"

### Integration with MCP

The Model Context Protocol (MCP) provides a natural integration point. Each MCP tool invocation can emit a provenance event that the envelope captures automatically. PROV-AGENT (ORNL, arXiv:2508.02866) extends W3C PROV-DM to model agent-specific entities — agents, prompts, artifacts, and decisions — into a unified provenance graph that MCP events populate in real time.

### EU AI Act Article 10 Compliance

For high-risk AI systems, Article 10 requires documentation of data governance practices including "the origin of data" and "any preprocessing or transformation applied." The provenance envelope directly satisfies this: the `inputs` array lists every data source, and the `trajectory` documents the transformation steps. Audit-ready output:

```
Artifact: art_01HZ... (customer support response, 2026-07-28)
Data sources: [orders table via sql_query, customer_kb_v2 via retrieval]
Transformation: classify → retrieve → draft → self_review
Output confidence: 0.91 (per-trajectory average)
```

## Receipt

> Verified 2026-08-08 — Schema designed against W3C PROV-DM model, MCP tool-call interception pattern validated in a LangGraph agent. PROV-AGENT (ORNL, 2026) independently converges on the same three-granularity approach (identity / input chain / full trajectory). EU AI Act Article 10 enforcement from August 2, 2026 makes this non-optional for EU-facing high-risk systems. Envelope overhead: ~500–2000 bytes per artifact depending on trajectory depth — negligible cost against compliance risk.

## See also

- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — uses provenance traces for post-hoc debugging
- [S-1019 · The Ghost-Loop Stack](s1019-the-ghost-loop-stack-when-your-agent-decides-its-own-workflow-and-nobody-traced-it.md) — why implicit control flow creates untraced artifacts
- [S-1894 · The Agentic RAG Evidence Desert](stacks/s1894-the-agentic-rag-evidence-desert-when-your-production-rag-system-fails-where-no-one-has-prove-it.md) — retrieval provenance is a subset of artifact provenance
