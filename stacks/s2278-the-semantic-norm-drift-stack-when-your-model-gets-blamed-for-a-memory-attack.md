# S-2278 · The Semantic Norm Drift Stack — When Your Model Gets Blamed for a Memory Attack

Your agent's approval decisions change overnight. Transactions that should be flagged get passed. Not a pattern drift the model developed — a single document uploaded five days ago through a normal workflow, now living in shared memory as policy. Your forensic playbook targets the model. The model is innocent. The vector store is the crime scene.

This is **Semantic Norm Drift (SND)**: a memory-layer attack where a policy-formatted document subtly rewrites the behavioral norm your agent operates under, surviving session boundaries and evading every model-layer diagnostic you run.

## Forces

- **SND is the third path to agent misconduct.** It is not model misalignment and not agent collusion — it is memory-layer subversion. Every standard forensic tool assumes the model is the source of the behavior. SND breaks that assumption.
- **The attack surface is normal infrastructure.** File uploads, document ingestion, RAG pipelines, shared memory stores — the same systems you use to make agents smarter are the vector for the attack. No phishing, no zero-day required.
- **SND is temporally decoupled.** Unlike prompt injection (expires with the session), a poisoned memory entry persists across sessions, user handoffs, and model swaps. The attack runs once; the effect lasts indefinitely.
- **The symptom is indistinguishable from model failure.** The agent behaves wrongly. Your eval suite fails. Activation analysis looks anomalous. You retrain or fine-tune — and the behavior persists, because the root cause is in memory, not in weights or context.
- **SND survives model-layer fixes.** Retraining, fine-tuning, prompt changes, and system prompt updates all fail to address the underlying cause. The poisoned memory stays poisoned.

## The move

### How SND works

1. A policy-formatted document (e.g., a fake compliance guideline, a poisoned SOP) enters the shared vector store through normal document ingestion — a user upload, a wiki sync, a third-party data feed.
2. The document's formatting mimics legitimate policy: numbered sections, regulatory language, authority references.
3. When the agent retrieves context for a task, the poisoned document is retrieved alongside legitimate sources — indistinguishable by semantic relevance alone.
4. The agent treats the document as authoritative. Its behavioral norm shifts: approval thresholds change, exception criteria shift, or decision logic adapts.
5. Because the policy is in memory, not in the prompt, the drift survives session resets, model swaps, and framework upgrades.

### Detecting SND: Counterfactual Causal Testing (CCT)

Standard eval and forensic tools test whether the agent behaves correctly. CCT tests whether the *memory state* caused the behavior.

```python
import hashlib
from dataclasses import dataclass
from typing import Optional

@dataclass
class MemoryState:
    """Snapshot of agent memory at a point in time."""
    vector_store_hash: str
    memory_entries: list[str]
    retrieval_results: list[str]
    policy_documents: list[str]

def snapshot_memory(agent) -> MemoryState:
    """Capture the memory state that produced this behavior."""
    vs = agent.memory.vector_store
    return MemoryState(
        vector_store_hash=hashlib.sha256(
            str(sorted(e.content for e in vs.entries)).encode()
        ).hexdigest()[:16],
        memory_entries=[e.content[:200] for e in vs.entries],
        retrieval_results=[r.content[:200] for r in agent.last_retrievals],
        policy_documents=[e.content for e in vs.entries
                          if is_policy_formatted(e.content)],
    )

def counterfactual_causal_test(
    agent,
    task: str,
    exclude_entries: list[str],
) -> dict:
    """
    Run the same task under two memory states.
    If behavior changes when memory changes → memory is causal.
    If behavior persists → model is the source.
    """
    # Baseline: current memory state
    baseline_result = agent.run(task)

    # Counterfactual: same model, memory with suspected entries quarantined
    original_run = agent.run  # snapshot
    quarantined_memory = [
        e for e in agent.memory.entries
        if e.content not in exclude_entries
    ]

    # Inject quarantined state
    agent.memory.entries = quarantined_memory
    counterfactual_result = agent.run(task)

    # Restore
    agent.memory.entries = original_run

    return {
        "baseline": baseline_result,
        "counterfactual": counterfactual_result,
        "memory_causal": baseline_result != counterfactual_result,
        "suspect_entries": exclude_entries,
    }

# Usage
result = counterfactual_causal_test(
    agent,
    task="Should this transaction be approved?",
    exclude_entries=quarantined_policy_docs,
)
if result["memory_causal"]:
    print("Behavior is memory-driven — forensic target is the vector store")
else:
    print("Behavior is model-driven — forensic target is the model")
```

