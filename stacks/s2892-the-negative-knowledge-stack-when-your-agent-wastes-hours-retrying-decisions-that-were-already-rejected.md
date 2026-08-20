# S-2892 · The Negative Knowledge Stack — When Your Agent Wastes Hours Re-trying Decisions That Were Already Rejected

Agent A spent 20 minutes narrowing a research query. It considered and rejected three approaches before landing on the right framing. Agent B receives a clean, concise task description — and immediately tries approach #2. The one Agent A already ruled out. No tool call failed. No model hallucinated. The downstream agent simply never knew what was already excluded. This is the negative knowledge problem: every handoff discards the *what was rejected* and the *why*, and the downstream agent pays for that loss in failed attempts, wasted tokens, and compounding delay.

## Forces

- **Every handoff is a lossy compression event.** The upstream agent's full reasoning — constraints considered, alternatives evaluated, dead ends mapped — gets summarized into a task description. What survives is the conclusion. What dies is the trail.
- **Agents don't ask "what was ruled out here?"** LLMs are optimists. Given a task, they pursue the most plausible path — which includes paths the previous agent already tried and abandoned. There is no self-correction mechanism for inherited context gaps.
- **Rejected alternatives encode the most expensive knowledge.** The upstream agent burned tokens and tool calls figuring out that approach X doesn't work for constraint Y. Without that, the downstream agent repeats the same exploration from zero.
- **The failure manifests downstream, not at the handoff.** Agent A's reasoning is invisible to the system. Agent B's failures look like new bugs. The real cause — missing negative knowledge — is never surfaced.
- **Adding context is easier than adding negative knowledge structure.** Teams know to pass outputs forward. Nobody has a convention for passing *exclusions* forward.

## The Move

Structure every handoff as a **negative knowledge document** — a lightweight annotation layer on top of the task payload that explicitly records what was rejected and why. This is not a verbose reasoning dump. It is a one-paragraph addition to every agent output that answers: *what did you decide not to do, and what would have made those choices viable if the constraints change?*

### The four fields

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HandoffNote:
    """Standard negative-knowledge annotation for inter-agent handoffs."""

    # What the upstream agent decided TO do
    decision: str
    rationale: str  # one sentence max

    # What the upstream agent decided NOT to do — and why
    rejected: list["Rejection"] = field(default_factory=list)

    # Constraints that must survive the handoff
    hard_constraints: list[str] = field(default_factory=list)

    # What would make a rejected approach viable again
    unblock_condition: Optional[str] = None


@dataclass
class Rejection:
    approach: str          # e.g. "use regex for HTML parsing"
    reason: str            # e.g. "malformed tags in production data cause 40% miss rate"
    evidence: Optional[str] = None  # optional: token cost, error log, benchmark result
```

### Injecting into a LangGraph handoff

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from dataclasses import dataclass, field
from typing import TypedDict


class AgentState(TypedDict):
    messages: list
    handoff_note: dict | None  # carries negative knowledge


def researcher_node(state: AgentState) -> AgentState:
    # ... do research, produce findings ...
    findings = run_research(state["messages"])

    # Build the handoff note — this is the negative knowledge
    handoff = {
        "decision": "Focused on PDF extraction via pymupdf",
        "rationale": "pymupdf handles malformed PDFs that pdfplumber chokes on",
        "rejected": [
            {
                "approach": "pdfplumber for table extraction",
                "reason": "30% of our PDFs have nested tables that pdfplumber flattens incorrectly",
                "evidence": "Ran on 200 docs: pdfplumber 0.70 acc vs pymupdf 0.91 acc",
            },
            {
                "approach": "OCR-first approach for all documents",
                "reason": "Adds 8s latency per doc; 70% of docs are born-digital with clean text",
            },
        ],
        "hard_constraints": [
            "Must preserve table structure (row headers + cell coordinates)",
            "No external network calls during extraction",
        ],
        "unblock_condition": (
            "If document count exceeds 10k/day AND OCR latency budget approved, "
            "re-evaluate OCR-first for born-digital docs (eliminates malformed-PDF class)"
        ),
    }
    return {"messages": [findings], "handoff_note": handoff}


def writer_node(state: AgentState) -> AgentState:
    handoff = state.get("handoff_note", {})

    # The writer reads negative knowledge before starting
    rejection_list = handoff.get("rejected", [])
    constraint_text = "\n".join(
        f"- REJECTED: {r['approach']} — {r['reason']}"
        for r in rejection_list
    )
    constraints = "\n".join(f"- {c}" for c in handoff.get("hard_constraints", []))

    system_prompt = f"""You are writing a report. Before drafting:
1. Acknowledge what was already ruled out:
{constraint_text}
2. Respect these hard constraints:
{constraints}
3. Unblocking condition (revisit only if this becomes true):
{handoff.get('unblock_condition', 'None')}

Now write the report based on the findings provided."""

    # ... rest of writing logic ...
    return {"messages": [write_report(state["messages"], system_prompt)]}
```

