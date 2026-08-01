# S-1951 · The Compound Failure Stack — When Adding Agents Makes Your System Less Reliable

You added a second agent to share the workload. Error rate dropped from 8% to 14%. You added a third to specialize. The system started hallucinating results the first agent never produced. The more agents you added, the worse it got — and nobody on the team could explain why.

This is not a model problem. This is arithmetic: compound failure is the default outcome of multi-agent architecture, and most teams discover it the hard way.

## Forces

- **Per-step reliability multiplies, not adds.** A 10-step workflow at 90% per-step reliability succeeds 34.9% of the time. Add one agent per step and every handoff is a new failure point.
- **Single agents beat multi-agent on most tasks.** Princeton NLP benchmarked single vs. multi-agent systems: a single agent matched or outperformed multi-agent on 64% of tasks, at roughly half the cost.
- **More agents means more token duplication.** CAMEL 86%, MetaGPT 72%, AgentVerse 53% — the same context re-encoded across agents burns budget and introduces inconsistency.
- **Coordination overhead compounds.** Every peer-to-peer call is a potential infinite loop, a contradictory state mutation, or an untraceable decision.
- **40% of multi-agent pilots fail within six months** of production deployment — not because multi-agent is broken, but because teams pick it without understanding how it breaks.

## The Move

The move: treat agent count as a cost, not a feature. Split only when the reliability math favors it, not when the architecture looks elegant.

- **Start with one agent.** Run it in production long enough to see its actual failure modes. Split only after you have real data, not benchmark intuition.
- **Split on failure mode boundaries, not task types.** If one agent handles N steps and fails at step 7 under specific conditions, extract steps 1–6 into a separate agent that never reaches those conditions. Don't split because "there are three task categories."
- **Use typed worker returns, never raw LLM text.** Workers return structured JSON or a typed object. The supervisor parses it or rejects it. Raw text between agents is a silent hallucination vector.
- **Implement per-worker timeouts and hard escalation.** A stuck worker should not stall the whole graph. Timeout → retry once → escalate to supervisor → log the failure. Never let one worker block the pipeline indefinitely.
- **Log supervisor reasoning, not just outcomes.** When something breaks three weeks later, the only thing that saves you is the supervisor's trace: why did it pick that worker, what did it expect, what did it get?
- **Budget cost at the supervisor level.** Track tokens per task. Hard-stop if a single task exceeds 10× median spend. Multi-agent token costs are unpredictable; cost guards are not optional.
- **Count coordination as a reliability tax.** Every agent-to-agent call adds latency, a failure mode, and a logging gap. If the task can be done by one agent with a longer context window, it probably should be.

## Evidence

- **Survey:** LangChain's State of Agent Engineering 2026 (1,300+ respondents) found quality is the #1 production barrier at 32%, and 57% of respondents have agents in production — but the compound failure math means most multi-agent systems underperform their single-agent baselines in real conditions.
  — [langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)
- **Research:** Princeton NLP benchmark results: single agents matched or outperformed multi-agent systems on 64% of tasks with equivalent tools and context, at roughly half the token cost. The finding directly challenges the assumption that more agents equals better results.
  — [beam.ai](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Real-world numbers:** An e-commerce support system using supervisor-worker pattern (one supervisor, three specialists) achieved 62% fully auto-resolved tickets, zero unauthorized refunds, 3.2s P50 response time, and median 5.1 supervisor iterations per ticket — 90 days post-launch. Key: supervisor owned the plan, workers returned typed structures, cost guards enforced at supervisor level.
  — [hireagentic.dev](https://hireagentic.dev/blog/multi-agent-swarm-pattern)

## Gotchas

- **"We'll add more agents later" is the wrong starting point.** Teams default to multi-agent because it looks sophisticated. The correct question is: "what failure mode requires a separate agent, and does the reliability math favor splitting?"
- **Free-for-all agent networks are production-unusable.** When every agent can call every other agent, infinite loops, contradictory mutations, and untraceable decisions emerge predictably. A supervisor that owns planning and routes all delegation is the minimum viable production topology.
- **Token duplication is invisible until you check the bill.** CAMEL (86%), MetaGPT (72%), and AgentVerse (53%) all re-encode shared context across agents. In production, this translates to cost overruns that don't show up in prototype budgets.
- **Eval suites lie about compound failure.** A passing eval suite tests each agent in isolation. The failure modes you need to catch emerge at handoff boundaries — supervisor → worker, worker → worker — and those are the edges most evals don't cover.
