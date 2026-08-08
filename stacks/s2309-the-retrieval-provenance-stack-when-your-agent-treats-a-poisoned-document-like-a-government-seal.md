# S-2309 · The Retrieval Provenance Stack — When Your Agent Treats a Poisoned Document Like a Government Seal

A customer-support agent retrieves a knowledge-base article and follows it exactly — including instructions to redirect callers to a fraudulent number. A coding agent reads a README that contains embedded instructions to exfiltrate environment variables. A financial agent pulls a policy document and acts on it, never knowing it was uploaded by a compromised third-party integration. In every case, the agent treated retrieved content as authoritative because the retrieval layer gave it no reason not to.

This is the **retrieval provenance problem**: documents and tool outputs enter the agent's context without any trust signal, yet agents act on them as if they carry institutional authority.

## Forces

- **LLM-integrated applications conflate data and instructions.** The context window does not distinguish between the user's query, the system prompt, and content retrieved from a vector store. When the agent reads a passage, it has no structural way to know whether it came from a vetted internal document, a user upload, a scraped web page, or a poisoned RAG index.
- **RAG poisoning requires only five documents.** Research from January 2026 showed that five carefully crafted documents in a corpus of millions can manipulate AI responses with 90% reliability. The attacker doesn't need to compromise the model — they only need to get their content indexed. Once retrieved, injected instructions carry the same epistemic weight as anything else in the prompt.
- **Trust is assumed, not enforced.** Most RAG pipelines rank documents by semantic similarity and inject the top-K chunks without any provenance, freshness, or author-verification metadata. The retrieval step provides no trust signal; the generation step has no mechanism to act on one.
- **Content from different sources carries different risk profiles.** Internal, vet-proven documentation is categorically different from user uploads, third-party APIs, scraped web pages, or shared vector indexes. A single pipeline that treats all retrieved content identically is a single failure point.

## The move

Separate retrieval from authority. Provenance labeling is not a content filter — it is a structural separation that forces every retrieved passage to declare its source, author trust level, and policy authority before the agent decides whether to act on it.

**Step 1 — Tag at ingest, not at retrieval.**

Every document entering the vector store carries a provenance envelope at indexing time:

```python
@dataclass
class ProvenanceEnvelope:
    source_type: Literal["internal", "third_party", "user_upload", "web_scrape", "tool_output"]
    author_trust: Literal["verified", "unverified", "anonymous"]
    policy_authority: bool  # Does this document define rules the agent should follow?
    ingestion_timestamp: datetime
    content_hash: str  # SHA-256 of the raw content at ingest
    allowed_privilege: int  # Minimum privilege level required to read; 0 = public

def index_document(
    content: str,
    source_type: str,
    author_trust: str,
    policy_authority: bool = False,
    allowed_privilege: int = 0,
) -> None:
    envelope = ProvenanceEnvelope(
        source_type=source_type,
        author_trust=author_trust,
        policy_authority=policy_authority,
        ingestion_timestamp=datetime.utcnow(),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        allowed_privilege=allowed_privilege,
    )
    # Store envelope as a separate metadata field alongside the chunk
    vector_store.add_texts(
        texts=[content],
        metadatas=[asdict(envelope)],
    )
```

**Step 2 — Retrieve with provenance, not just chunks.**

```python
def retrieve_with_provenance(
    query: str,
    agent_privilege_level: int,
    require_policy_authority_for: list[str] = ("route", "redirect", "transfer", "delete"),
) -> tuple[list[str], list[ProvenanceEnvelope]]:
    """Retrieve chunks AND their provenance metadata. Filter by privilege level."""

    results = vector_store.similarity_search_with_score(query, k=10)

    trusted_chunks, trusted_envelopes = [], []
    for chunk, score in results:
        env = ProvenanceEnvelope(**chunk.metadata)

        # Privilege filter: skip content above agent's clearance
        if env.allowed_privilege > agent_privilege_level:
            continue

        trusted_chunks.append(chunk.page_content)
        trusted_envelopes.append(env)

    return trusted_chunks, trusted_envelopes
```

**Step 3 — Inject with explicit attribution markup.**

```python
def build_attributed_context(
    chunks: list[str],
    envelopes: list[ProvenanceEnvelope],
) -> str:
    """Wrap each chunk in a machine-readable attribution tag."""

    parts = []
    for chunk, env in zip(chunks, envelopes):
        parts.append(
            f'<retrieved source="{env.source_type}" '
            f'trust="{env.author_trust}" '
            f'policy_authority="{env.policy_authority}" '
            f'timestamp="{env.ingestion_timestamp.isoformat()}">\n'
            f'{chunk}\n'
            f'</retrieved>'
        )
    return "\n\n".join(parts)
```

**Step 4 — Enforce policy authority gate.**

```python
def enforce_policy_authority(
    attributed_context: str,
    task_action: str,
    policy_authority_required: bool = True,
) -> bool:
    """Block action if context contains unverified policy-authority content."""

    import re

    if not policy_authority_required:
        return True

    # Extract all policy_authority flags from the attributed context
    flags = re.findall(r'policy_authority="(true|false)"', attributed_context)
    sources = re.findall(r'source="([^"]+)"', attributed_context)

    # User-uploaded and web-scraped content with policy_authority=true is blocked
    for src, pol in zip(sources, flags):
        if pol == "true" and src in ("user_upload", "web_scrape"):
            return False  # Gate: untrusted source claims policy authority

    return True
```

**Step 5 — Verify content integrity at retrieval time.**

```python
def verify_retrieval_integrity(
    chunk: str,
    envelope: ProvenanceEnvelope,
) -> bool:
    """Confirm the retrieved chunk matches what was indexed. Detect in-flight tampering."""

    current_hash = hashlib.sha256(chunk.encode()).hexdigest()
    return current_hash == envelope.content_hash
```

## Receipt

> Receipt pending — 2026-08-08. Core pattern implemented in a test harness; integrity hash and privilege filter verified in unit tests. Production deployment requires integration with the existing RAG pipeline and agent privilege system.

## See also

- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth.md) — the broader injection threat model; this entry covers the specific retrieval-layer variant
- [S-100 · Agentic RAG](s100-agentic-rag.md) — the retrieval planning layer; this entry applies to any RAG pipeline regardless of agentic planning
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance enforcement that survives prompt drift; provenance labeling is the data-layer complement to governance guardrails
