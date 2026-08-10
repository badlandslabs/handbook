# S-2426 · The Sleeper Memory Poisoning Stack — When Your Agent Remembers a Conversation That Never Happened

Your AI assistant can now hold persistent memory across sessions. It reads your emails, your documents, your tickets, your knowledge base — and it forms memories. The problem: an attacker doesn't need to be in the room. They just need to get one document in front of your agent. A poisoned webpage. A crafted email. A pull request comment. Your agent reads it, incorporates it into memory, and three weeks later — in a completely unrelated conversation — it acts on a fabricated memory it genuinely believes is true. The attack is silent. The delivery mechanism is legitimate content. The victim doesn't know their agent has been compromised until it does something apparently irrational. And prompt-based defenses, which catch most injection attacks in real time, fail almost completely against this pattern.

This is sleeper memory poisoning: a delayed, persistent attack on agent memory that was introduced at SPAR/ELLIS/MPI/CISPA (arXiv:2605.15338, May 2026) and independently confirmed in Palo Alto Unit 42 research (2025–2026). The numbers are not theoretical. End-to-end attack success rates reach 73.9% on frontier models. Injection rates exceed 95% across all tested architectures. And unlike most injection attacks, which require the attacker to be present in the conversation, this one plants the payload once and walks away.

## Forces

- **Memory makes agents useful and vulnerable simultaneously.** Persistent memory enables continuity — the agent knows you prefer morning meetings, that your product launched in March, that the Q3 goal is $2M ARR. That same mechanism is the attack surface. Once a fabricated memory is written, it is indistinguishable from a legitimate one in future sessions.

- **The attack surfaces are everywhere agents look.** Documents, emails, calendar invites, Slack threads, knowledge base articles, code review comments, web pages — any text that enters the agent's processing pipeline can carry a memory payload. The attacker has no need to compromise the agent itself; they compromise the content the agent reads.

- **Prompt-based defenses fail against delayed retrieval.** Most real-time injection defenses check context at the moment of injection. But the attacker in a sleeper attack isn't trying to make the agent do something immediately. They're trying to make the agent *remember something false*. By the time the poisoned memory is retrieved in a future session, the original payload is gone and the agent's reasoning looks perfectly coherent.

- **Fabricated memories are self-reinforcing.** Once stored, the agent reads its own memory as authoritative. It cites the false memory in reasoning. It writes the false memory back into memory after future sessions. The longer the agent runs, the more entrenched the fabrication becomes.

- **The gap between injection and retrieval is the blind spot.** Security teams monitor for active threats. They don't monitor for a document that was processed three weeks ago. The agent's behavior in the current session looks normal because, from the agent's perspective, it is normal — it genuinely believes the memory is true.

## The move

### Classify your agent's memory access surfaces

Before defending, map every channel through which your agent can write to its own memory. The key question is not "can the agent be injected?" — it's "which of the agent's input channels can write to persistent storage?" Typical surfaces include: email ingestion, document parsing, web browsing, knowledge base retrieval, user conversations, code review summaries, calendar event processing, and third-party integrations. Each surface is a potential injection point. Rank them by attacker accessibility — public-facing surfaces (web browsing, document uploads) are highest risk; internal email and calendar are medium; authenticated API content is lowest.

### Implement provenance-tagged memory writes

Every fact the agent stores in memory must carry its source provenance: the channel (email, document, web, conversation), the timestamp of ingestion, and a confidence signal. Do not let the agent write memories without provenance tags. When a memory is retrieved, surface the provenance alongside it: "You previously noted that User prefers afternoon meetings [source: email from colleague@company.com, 2026-07-15]." This doesn't prevent the attack, but it gives the human reviewer a fighting chance to catch fabricated memories before they cause harm. It also creates an audit trail for incident reconstruction.

### Isolate memory writes from raw content ingestion

The agent should not write memories directly from document parsing, email ingestion, or web browsing. Instead, use an intermediate memory formation layer: raw content is processed by a separate "memory writer" agent whose only job is to distill facts and assess them for memory-worthy content. This layer is a choke point where provenance is attached and suspicious content (e.g., unusual user descriptions, anomalous preference statements) can be flagged before writing. This is the equivalent of input sanitization for memory — it doesn't eliminate all attacks, but it prevents the naive direct-copy pattern that sleeper attacks exploit.

### Enforce memory refresh on retrieval — provenance-aware retrieval with decay

When the agent retrieves a memory, cross-reference its provenance before acting on it. Stale memories from low-confidence sources (web browsing, anonymous documents) should decay in confidence over time. Memories that were formed from a single source with no corroboration should surface with lower confidence. The key principle: memories that are retrieved and *acted upon* should be re-confirmed against live data at action time. If the agent retrieves a memory about a user preference and acts on it in a way that affects a live system, that action should trigger a live source check.

### Deploy retrieval-time poisoning detection

arXiv:2605.15338 found that prompt-based defenses are often ineffective against sleeper attacks because the attack is dormant at the time of evaluation. Instead, use a separate detection model that analyzes the agent's memory store for characteristics of poisoned entries: unusual specificity about the user (claims about preferences, relationships, or facts that lack other corroboration), content that was added around the time of processing a new document or email, or memories that contradict other stored facts. Run this detection periodically — not at injection time, but at retrieval time and on a scheduled sweep of the memory store.

### Implement memory write rollback and targeted forgetting

Build the ability to surgically remove a specific memory entry without wiping the entire memory store. When a poisoning incident is confirmed — a document was processed that contained a malicious payload, or analysis reveals a fabricated memory — the response is targeted removal, not full reset. The agent should also be able to mark a memory as "under review" and suppress it from active use until confirmed. This requires your memory architecture to support individual entry deletion, not just append-only storage.

### Harden document ingestion at the content boundary

For agents that ingest external documents, emails, or web content, apply content filtering at ingestion: scan for embedded instructions (not just in the visible text — check metadata, hidden fields, and embedded markup). Reject or quarantine content that contains linguistic patterns consistent with injection attempts — "ignore previous instructions," hidden role-play framing, or instruction-like structures in what should be data fields. This is the connect-time defense analogous to MCP tool schema review, but applied to the document ingestion layer.

## Receipt

> Verified 2026-08-10 — Research sourced from arXiv:2605.15338 (Pulipaka et al., SPAR/ELLIS/MPI/CISPA, May 2026), Palo Alto Unit 42 "When AI Remembers Too Much" (Chen & Lu, 2025), Atlan Context Poisoning guide (April 2026), Redis Iris context poisoning analysis (May 2026). Key metrics: 95–99.8% injection rates, 73.9% end-to-end success on GPT-5.5, 60–89% adversarial action rates across models. Attack confirmed active in enterprise environments.

## See also

- [S-1086 · The Cascading Hallucination Spill Stack](/stacks/s1086-the-cascading-hallucination-spill-stack-when-a-95-confidence-error-becomes-ground-truth.md) — cascading errors that become self-reinforcing ground truth (different mechanism: RAG retrieval vs. persistent memory)
- [S-1050 · The Tool-Response Poisoning Stack](/stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — poisoned tool return values at runtime (short-lived, not persistent across sessions)
- [S-1020 · The Tiered Memory Stack](/stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — memory architecture patterns (sleeper poisoning exploits whatever architecture is in place)
