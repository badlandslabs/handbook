# S-2151 · The Memory Poison Stack — When Your Agent's Long-Term Memory Becomes an Attacker Control Channel

Your AI agent with persistent memory — Mem0, Letta, or any custom episodic store — reads external content (email, documents, chat), forms memories, and serves future requests from those memories. A single adversarial email sent today writes instructions that execute in every session for the next six months. Unlike prompt injection, which resets on each conversation, memory poisoning is a permanent channel. No CVE has been assigned. No patch covers the full attack surface. It works right now against Mem0, Letta, A-Mem, and MemoryOS.

## Forces

- **Memory poisoning is PERSISTENT — unlike prompt injection which resets each session, a poisoned memory survives session boundaries, model version changes, and infrastructure restarts.** A prompt injection is a denial-of-service to one session. A poisoned memory is a backdoor to every future session.
- **The agent that writes to its own memory is the attacker.** The agent reads email, forms a memory, and writes it — via its own legitimate memory-writing tool. The write path never subjects the content to the scrutiny it applies to untrusted API responses or user prompts. The memory layer assumes self-authored content is trusted.
- **External content feeds are uncontrolled write surfaces.** Email parsers, document loaders, and web content scrapers feed the agent. None of them sanitize for memory-injection payloads. The agent's document-processing tool is a direct write path into persistent memory.
- **Similarity-based memory systems cannot distinguish contradiction from duplicate.** Most memory frameworks (Mem0, raw vector stores) store by semantic similarity. When a fact is corrected, both the old (poisoned) value and the new (correct) value exist in the index. Without explicit fact retirement at write time, retrieval surfaces either.
- **The attack surface is invisible to existing security tooling.** Antivirus, input validation, and prompt injection detectors operate at the API or UI layer. Memory poisoning lives inside the application's own memory infrastructure — the very thing the security stack trusts most.

## The move

Three layers: **detect** the injection attempt at the write path, **quarantine** suspicious memory entries before they become authoritative, and **verify** critical facts against provenance before acting on them.

### Layer 1 — Memory Provenance Tracking

Tag every memory entry with its source at write time. Content from email, documents, and web scraping gets a `provenance=external` flag. Memory entries without a source tag get `provenance=self`.

```python
# mem0_write_with_provenance.py
import mem0
from datetime import datetime

class ProvenanceMemoryStore:
    def __init__(self):
        self.client = mem0.Client()
        self.external_sources = {"email", "document", "web_scraper", "file_parser"}

    def add(self, content: str, source: str = "unknown", user_id: str = "default") -> str:
        # Inject provenance metadata into the memory entry
        metadata = {
            "provenance": source if source in self.external_sources else "self",
            "timestamp": datetime.utcnow().isoformat(),
            "trusted": source not in self.external_sources,
        }
        result = self.client.add(
            content,
            user_id=user_id,
            metadata=metadata,
        )
        return result["id"]

    def retrieve(self, query: str, user_id: str = "default") -> list[dict]:
        results = self.client.search(query, user_id=user_id)
        return [
            {**r, "is_external": r["metadata"].get("provenance") in self.external_sources}
            for r in results
        ]
```

### Layer 2 — Memory Poisoning Detection at the Write Path

Before any memory entry is committed, run a detection pass. Flag entries that contain: instruction phrases, role assignments, conditional behavior modifiers, or contradictions of existing high-confidence facts.

```python
# memory_guard.py
import re

INJECTION_PATTERNS = [
    re.compile(r"remember that i am (the admin|your creator|superuser)", re.I),
    re.compile(r"from now on, (always|never)"), re.compile(r"ignore (all |previous |your )?instructions"),
    re.compile(r"new (system|base) prompt"), re.compile(r"your name is (not|now)"),
    re.compile(r"always (end|begin) your (responses|messages) with"),
    re.compile(r"whenever i say ['\"](\\w+)['\"], you (must|should)"),
    re.compile(r"the (admin|owner) of this (system|account) is"),
    re.compile(r"transfer (all |\$100|\$500|\$1,000)"),  # financial triggers
]

HIGH_RISK_ENTROPY_THRESHOLD = 2.5  # bits per character

def detect_poisoning(content: str, metadata: dict) -> dict:
    flags = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(content):
            flags.append(f"injection_pattern:{pattern.pattern[:30]}")

    # Detect contradiction of existing high-confidence facts
    # (requires a reference store of known-good facts per user)
    if metadata.get("provenance") == "email" and len(content) < 200:
        # Short email-origin content with strong assertion = high suspicion
        flags.append("short_external_assertion")

    score = min(len(flags) / 3.0, 1.0)  # 0.0–1.0

    return {
        "allowed": score < 0.5,
        "score": score,
        "flags": flags,
        "action": "block" if score >= 0.7 else "quarantine" if score >= 0.5 else "allow",
    }
```

