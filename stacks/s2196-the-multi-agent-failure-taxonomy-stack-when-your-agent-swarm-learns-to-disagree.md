# S-2196 · The Multi-Agent Failure Taxonomy Stack — When Your Agent Swarm Learns to Disagree

Your multi-agent pipeline worked great in demos. Three agents, clean handoffs, parallel threads. Then it hit production and started failing 41–87% of the time — not because the models degraded, but because the agents started disagreeing about who owns what, what the goal means, and when to stop. This is the coordination failure problem: the most common reason agentic systems collapse in production, and the one teams rarely test for until they're already on fire.

## Forces

- **The specification ambiguity problem.** When you give two agents the same task description, they can interpret "finish the report" very differently. Role ambiguity is the single largest failure category — 41.77% of production failures trace back to unclear or drifting specifications
- **The coordination overhead problem.** More agents means more handoffs, more shared state, more opportunities for one agent to undo another's work. The coordination cost grows superlinearly with agent count
- **The verification gap problem.** Agents often skip checking each other's output. A code-writing agent and a code-reviewing agent running in parallel with no cross-verification will occasionally ship both good and bad code without anyone noticing
- **The hero agent problem.** One agent becomes the bottleneck because it "knows best," collapsing the multi-agent design back into a single-agent system with extra steps
- **The unbounded spawn problem.** Without hard limits, orchestration patterns that dynamically decompose tasks can spawn an ever-growing tree of sub-agents until the system exhausts context or budget

## The Move

Apply the MAST failure taxonomy — validated at NeurIPS 2025 across 1,600+ execution traces — to diagnose and fix multi-agent coordination failures before they hit production.

**1. Tighten specifications first (41.77% of failures live here).** Every agent role needs a written, unambiguous spec: explicit input/output contracts, hard stop conditions, and a definition of what "done" means. Use structured prompts with role headers, constraint lists, and refusal conditions — not prose descriptions.

**2. Implement structured handoffs, not message passing.** The difference matters: a handoff transfers conversation ownership to the next agent; a message pass just adds to a shared thread. OpenAI's Agents SDK and Anthropic's approach both make this distinction explicit. Prefer handoffs when ownership transfer is needed; use shared context when agents need to react to rather than replace each other.

**3. Add a verification loop at every handoff boundary.** The most reliable multi-agent patterns — supervisor-worker, orchestrator-workers — both include a synthesis step where the parent agent reviews child outputs before proceeding. Don't let agents skip this step to save tokens.

**4. Treat agent count as a cost, not a feature.** Research on code LLMs shows that no single model dominates across all task categories — which is the original argument for multi-agent. But the marginal value of each additional agent drops sharply past 3–4 specialists. Start with the minimum viable agent count and add only when you have a specific failure mode to address.

**5. Set hard resource limits at the orchestration layer.** Max iterations, token budgets, and recursion depth limits prevent unbounded spawn failures. These belong in the orchestrator, not in individual agent prompts.

## Evidence

- **Research (NeurIPS 2025, MAST taxonomy):** Multi-agent LLM systems fail at 41–86.7% rates in production. The MAST taxonomy validated across 1,600+ execution traces maps 14 failure modes to three root categories: specification ambiguity (41.77%), coordination breakdowns (37.2%), and verification gaps (21.03%). Fixing specifications and coordination protocols delivers the highest reliability ROI. — [augmentcode.com](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them)
- **Enterprise case study (DoorDash):** DoorDash's Ask DoorDash agentic ordering system scaled evaluation from ~1 employee feedback per day to 2,000 auto-graded sessions daily by combining rubric-based evaluation, transcript builders from OpenTelemetry traces, and calibrated LLM judges. Drove an 8-point quality improvement and 50% error rate reduction. — [doordash.com](https://careersatdoordash.com/blog/building-ask-doordash-part-three-evaluation/)
- **Research (MIT IBM / NeurIPS 2025):** Code LLMs excel at different optimization categories — no single model dominates others. The LessonL framework uses a team of agents that learn complementary strengths from each other's successes and failures without requiring a priori knowledge of which model is best at what. — [arxiv.org/abs/2505.23946](https://arxiv.org/abs/2505.23946)
- **Pattern catalog (agentpatternscatalog.org):** Field-tested patterns explicitly name the failure modes — infinite debate, hero agent, unbounded subagent spawn — so teams can recognize them and walk away from designs that will collapse. — [agentpatternscatalog.org](https://www.agentpatternscatalog.org/multi-agent-patterns/)
- **Company guidance (Anthropic):** Over a year of working with dozens of teams building LLM agents across industries showed the most successful implementations weren't using complex frameworks. The key recommendation: keep the agent loop simple, add tools sparingly, and use a supervisor pattern for multi-agent coordination. — [anthropic.com](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Adding more agents to fix a broken coordination design makes it worse.** Teams facing high failure rates often add a "coordinator" or "verifier" agent. Without fixing the underlying spec ambiguity, this just adds another failure surface
- **Shared context sounds good but creates race conditions.** When two agents can read/write the same memory store, order of operations matters in ways that are hard to debug. Use ownership-based context (one agent writes, others read) rather than shared read-write state
- **The "it worked in testing" illusion.** Single-agent tests pass at much higher rates because there's no coordination surface to fail. Multi-agent reliability only shows up under realistic concurrent load with adversarial edge cases
- **MCP adoption is surging (10,000+ servers, 97M monthly SDK downloads as of 2025) but coordination protocols are still fragmented.** Different frameworks implement handoffs, tool negotiation, and context passing differently. Choosing a framework with a standard protocol matters more as agent counts grow
