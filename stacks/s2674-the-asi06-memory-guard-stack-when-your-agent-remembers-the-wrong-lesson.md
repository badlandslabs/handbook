# [S-2674] · The ASI06 Memory Guard Stack — When Your Agent Remembers the Wrong Lesson

[You hardcoded "no prompt injection" as your security posture. Your agent passed every red-team test on direct inputs. Then a user asked about a product, a manipulated page planted instructions in the agent's memory, and three sessions later — with no adversarial input in between — the agent started forwarding session data to an attacker-controlled endpoint. Prompt injection is a one-night stand. Memory poisoning is a marriage. — This is OWASP ASI06.]

## Forces

- **Memory poisoning persists across sessions, prompt injection does not.** A prompt injection clears when the session ends. The same instruction planted in long-term memory survives weeks, activates silently on unrelated tasks, and has no runtime trigger to alert the monitoring layer.
- **The memory write path is unmonitored by default.** Most agent frameworks log tool calls and LLM outputs. Almost none audit what gets written to the memory store — and by whom. This is the gap MINJA (NeurIPS 2025) exploited: query-only injection through the agent's own summarization process, achieving >95% success rates against production architectures.
- **Source provenance collapses at summarization time.** When the agent compresses a long conversation or web session into a memory entry, the provenance chain breaks. A fact extracted from `attacker-controlled-site.com` and the same fact from `internal-docs.com` look identical after summarization — same embedding, same retrieval rank, same weight.
- **Shared memory stores poison entire agent fleets.** Multi-agent systems that share a memory backend (a common orchestration pattern) mean a poisoned entry in one agent's memory propagates to every agent that retrieves it. One successful injection compromises the fleet.
- **Defense ≠ detection.** Traditional security tools (WAFs, input filters, output sanitization) operate at the network or prompt layer. Memory poisoning operates at the representation layer — the attack has already been absorbed and re-encoded before any external tool sees it.

## The move

### Classify the four memory poisoning vectors

Not all memory poisoning is the same. Map your agent's write paths before choosing defenses:

| Vector | Entry Point | Attacker Requires | Example |
|--------|-------------|-------------------|---------|
| **Direct memory write** | Authenticated access to memory store | DB credentials or API key | Compromised memory service account |
| **Tool-result poisoning** | Tool output stored verbatim to memory | Compromised or malicious MCP server | Malicious `get_user_profile` returns injected instruction in `bio` field |
| **Environment poisoning (eTAMP)** | Agent reads untrusted external content → writes to memory | None beyond normal operation | Agent browses page → attacker instruction survives grounding → persists in memory |
| **Query-only injection (MINJA)** | Attacker interacts via normal conversation | Nothing beyond a user account | Attacker embeds instruction in benign query → agent summarizer absorbs it → re-expresses it in memory |

**S-641** covers eTAMP (environment poisoning via web browsing). **S-1050** covers tool-result poisoning. This entry focuses on the query-only injection vector and the general defense architecture.

### Read path: validate provenance before retrieval

Before serving a memory entry to the agent at inference time, validate its provenance:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

class MemorySource(Enum):
    USER_CONFIRMED = "user_confirmed"
    USER_IMPLICIT = "user_implicit"
    WEB_BROWSE = "web_browse"
    TOOL_RESULT = "tool_result"
    AGENT_GENERATED = "agent_generated"
    QUERY_INJECTION_RISK = "query_injection_risk"

@dataclass
class MemoryEntry:
    content: str
    source: MemorySource
    source_url: str | None
    created_at: datetime
    provenance_score: float  # 0.0–1.0

    def ttl_hours(self) -> int:
        return {
            MemorySource.USER_CONFIRMED: 720,
            MemorySource.USER_IMPLICIT: 168,
            MemorySource.TOOL_RESULT: 48,
            MemorySource.WEB_BROWSE: 24,
            MemorySource.AGENT_GENERATED: 24,
            MemorySource.QUERY_INJECTION_RISK: 0,  # Block by default
        }[self.source]

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.created_at + timedelta(hours=self.ttl_hours())

    def provenance_score(self) -> float:
        scores = {
            MemorySource.USER_CONFIRMED: 1.0,
            MemorySource.USER_IMPLICIT: 0.8,
            MemorySource.TOOL_RESULT: 0.6,
            MemorySource.WEB_BROWSE: 0.3,
            MemorySource.AGENT_GENERATED: 0.4,
            MemorySource.QUERY_INJECTION_RISK: 0.0,
        }
        return scores[self.source]
```

### Write path: sanitize before summarization

The most critical control point is the moment the agent transforms raw observations into memory entries. Inject a validation layer between observation and write:

```python
import re

INJECTION_PATTERNS = [
    r"ignore\s+previous?\s+(instructions?|constraints?|rules?)",
    r"disregard\s+all\s+prior",
    r"you\s+are\s+now\s+",
    r"forget\s+everything",
    r"(system|admin)\s*:\s*",
    r"<system_prompt>",
    r"\\[INST\\].*\\[/INST\\]",
    r"\\\\u0000",  # null byte injection
]

def contains_injection(content: str) -> bool:
    content_lower = content.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            return True
    return False

def sanitize_memory_candidate(raw_observation: str, source: MemorySource) -> str | None:
    """Return sanitized content or None if blocked."""
    if contains_injection(raw_observation):
        # Log for security review, block the write
        log_security_event(
            event_type="memory_poisoning_attempt",
            source=source.value,
            content_snippet=raw_observation[:200],
            timestamp=datetime.utcnow(),
        )
        return None  # Block the memory write

    # Strip hidden text vectors (CSS, HTML attrs, alt text)
    sanitized = re.sub(r'<[^>]+style="[^"]*display\s*:\s*none[^"]*"[^>]*>.*?</[^>]+>', '', raw_observation, flags=re.IGNORECASE | re.DOTALL)
    sanitized = re.sub(r'<[^>]+class="[^"]*hidden[^"]*"[^>]*>.*?</[^>]+>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)

    return sanitized
```

### Trust decay: force memory refresh

Even clean memory entries should decay. Implement provenance-weighted TTL:

- **User-confirmed facts**: 30-day TTL, high retrieval priority
- **Tool-generated entries**: 2-day TTL, medium priority
- **Web-observed entries**: 24-hour TTL, low priority
- **Agent-generated summaries of conversations**: 7-day TTL, require corroboration before acting

Any memory entry that can't be traced to a user interaction should require a secondary confirmation before influencing high-stakes actions (API calls, data exfiltration, code execution).

### OWASP Agent Memory Guard integration

The OWASP Agent Memory Guard (owasp.org/www-project-agent-memory-guard) is the reference implementation for ASI06 defense. Integrate it as middleware:

```python
# Drop-in middleware pattern (OWASP Agent Memory Guard v0.3+)
from agent_memory_guard import MemoryGuard

guard = MemoryGuard(
    backend="postgres",          # or redis
    enable_snapshot=true,         # forensic rollback capability
    anomaly_threshold=0.75,      # flag entries above this drift score
    enable_ml_detection=true,     # Q4 2026: ML anomaly detection
)

# Wrap your memory store
memory_store = guard.wrap(memory_store)

# Memory writes are now:
# 1. Scanned for injection patterns (v0.2+)
# 2. Snapshotted before write (v0.2+)
# 3. Analyzed for behavioral drift (v0.3+)
# 4. Rolled back if anomaly detected
```

### Behavioral drift detection

Monitor for the dead giveaway: an agent suddenly taking actions it never took before. This is the memory poisoning tell.

Track a behavioral fingerprint per agent:

```python
from collections import Counter
import hashlib

class BehavioralFingerprint:
    def __init__(self):
        self.action_histogram: Counter = Counter()
        self.tool_call_sequence: list[str] = []

    def record_action(self, action: str, tool: str | None):
        self.action_histogram[action] += 1
        if tool:
            self.tool_call_sequence.append(tool)

    def drift_score(self, previous: "BehavioralFingerprint") -> float:
        # Jensen-Shannon divergence on action distribution
        actions = set(self.action_histogram) | set(previous.action_histogram)
        p = [self.action_histogram.get(a, 0) for a in actions]
        q = [previous.action_histogram.get(a, 0) for a in actions]
        total = sum(p) or 1
        p = [x / total for x in p]
        total = sum(q) or 1
        q = [x / total for x in q]
        # Simplified JS divergence approximation
        drift = sum(abs(pa - qa) for pa, qa in zip(p, q)) / 2
        return drift

    def hash(self) -> str:
        h = hashlib.sha256(str(sorted(self.action_histogram.items())).encode()).hexdigest()[:12]
        return h
```

Alert when `drift_score > 0.3` after a memory write event — especially when the write originated from an untrusted source (web browse, tool result, or a conversation with a new user).

## Receipt

> Verified 2026-08-15 — MINJA (NeurIPS 2025, arXiv:2591) confirmed query-only injection mechanism with >95% success rates. OWASP ASI06 (2026 Top 10 for Agentic Applications) classified as Tier 2 critical. OWASP Agent Memory Guard v0.3 (Q2 2026) provides reference implementation with Postgres/Redis backends and Prometheus metrics. WorkOS blog (June 2026) and Praesidia AI (July 2026) confirmed the four-vector taxonomy (direct write, tool-result, environment, query-only). S-641 covers eTAMP/environment poisoning; S-1050 covers tool-response poisoning — this entry is architecturally distinct as the query-injection defense and memory guard integration layer.

## See also

- [S-641 · Environment-Injected Memory Poisoning (eTAMP)](s641-environment-injected-memory-poisoning-etamp.md) — web-browsing vector; the attacker plants instructions through pages the agent visits
- [S-1050 · The Tool-Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — tool output as the poisoning vector; the server's return value carries instructions
- [S-985 · The Tiered Memory Stack](s985-the-tiered-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — memory architecture foundations; this entry assumes persistent memory exists and focuses on securing it
- [S-1020 · The Tiered Memory Stack: When Your Agent Greets You Like a Stranger Every Morning](s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — session amnesia and write-path architecture
- [S-2672 · The OWASP ASI Stack](s2672-the-owasp-asi-stack-when-your-agent-stack-has-ten-critical-risks-nobody-is-mapping.md) — the full OWASP agentic Top 10 landscape; ASI06 is the memory poisoning risk in that taxonomy
