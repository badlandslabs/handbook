# S-2359 · The Inter-Agent Trust Propagation Stack — When Your Security Boundary Is the Agent You Trust

You built your multi-agent pipeline carefully: a planner agent, a research agent, a writing agent, a reviewer. You gave each one scoped credentials. You enforced least privilege on the tools. You thought the attack surface was the tools and the external data sources. What you missed: the trust relationship between your own agents. An attacker doesn't need to inject your planner agent directly — they inject the *research agent's output*, which your pipeline already feeds directly into the planner's context. Once one agent accepts adversarial content, modern pipelines propagate it as trusted input to every downstream agent. The vulnerability isn't a model weakness. It's an architectural assumption baked into every pipeline that chains agents without boundary verification. This is the inter-agent trust propagation attack surface.

## Forces

- **Your pipeline treats agent output as trusted by design.** Unlike tool calls (where output comes from external code with schema validation), agent-to-agent handoffs pass natural language — the format LLMs are most fluent at interpreting as instruction. The pipeline's architecture creates a channel where one agent's output becomes another agent's implicit directive.

- **Attack surface scales with pipeline depth, not agent capability.** Research on adversarial attacks in multi-agent LLM pipelines (Bappy et al., IEEE GLOBECOM 2026, arXiv:2608.00718) shows attack success aligns with pipeline structure rather than backbone model choice. A 5-agent pipeline has 10 inter-agent boundaries, each an injection point, and the attack compounds at every hop. Single-agent systems don't have this attack surface at all.

- **The Trust–Vulnerability Paradox (TVP).** IEEE research (Xu et al., TCSS 2026) formally describes the TVP: increasing inter-agent trust to improve coordination *simultaneously* amplifies risks of over-exposure and authorization drift. The mechanisms that make agents cooperate well are the same mechanisms that make adversarial content propagate efficiently. Reducing trust breaks the pipeline; increasing trust widens the attack surface.

- **Pipelines embed implicit trust assumptions that are not adversarially robust.** The Bappy paper identifies three unverifiable trust assumptions in multi-agent pipelines: (1) agents assume received content is non-adversarial, (2) agents assume other agents are operating within authorized parameters, and (3) agents assume inter-agent communication channels are integrity-protected. All three are false in adversarial conditions.

- **Boundary verification is absent from every major agent framework.** LangChain, AutoGen, CrewAI, CrewAI's official documentation, LangGraph — none provide an explicit inter-agent boundary verification primitive. The gap between "tool call with schema validation" and "agent handoff with implicit trust" is where this attack lives.

## The move

### 1. Map every inter-agent trust edge

Every pipeline has a directed graph of agent-to-agent communication. Draw it explicitly. For each edge (A → B), identify: what data crosses it, what trust assumption it encodes, and what happens if B treats adversarial content from A as instruction. Any edge that passes natural language output from one agent's generation into another agent's context is a potential propagation vector.

### 2. Apply content-level boundary verification at every handoff

The missing primitive is boundary verification — explicit validation of data crossing inter-agent boundaries, covering four dimensions:

- **Content integrity** — Is this output structurally what it should be? (type check, schema validation, length bounds)
- **Identity provenance** — Which agent produced this, and was that agent's environment compromised?
- **Intent consistency** — Does this output's apparent goal align with the authorized task scope of the producing agent?
- **State integrity** — Does this output reference only state the producing agent was authorized to access?

In practice: wrap every inter-agent handoff in a lightweight verification layer — a small classifier, rule-based filter, or separate "guardian" LLM call that screens the output before it enters the next agent's context. This is not the same as the downstream agent's own judgment; it is a structural gate that fires *before* the next agent processes the content.

### 3. Honor the TVP with structured trust tiers

The IEEE TVP framework operationalizes trust as a system-level control parameter with two axes: authorization strictness and information disclosure. Design your pipeline with explicit trust tiers:

- **Zero-trust tier** — Agents in this tier receive no output from other agents without verification. All cross-boundary data passes through boundary verification.
- **Low-trust tier** — Agents can accept verified outputs from approved peer agents without per-hop re-verification, but unverified content from new sources is blocked.
- **Trusted tier** — Reserved for agents whose outputs have been verifiably clean through testing; only expand to this tier after establishing a baseline of clean output patterns.

Enforce these tiers structurally, not procedurally. A "trusted tier" agent whose outputs are never verified is a pipeline compromise waiting to propagate.

### 4. Harden the boundary between agents and external data sources

The pipeline's attack surface isn't only inter-agent — it's also the boundary between agents and the external tools, documents, and APIs they call. The Bappy paper identifies external content ingestion as a primary injection vector: an attacker compromises a document or API response that an upstream agent processes, and the poisoned output propagates downstream. Treat every tool call result as a potential injection vector, not just user-provided content. Run the same boundary verification on tool-call outputs that cross into agent context as on inter-agent handoffs.

### 5. Add a verification step at structural convergence points

In any pipeline with fan-in (multiple agents feeding a single downstream agent), the convergence point is the highest-value target. An attacker who can poison any one of the upstream agents gets their content into the single agent that synthesizes everything. Add an explicit verification gate at every fan-in convergence point: a guardian agent or rule-based filter that screens all incoming outputs before the synthesizing agent processes them.

## Receipt

> Verified 2026-08-09 — arXiv:2608.00718 (Bappy et al., IEEE GLOBECOM 2026) provides the empirical and theoretical foundation: attack success aligns with pipeline structure, not model capability; three unverifiable trust assumptions are the root cause. IEEE TCSS 2026 (Xu et al., DOI 10.1109/TCSS.2026.3695070) provides the TVP formal framework. Deduplication confirmed: S-1013 covers benign coordination failures (not adversarial propagation), S-1050 covers tool/MCP server poisoning (not inter-agent trust exploitation). No existing entry covers the structural trust propagation attack mechanism.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — benign coordination failures across agent boundaries
- [S-1050 · The Tool-Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — external MCP server returns malicious content
- [S-1000 · The Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — structural vs. prompt-level security enforcement