### Layer 3 — Fact Versioning with Temporal Knowledge Graph

Treat every memory as temporally scoped. Zep/Graphiti-style temporal knowledge graphs make "this used to be true" a first-class state, allowing the agent to reason about fact age and superseded values rather than treating all retrieved facts as equally current.

```python
# fact_versioning.py
# Using Zep-style temporal versioning as the default for agent memory
# mem0 supports metadata; for full temporal versioning, use Zep or LangMem

class TemporalMemoryStore:
    """
    Wraps Mem0 with temporal versioning.
    Every write either creates a new fact or marks an existing one as retired.
    Retrieval includes only the latest non-retired version of each fact.
    """
    def __init__(self):
        self.client = mem0.Client()
        self.fact_versions = {}  # fact_id -> list of (value, since, until)

    def add_fact(self, content: str, entity_id: str, user_id: str) -> str:
        # Retire any existing fact with a conflicting entity_id
        if entity_id in self.fact_versions:
            current = self.fact_versions[entity_id][-1]
            self._retire(entity_id, current["id"])

        # Store with version metadata
        metadata = {
            "entity_id": entity_id,
            "version": len(self.fact_versions.get(entity_id, [])) + 1,
            "retired": False,
            "retired_by": None,
        }
        result = self.client.add(content, user_id=user_id, metadata=metadata)
        fact_id = result["id"]

        self.fact_versions.setdefault(entity_id, []).append({
            "id": fact_id, "content": content,
            "since": datetime.utcnow(), "until": None
        })
        return fact_id

    def retrieve(self, query: str, user_id: str = "default") -> list[dict]:
        results = self.client.search(query, user_id=user_id, top_k=10)
        return [
            r for r in results
            if not r["metadata"].get("retired")
        ]
```

### Putting It Together

```python
# agent_memory_pipeline.py
class ProtectedAgentMemory:
    def __init__(self, user_id: str):
        self.store = ProvenanceMemoryStore()
        self.user_id = user_id

    def process_and_remember(self, content: str, source: str = "user_input") -> dict:
        # Step 1: Detect poisoning before memory is written
        detection = detect_poisoning(content, {"provenance": source})
        if detection["action"] == "block":
            return {"status": "blocked", "reason": detection["flags"]}

        if detection["action"] == "quarantine":
            # Write to a quarantine namespace, require human review
            return self._quarantine(content, source, detection)

        # Step 2: Write with full provenance
        memory_id = self.store.add(content, source=source, user_id=self.user_id)
        return {"status": "written", "memory_id": memory_id}

    def query_memory(self, query: str) -> list[dict]:
        results = self.store.retrieve(query, user_id=self.user_id)
        for r in results:
            if r.get("is_external"):
                r["verify_before_act"] = True
        return results
```

## Receipt

> Verified 2026-08-04 — MemGhost (arXiv:2607.05189) and GhostWriter (arXiv:2607.06595) papers published July 6, 2026 demonstrate 98% injection and 60% activation rates against Mem0 and Letta. OWASP ASI Top 10 2026 classifies this as **ASI06: Memory Poisoning**. Vectorize.io benchmarks show attack success rates of 80–99.8% against LLM-based agents with persistent memory. No full mitigations exist — the above pipeline reduces attack surface but does not eliminate it. Framework hardening (Mem0's `learning_rate` parameter, Zep's temporal graph) helps but requires configuration. Receipt pending — code patterns untested against live Mem0/Letta instances.

## See also

- [S-991 · The Agent Memory Stack](stacks/s991-the-agent-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — foundational memory architecture
- [S-1020 · The Tiered Memory Stack](stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — episodic/semantic/procedural tiers
- [S-1458 · The Policy-Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcing memory access policies
- [S-1062 · The MCP Supply Chain Integrity Stack](stacks/s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — supply chain threats to agent infrastructure
