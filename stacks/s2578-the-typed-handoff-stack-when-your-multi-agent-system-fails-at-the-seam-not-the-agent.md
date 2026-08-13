# S-2578 · The Typed Handoff Stack — When Your Multi-Agent System Fails at the Seam, Not the Agent

Your three agents each work perfectly in isolation. Put together, the system quietly breaks. A statistic gets passed from the researcher to the writer to the reviewer — each agent receives a subtly different context, each makes a locally correct decision, and the wrong number ships to production. The agents aren't the problem. The boundaries between them are. The handoff is where production multi-agent systems die.

## Forces

- **Context dump collapse:** Passing full conversation history and all tool results to the next agent creates the "Lost in the Middle" effect — models show U-shaped retrieval accuracy where information buried in the middle of long contexts becomes significantly harder to access. By the time the receiving agent processes a full dump, critical signal has already been diluted.
- **Context drought collapse:** Passing too little — just the final answer — strips the next agent of the reasoning trail, the failed attempts, and the partial insights that would let it build on the work rather than restart it. The agent then redundantly re-derives what the previous one already figured out.
- **Bounce amplification:** Without a hard budget on how many times work can ping-pong between agents, failures compound. Coordination overhead scales quadratically: ~200ms for 2 agents, 4+ seconds for 8+ agents. More bounces means more surface area for error propagation.
- **Implicit ownership:** When handoffs are just "pass the conversation along," no agent holds clear ownership of the task outcome. Specification failures account for ~42% of multi-agent failures; coordination breakdowns for ~37% — most of these originate in unclear ownership at the seam.

## The Move

Engineer the handoff as a first-class construct, not an implicit conversation pass. Three non-negotiable elements:

- **Single task owner.** The sending agent transfers full ownership, not a partial recommendation. The recipient is responsible for completion, not continuation. In LangGraph, model this as a typed state transition with a named destination node — not a tool call that returns text for another agent to interpret.
- **Typed handoff payload.** Define a schema for what crosses the seam. At minimum: the specific task being transferred, the critical findings (not all findings), the confidence level, and what remains to be done. Anthropic's production research system uses five explicit fields: agent role, summary of completed work, summary of open questions, specific next-step request, and relevance flag for prior context.
- **Hard bounce budget.** Set a maximum handoff count before escalation to a supervisor or human. Track this in graph state. When the budget is exhausted, the system must either commit to the current result or surface the failure rather than continuing to bounce.
- **Curated context injection.** Don't dump all prior work; selectively inject only what is directly relevant to the next agent's specific task. Use a relevance filter — either programmatic (keyword/entity match) or LLM-based (ask the sending agent: "what does the next agent absolutely need to know?"). LangGraph's handoff tools support passing a curated `context` field alongside the destination.
- **Result schema on entry.** The receiving agent should receive a structured input it can validate against, not free-form text. Define what a successful completion looks like before the work starts, not after.

## Evidence

- **Anthropic engineering blog (Jun 2025):** Their multi-agent research system uses five explicit fields in every inter-agent handoff: agent role, summary of completed work, summary of open questions, specific next-step request, and a flag indicating whether the receiving agent should re-examine prior context. Adding full production tracing let them diagnose why agents failed and fix issues systematically at the seam level, not the model level. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Tian Pan / tianpan.co (Nov 2025):** Documents two canonical handoff failure modes — the context dump (causes "Lost in the Middle" degradation) and the context drought (causes re-derivation loops). Cites production failure rates of 41%–86.7% without formal orchestration. Proposes the single-task-owner principle and typed handoff payload as the corrective. — [URL](https://tianpan.co/blog/2025-11-02-multi-agent-handoffs-reliable-coordination)
- **Galileo AI blog (Aug 2026):** Reports that orchestration reduces failure rates by 3.2x compared to unorchestrated multi-agent systems. Coordination overhead scales quadratically with agent count (200ms at 2 agents → 4+ seconds at 8+). Guardrails at handoff seams reduce incident response costs by 60%. — [URL](https://galileo.ai/blog/multi-agent-ai-failures-prevention)
- **arXiv:2507.17852 (Jul 2025):** Production implementation of "Tippy," a five-agent system for drug discovery lab automation. Uses OpenAI Agents SDK with MCP for tool access. Explicitly names each agent's domain (Molecule, Lab, Analysis, Report), defines the supervisor's routing authority, and uses structured tool schemas to enforce what information can cross agent boundaries. — [URL](https://arxiv.org/pdf/2507.17852)
- **HN "Ask HN: How are you orchestrating multi-agent AI workflows in production?":** Practitioners reporting production deployments show a split between full custom abstractions (Node.js + Express + V8 isolates + MongoDB) and LangGraph/CrewAI. Several contributors explicitly cited handoff reliability as the reason they rolled their own: "there's absolutely 0 framework out there that's good enough for serious work" without explicit schema enforcement. — [URL](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **Handoff ≠ tool call.** Passing context via a tool that returns text for another agent to parse is not a handoff — it's a prompt injection surface. The next agent should receive structured state, not interpreted text.
- **LangGraph handoff tool loops.** LangGraph's built-in handoff tool can route back to the starting agent even when the destination is a different node (GitHub issue #6064, open as of 2026). If using LangGraph's `create_handoff_tool()`, validate the routing graph explicitly in tests before relying on it for critical paths.
- **Context amnesia at bounce N.** The more times work bounces, the more each agent's context diverges from the original task. After 3–4 bounces, no agent may hold the full original intent. Log the task origin and pass it explicitly in the handoff payload, not just in the conversation history.
- **Typed payload ≠ rigid schema.** The handoff payload should have required fields (task, owner, confidence) and optional fields (partial findings, failed attempts). Forcing every handoff to pass a full structured object adds ceremony without value. Let the schema flex with the task complexity.
