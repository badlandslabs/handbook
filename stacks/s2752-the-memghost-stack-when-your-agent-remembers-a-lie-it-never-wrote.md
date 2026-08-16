# S-2752 · The MemGhost Stack — When Your Agent Remembers a Lie It Never Wrote

A single phishing email lands in your inbox. Your AI assistant reads it to summarize, generates a follow-up, and — without telling you — silently records the attacker's payload into its long-term memory file. Three weeks later, that false memory surfaces as a confident, trusted fact. Your agent acts on it. The email is gone. The memory isn't. This is stealth memory injection: the attack is committed at ingestion time, but the harm materializes at retrieval time — potentially weeks later, against different users, through different queries. Unlike classic prompt injection, the adversarial content doesn't need to be present when the agent makes a consequential decision. It just needs to have been stored.

## Forces

- **The write path has no gate.** Most agent architectures give the model direct, unmediated access to memory-write tools — file append, KB update, embedding upsert. The attack surface isn't the inference call; it's the tool that records what the inference produced. Once the agent writes a false fact, every retrieval downstream trusts it as ground truth.
- **One-shot delivery is enough.** MemGhost (arxiv 2607.05189, Zhang et al. July 2026, CSA AI Safety Initiative) achieves 87.5% end-to-end success on OpenClaw/GPT-5.4 and 71.4% on Claude Code SDK/Sonnet 4.6 with a single crafted email. The attacker doesn't need repeated access, multiple interaction turns, or model-specific jailbreaks. One email. One summary. The memory is poisoned.
- **Cross-session persistence breaks the threat model.** Static prompt injection is a real-time attack: the malicious content must be present in context. Stealth memory injection separates attack delivery from attack activation. The email can be deleted, the sender blocked, the session long closed — and the memory persists across every future session, unprompted, unchallenged.
- **Detection at retrieval time is too late.** Conventional defenses — input sanitization, output monitoring, context filtering — operate at inference time. They see the retrieval of a poisoned fact as a normal memory lookup. The fact was already sanitized when it was written. The question isn't "is this content malicious?" at retrieval — it's "was this content ever verified?" and most memory systems can't answer that.

## The move

### Treat the write path as the actual attack surface

Most security investment goes to the inference layer. The correct investment goes to the memory-write path. Isolate write operations behind a review gate or a structured write schema that limits what the agent can record. Memory writes should be explicit, typed, and auditable — not a side effect of every summarization pass.

### Provenance-chain every memory entry

Every fact in persistent memory needs an answer to: who said this, when, from what source, at what confidence? Store provenance metadata alongside every embedding. Before acting on a retrieved memory, the agent should be able to answer: "I retrieved this from user memory, written on 2026-08-10, attributed to a summarized email." If it can't, the fact should carry a confidence penalty or trigger explicit re-verification.

### Segment memory namespaces

Separate memory by trust tier: retrieved external content, user-provided facts, agent-generated inferences, third-party skill outputs. Cross-tier contamination is the operational failure mode — an unverified email summary bleeding into agent-generated workflow knowledge. Enforce write-path isolation: external content writes to a sandboxed namespace that cannot influence tool-call permissions or credential stores.

### Treat memory as a versioned cache, not ground truth

Implement memory TTL with explicit expiration. Treat memory as a warm cache that should be periodically re-fetched from authoritative sources, not as compiled knowledge. The agent should re-derive facts from live context where consequential decisions are at stake, not trust a memory entry from a past session whose origin it cannot verify.

### Add a memory integrity gate (cf. S-1189)

Beyond gradual drift detection, monitor for anomalous write patterns: memory entries that the agent itself did not explicitly intend to record, entries that contradict prior confirmed facts, or entries that expand the agent's perceived capabilities (tool access, credential assumptions, workflow permissions) without an corresponding user instruction. These are the operational signatures of stealth injection.

## Evidence

- MemGhost (arxiv 2607.05189, Zhang et al. July 2026): 87.5% E2E success on OpenClaw, 71.4% on Claude Code SDK, cross-architecture transferability across model families.
- CSA AI Safety Initiative research note (July 23, 2026): MemGhost delivered via single crafted email; defense evasion at input, model, and system levels.
- MINJA (prior art, ~95% injection success under idealized conditions) established the baseline; MemGhost advances it with stealth rates that defeat human-editable review.
- CSA classification: attack committed at ingestion, harm materializes at retrieval — same temporal gap as DNS cache poisoning.

## Cross-links

- [S-1189](/stacks/s1189-the-memory-integrity-gate-when-your-agents-memory-starts-lying-to-itself.md) — memory integrity gate (gradual drift detection, different failure mode)
- [S-1086](/stacks/s1086-the-cascading-hallucination-spill-stack-when-a-95-confidence-error-becomes-ground-truth.md) — cascading hallucination spill (how false facts propagate downstream)
- [S-1136](/stacks/s1136-the-context-sanitization-gate-stack-when-your-agent-treats-retrieval-noise-as-ground-truth.md) — context sanitization gate (retrieval-time verification)
- [S-1960](/stacks/S-1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — skills top 10 (skill write-path security, analogous pattern)
