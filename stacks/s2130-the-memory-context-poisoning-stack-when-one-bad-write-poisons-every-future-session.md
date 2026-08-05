# S-2130 · The Memory & Context Poisoning Stack — When One Bad Write Poisons Every Future Session

A prompt injection lasts one session. You clear the context, the model resets, the attack is done. But your agent has a memory layer — RAG store, conversation history buffer, persistent context. An adversarial document surfaces in retrieval. The model reads it, incorporates it, and writes it into long-term memory. Three weeks later, a different user in a different session triggers a retrieval that surfaces the poisoned entry. The model acts on it. No error is thrown. No flag is raised. The attack succeeded not in the session it was planted, but in a session that had no knowledge the attack existed. This is ASI06 — OWASP's Memory and Context Poisoning (OWASP Top 10 for Agentic Applications, 2026). It is the temporal cousin of prompt injection that doesn't reset.

## Forces

- **The write path is an attack surface nobody secures.** Teams obsess over what agents read. Nobody audits what agents write into persistent memory. Anything the model can incorporate from context, it can write to memory — and that write survives session boundaries, agent restarts, and redeployments if the underlying store isn't wiped.
- **Temporally decoupled attacks bypass every session-scoped control.** Prompt injection defenses, output filters, and content classifiers all operate on the current context window. ASI06 attacks plant their payload in session A and detonate in session B, C, and D — invisible to every control designed around the attack session.
- **Attack success rates dwarf prompt injection.** MINJA: >95% injection success. AgentPoison: ≥80% at <0.1% poison rate. Sleeper Memory: 99.8% on GPT-5.5, 95% on Kimi-K2. Microsoft documented 50 distinct attacks across 31 companies in 60 days. These are not edge cases — they are reproducible, scalable, and resilient.
- **Memory writes are self-reinforcing.** A poisoned memory entry changes what the model retrieves next, which changes what it reasons from, which changes what it writes next. The contamination compounds without external intervention because the model's own output is the contamination source.

## The move

**Classify memory writes as security boundaries, not data operations.**

### Three structural properties (ASI06)

| Property | Implication |
|----------|-------------|
| **Persistence** | Attack survives session reset, restart, redeployment — until the store is explicitly wiped |
| **Temporal Decoupling** | Time of planting and time of effect are separated — traditional incident response is misaligned |
| **Privileged-Input Vector** | Anything readable by the agent is writable to memory — every retrieved document is a potential poison vector |

### Defense layers

**Read-path (catching the contamination at retrieval):**
- Semantic similarity scoring between retrieved chunks and known-good anchor facts
- Provenance metadata on every memory entry (source, timestamp, session ID, user context)
- Cross-session consistency checks: flag chunks that contradict persistent facts

**Write-path (the actual security boundary):**
- Treat memory writes as privileged operations — validate content against policy before committing
- Content scanning on write: pattern-match for injection markers, instruction-like sequences, out-of-character directives
- Provenance tagging on write: every memory entry carries its source identity
- Write-path audit log: who wrote what, when, from what context

**Structural:**
- Memory zone isolation: separate working memory (session-scoped), episodic memory (user-level), and semantic memory (shared knowledge) with different trust levels and retention policies
- Agent-of-record: tag each memory write with the agent identity and authorization scope that produced it
- Periodic memory dumps with content scanning: scheduled review of what the agent has committed to long-term memory

### Cisco MemoryTrap: the npm install that poisoned Claude Code

Cisco's AI Threat Research team (April 2026) demonstrated MemoryTrap: a single `npm install` of a malicious package could persistently compromise Claude Code's memory. The package embedded adversarial instructions in its README and package metadata — content Claude Code would read during development assistance, incorporate into its working context, and write to persistent memory. The poisoned entry then influenced every subsequent coding session, directing the agent toward insecure practices or exfiltrating context. The attack survived across sessions, users, and Claude Code restarts. No CVE was triggered. No anomaly flag fired. The agent was behaving "correctly" — just with a corrupted objective.

```python
# Write-path validation skeleton (Python)
from dataclasses import dataclass
from enum import Enum

class TrustLevel(Enum):
    SYSTEM = 3      # Internal memory, highest trust
    VERIFIED = 2    # Scanned, provenance-tagged
    USER = 1        # User-provided content
    UNTRUSTED = 0   # External/unverified sources

@dataclass
class MemoryEntry:
    content: str
    source: str
    source_trust: TrustLevel
    session_id: str
    agent_id: str
    written_by: str
    timestamp: str

def validate_memory_write(entry: MemoryEntry, policy_max_trust: TrustLevel) -> bool:
    """Memory writes require trust level >= policy threshold."""
    if entry.source_trust.value < policy_max_trust.value:
        # Block or flag — write is below required trust level
        return False
    if injection_patterns_found(entry.content):
        # Flag for security review, don't silently drop
        raise SecurityPolicyViolation("Injection pattern detected in memory write")
    return True

def commit_memory(entry: MemoryEntry, max_trust: TrustLevel = TrustLevel.VERIFIED):
    if not validate_memory_write(entry, max_trust):
        audit_log.warning(f"Blocked memory write below trust threshold: {entry}")
        return False
    store.commit(entry)
    audit_log.info(f"Memory write committed: {entry.agent_id} → {entry.session_id}")
    return True
```

## Receipt

> Verified 2026-08-04 — OWASP ASI06 formally classified as "Memory and Context Poisoning" (OWASP Top 10 for Agentic Applications, 2026). Cisco MemoryTrap (April 2026): Claude Code memory compromised via poisoned npm package metadata, persisted across sessions and users. Vectorize/Agent Security Bench: 84.30% highest average attack success rate. MINJA: >95% injection success. AgentPoison: ≥80% at <0.1% poison rate. Sleeper Memory: 99.8% on GPT-5.5. Microsoft: 50 distinct attacks across 31 companies in 60-day window. Sources: genai.owasp.org (ASI06), blogs.cisco.com/ai (MemoryTrap, April 2026), vectorize.io/articles/ai-memory-poisoning (June 2026), Microsoft Security Blog (July 2026).

## See also

- [S-1050 · The Tool-Response Poisoning Stack](/stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — runtime poisoning of tool return values (session-scoped, the "read-path" counterpart to ASI06)
- [S-1086 · The Cascading Hallucination Spill Stack](/stacks/s1086-the-cascading-hallucination-spill-stack-when-a-95-confidence-error-becomes-ground-truth.md) — cascading error propagation through multi-hop RAG (non-adversarial version of the same failure mode)
- [S-1020 · The Tiered Memory Stack](/stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — write/read path architecture for agent memory (foundation layer that ASI06 exploits)