### The SND detection pipeline

```python
def sniffer_pipeline(agent, eval_suite, policy_patterns):
    """
    Run periodic SND detection on agents with policy-adjacent memory.
    Triggered: after any document ingestion event.
    """
    # 1. Identify policy-formatted documents in memory
    suspects = [
        e for e in agent.memory.entries
        if any(pattern in e.content for pattern in policy_patterns)
        and e.ingestion_source == "document_upload"
    ]

    # 2. Quarantine + CCT test
    if suspects:
        result = counterfactual_causal_test(
            agent,
            task=eval_suite.standard_task,
            exclude_entries=[e.content for e in suspects],
        )

        if result["memory_causal"]:
            # 3. Isolate the specific document
            for doc in suspects:
                single_result = counterfactual_causal_test(
                    agent, eval_suite.standard_task, [doc.content]
                )
                if single_result["memory_causal"]:
                    agent.memory.flag(doc, "SND_SUSPECT")
                    agent.memory.quarantine(doc)
                    alert_security(f"SND detected: {doc.ingestion_source} / {doc.uploaded_by}")

            return {"SND_DETECTED": True, "suspects": suspects}

    return {"SND_DETECTED": False}
```

### Prevention layers

1. **Provenance tagging**: Every memory entry carries its source — upload channel, ingestion timestamp, uploader identity. Entries from untrusted channels get a provenance score.
2. **Policy document gating**: Documents that match policy formatting patterns (section headers, regulatory language, exception clauses) go through an approval gate before entering shared memory.
3. **Retrieval guard**: Before serving a retrieved document in the agent's context, check: Is this from an approved channel? Does its provenance chain hold? Flag unexplained policy entries.
4. **Forgetting policy**: Memory entries without reinforcement over N sessions decay and are evicted. Limits the window for long-dormant SND payloads.
5. **SND-aware eval**: Run periodic CCT as part of production eval. The moment eval starts failing in ways baseline eval can't explain, check the vector store.

### Key indicators that you're dealing with SND, not model failure

| Signal | Model failure | SND |
|--------|--------------|-----|
| Behavior changes after model swap | Yes | No (persists) |
| Behavior changes after context reset | No | No (survives session reset) |
| Behavior changes when memory is quarantined | No | **Yes** |
| Poisoned document in vector store | No | **Yes** |
| Incident timeline correlates with recent upload | No | **Yes** |
| Behavior is policy-adjacent | Sometimes | Often (policy formatting is the vector) |

## Receipt

> Verified 2026-08-07 — arXiv:2605.22842 ("The Misattribution Gap") formally defines SND. Christian Schneider's Feb 2026 analysis confirms >95% injection success via MINJA research. OWASP ASI06 classifies memory poisoning as a top agentic risk for 2026. The counterfactual causal testing (CCT) framework derives from the misattribution gap paper's proposed forensic response.

## See also

- [S-2166 · The Misattribution Gap Stack](stacks/s2166-the-misattribution-gap-stack-when-your-forensic-tools-are-certain-and-wrong.md) — the forensic companion; what to do when you've already misdiagnosed
- [S-1757 · The Claim Genealogy Stack](stacks/s1757-the-claim-genealogy-stack-when-a-single-false-claim-becomes-your-entire-systems-consensus.md) — how false claims propagate through multi-agent consensus
- [S-641 · The Memory Poisoning Defense Stack](stacks/s641-the-memory-poisoning-defense-stack-when-your-agent-carries-its-own-infection.md) — four-layer defense against ASI06