### The lightweight alternative: one-prompt addition

If you can't change the schema, add this to every handoff prompt:

```
Before acting, read the following and do NOT retry any of these approaches:
- {APPROACH_A}: ruled out because {REASON_A}
- {APPROACH_B}: ruled out because {REASON_B}

Constraints you must respect: {CONSTRAINT_1}, {CONSTRAINT_2}

If {UNBLOCKING_CONDITION} becomes true, you may re-evaluate the above.
```

### Detecting when negative knowledge was lost

```python
import hashlib
from typing import Any


def handoff_integrity_hash(note: dict) -> str:
    """Store a hash of what was rejected so downstream can detect omissions."""
    payload = {
        "decision": note.get("decision", ""),
        "rejected": sorted(note.get("rejected", []), key=lambda r: r["approach"]),
        "constraints": sorted(note.get("hard_constraints", [])),
    }
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def validate_handoff_integrity(upstream_hash: str, downstream_note: dict) -> bool:
    """Downstream agent checks: did upstream share what it rejected?"""
    current_hash = handoff_integrity_hash(downstream_note)
    if current_hash != upstream_hash:
        # Handoff was truncated or negative knowledge was stripped
        raise HandoffIntegrityError(
            f"Handoff integrity check failed: {upstream_hash} != {current_hash}. "
            "Negative knowledge may have been lost in transit."
        )
    return True
```

## Receipt

> Receipt pending — 2026-08-20

Verified patterns from research:
- Paella doc (paelladoc.com, Jul 2026): "What gets lost is everything that is not code: decisions already made, constraints that must hold, paths already tried and rejected. The default handoff is 'here is the chat, catch up.'"
- MAST taxonomy (arxiv:2503.13657): Inter-agent misalignment named as one of three primary failure categories across 1,600+ production traces.
- Reddit r/AI_Agents field report (Aug 2026): "planner decides to skip approach A because of constraint X; handoff contains the task, not the constraint; executor picks approach A; loop fails silently." Solution: "every agent output should carry what it decided NOT to do, and why."
- SkillsMP session handoff skill (charliecpeterson): Explicit "considered and rejected" section with two-field distinction: "we thought about X and chose not to" vs. "we tried X and it failed."

## See also

- [S-1182 · The Structured Agent Handoff Stack](stacks/s1182-the-structured-agent-handoff-stack-when-your-agents-compose-into-a-worse-system.md) — covers schema contracts for handoff *outputs*; S-2892 adds negative knowledge to what outputs *omit*
- [S-1286 · The Handoff Contract](stacks/s1286-the-handoff-contract-when-your-agent-hands-off-work-and-the-context-goes-missing.md) — covers context preservation; S-2892 covers *context exclusion* (what was ruled out)
- [S-1325 · The Agent Handoff Stack](stacks/s1325-the-agent-handoff-stack-when-your-agents-pass-bad-batons.md) — covers coordination failures and baton-drop; S-2892 is the proactive fix: structuring what goes on the baton before it drops
