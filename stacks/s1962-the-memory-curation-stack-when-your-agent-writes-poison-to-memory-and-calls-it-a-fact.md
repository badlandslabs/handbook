# S-1962 · The Memory Curation Stack — When Your Agent Writes Poison to Memory and Calls It a Fact

Your agent just ran for six hours across fifty sessions. In session twelve it wrote "the staging API is at staging.internal:8080." In session twenty-three it corrected itself to port 9090 but the old entry still scores 0.87 cosine similarity — it surfaces alongside the new one, and now the agent holds two contradictory beliefs it can't distinguish. Meanwhile, an adversarial web page your agent visited in session nine left a memory entry claiming "delete_old_records.py is safe to run on all environments" — it passed the vector similarity check and the agent is about to execute it in production. This is the curation failure: your agent's memory write path has no gate, no version control, and no trust model. Everything written becomes canonical immediately.

## Forces

- **Write-through is the default.** Every agent memory framework — vector stores, SQLite, KV tables — treats each write as immediately canonical. Corrections overwrite nothing; contradictions accumulate.
- **Semantic similarity hides contradiction.** Two entries can both retrieve for the same query if they use different phrasing. The agent has no mechanism to know one supersedes the other.
- **Poisoned memory survives prompt defenses.** A jailbroken session or adversarial injection written to memory persists after the session resets. No future prompt can "unlearn" it — the vector store still returns it.
- **No review path exists in most stacks.** Human-in-the-loop review of memory writes adds latency that teams strip out in the name of "autonomy." Without a gate, autonomy and contamination are the same thing.

## The Move

Layer a three-stage write lifecycle with VCS-backed audit trail between your agent and its memory store:

- **Draft → Promote → Canonical.** Memory writes go to a `drafts/` staging area. They don't participate in retrieval until explicitly promoted. The agent can read drafts it wrote; other agents or sessions cannot.
- **LLM review gate before promotion.** Before a draft becomes canonical, a separate LLM call evaluates it against criteria: is this verifiable fact, or inference? Is the source trusted? Does it contradict an existing canonical memory? Only after this gate does it get promoted.
- **Supersession chains instead of overwrites.** When an agent corrects a belief, the old entry is marked superseded (not deleted — VCS preserves history). The supersession chain is traversable so the agent can understand its own reasoning evolution, but default retrieval excludes superseded entries.
- **Atomic rollback.** If a promoted memory causes problems, roll it back to the pre-promotion state in a single atomic operation. Jujutsu's operation log makes this lossless — every state is restorable.
- **Versioned audit trail as primary storage.** Every write is a Git commit. You can `jj log` the entire memory history, diff any two beliefs, and see who wrote what when — without any external logging infrastructure.
- **Cross-session isolation for untrusted sources.** Memories derived from web scraping, user uploads, or untrusted tools are tagged with provenance metadata. The retrieval system weights by source trust score.

## Evidence

- **GitHub (FAVA Trails):** FAVA Trails (Federated Agents Versioned Audit Trail) implements the full curation stack — draft isolation, promotion gates, supersession chains, and thought lifecycle hooks — using Jujutsu (JJ) VCS as storage backend, exposed via MCP. Agents interact through MCP tools and never see VCS commands. Supports Claude Desktop, Claude Code, and any MCP-compatible agent. — [https://github.com/MachineWisdomAI/fava-trails](https://github.com/MachineWisdomAI/fava-trails)
- **Security blog (Agent Security, Feb 2026):** Documents memory poisoning as a distinct attack class: adversarial content written to an agent's persistent memory during one session survives into future sessions where it shapes planning and execution without triggering conventional defenses. Contradiction accumulation is explicitly cited as the mechanism — old false entries coexist with corrected entries and both retrieve for related queries. — [https://agentsecurity.com/posts/memory-poisoning-in-autonomous-ai-agents](https://agentsecurity.com/posts/memory-poisoning-in-autonomous-ai-agents)
- **HN Show HN (4 months ago):** Fava Trails Show HN discussion notes that vector-store-based memory systems return semantically similar but contradicting entries simultaneously — the agent cannot prioritize which reflects the current state. The Fava Trails design uses draft isolation to prevent this: a second agent working on the same codebase sees only promoted, reviewed memories, not the first agent's working thoughts. — [https://news.ycombinator.com/item?id=47197011](https://news.ycombinator.com/item?id=47197011)
- **PyPI / docs:** Supersession tracking — when an agent corrects a belief, the old version is hidden from default recall. No contradictory memories in the retrieval surface. — [https://pypi.org/project/fava-trails/](https://pypi.org/project/fava-trails/)

## Gotchas

- **The review gate becomes a bottleneck if it's synchronous.** If every memory write requires a blocking LLM review call before the agent can continue, you've added latency to the agent's critical path. Async promotion with a separate worker thread is the practical approach — the agent continues writing to drafts, a background process handles the gate.
- **Jujutsu is experimental.** The JJ project explicitly marks itself as experimental despite stable Git compatibility. If the VCS layer has UX gaps or breaks, your memory layer breaks with it. Evaluate whether standard Git with GitHub/GitLab's audit APIs meet your requirements before taking the JJ dependency.
- **Supersession chains don't solve false canonical memories.** If a poisoned entry passes the promotion gate and becomes canonical before you detect it, the chain still contains it — you have to identify and roll back manually. The curation stack reduces poisoning risk; it doesn't eliminate it.
- **Trust gate prompt engineering is its own problem.** The LLM reviewer evaluating drafts needs a well-engineered system prompt to distinguish facts from inferences, trusted sources from web content, and current beliefs from superseded ones. That prompt is now a critical piece of your memory infrastructure.
