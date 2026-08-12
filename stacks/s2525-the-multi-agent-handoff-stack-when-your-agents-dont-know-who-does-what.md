# S-2525 · The Multi-Agent Handoff Stack — When Your Agents Don't Know Who Does What

You need three specialized agents — researcher, writer, reviewer — to produce a report. The researcher finishes and the system goes quiet. Nobody told the writer the research was ready. Nobody told the reviewer to stand by. The agents exist; the coordination doesn't. This is the handoff failure: the gap between "multiple agents" and "working together." The move is treating handoffs as infrastructure — with explicit protocols, context contracts, and failure paths — not as implicit LLM intuition.

## Forces

- **Communication channels scale quadratically.** A peer-to-peer mesh of 10 agents has 45 potential communication channels. A supervisor/worker topology has 10. More channels means more failure points and exponentially harder debugging. — [RockB, Multi-Agent System Design Guide 2026](https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026)
- **Context loss at handoff is the default.** When Agent A passes work to Agent B, it passes what it *thinks* matters. If the handoff contract isn't explicit, Agent B re-asks questions the user already answered, or proceeds on partial context it can't recognize as partial.
- **"Supervisor/worker" is dominant in production, not peer-to-peer.** 62% of organizations using multi-agent systems in production use supervisor/worker topology. — [TrueFoundry, 2026](https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026)
- **AutoGen is effectively dead.** Microsoft moved to the Agent Framework (MAF); AutoGen 0.4.x entered maintenance. LangGraph has the strongest production track record among active frameworks despite fewer GitHub stars than CrewAI. — [ODSEA, May 2026](https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production)

## The move

**Build handoffs as explicit protocol, not LLM intuition.**

- **Define handoff triggers in advance.** The supervisor decides *when* to hand off — not the worker. Pre-define routing rules: "if topic is X → Researcher; if topic is Y → Analyst." This prevents agents from deadlocking on who should act.
- **Package handoff context as a structured object.** Pass `{task, intent, prior_output, gaps_identified, constraints}` — not a raw transcript. Context objects should be compressed when they exceed a defined size threshold. — [Agentbrisk, Handoff Patterns 2026](https://agentbrisk.com/blog/agent-handoff-patterns-2026/)
- **Log every handoff with a step count.** Every dispatch, decision, and result gets a timestamp and input/output hash. Without this, debugging a 30-step multi-agent pipeline means forensic archaeology. — [Lines & Circles, Orchestration 2026](https://linesncircles.com/Blog/Enterprise/AI_Agent_Orchestration_2026)
- **Build a fallback for every agent.** If the dispatched agent's API call fails, the pipeline must know what happens — escalation to the supervisor, retry with backoff, or human-in-the-loop alert. "What if this agent goes down?" must have an answer before production.
- **Choose supervisor/worker for reliability, peer-to-peer for flexibility.** Supervisor/worker scales to more agents with fewer failure channels. Peer-to-peer excels when agents need to negotiate outcomes dynamically — but comes with O(N²) observability costs.
- **Test the pipeline end-to-end on real inputs, including edge cases.** A 3-agent pipeline that works on the happy path will break on the first ambiguous input in production. — [Agentbrisk, Handoff Patterns 2026](https://agentbrisk.com/blog/agent-handoff-patterns-2026/)

## Evidence

- **LangChain State of Agent Engineering 2026:** 57.3% of organizations now have agents in production (up from 51% a year prior). 1,300+ practitioners surveyed. Quality is the #1 blocker at 32%, latency at 20%. — [LangChain, April 2026](https://www.langchain.com/state-of-agent-engineering)
- **Gartner:** 1,445% surge in multi-agent inquiries from Q1 2024 to Q2 2025. 80% of enterprise applications embed at least one AI agent as of Q1 2026, up from 33% in 2024. — [RockB citing Gartner, 2026](https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026)
- **ODSEA production comparison:** LangGraph (33,400 stars, active) has the strongest production record. AutoGen (58,500 stars) entered maintenance mode. Framework choice affects reliability more than feature count. — [ODSEA, May 2026](https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production)

## Gotchas

- **Don't let agents decide their own handoffs without constraints.** Left to the LLM, agents will route work to the wrong specialist or create circular dependencies. Supervisor-level routing rules prevent this.
- **Don't pass raw conversation history as context.** It's full of repair turns, clarifications, and aborted attempts. Package intent and key outputs only, or your next agent wastes tokens re-parsing noise.
- **Don't skip observability because "it's just one more agent."** Multi-agent failure cascades are invisible without trace logs. LangSmith, Helicone, or equivalent is not optional at 3+ agents.
