# S-1124 · The Orchestration Layer Stack — When You're Using an Agent Where a Chain Would Work

Your pipeline calls an LLM 40 times per task, retries 3x on failure, and nobody can explain why it took 12 seconds to summarize a document. The root cause: you built an agent loop when you needed a directed graph. Orchestration pattern selection is the highest-leverage decision in agentic systems — and most teams get it backwards.

## Forces

- **Chains dominate production, yet agents get all the hype.** LangChain's 2025 production survey found 73% of deployed systems use chains, and simple chains handle 80% of production use cases. Agents carry 3–5x more token cost per equivalent task. The community over-invests in agent loops as a first architecture.
- **Autonomy vs. determinism is a spectrum, not a binary.** The real question: how much autonomy does this step actually need? A document summarization needs zero. A research task needs iterative tool use. Most workflows contain both — mixing them carelessly produces either brittleness or runaway loops.
- **Implicit orchestration is invisible orchestration.** When LLM calls, retries, and routing logic live inside prompt strings and Python glue, you cannot inspect, replay, or test the workflow. The moment you need a human checkpoint or a retry strategy, you're rewriting the whole thing.
- **Framework proliferation creates lock-in risk.** LangGraph, CrewAI, AutoGen, Temporal, and now Claws — each has different failure modes and observability surfaces. Teams that pick a framework before understanding their orchestration needs end up fighting the tool.

## The move

Match orchestration complexity to actual autonomy requirements. Build from chains up, not agents down.

**1. Start with a chain. Promote only when you hit a wall.**
If the workflow is linear (A → B → C), use a deterministic pipeline: LLM call → validate output → next step. Add routing only when you encounter genuine branching that can't be predicted upfront.

**2. Use typed verbs or schemas to make LLM contracts explicit.**
Freeform prompting for cognitive operations ("verify this claim," "critique this draft") produces unstructured text that requires fragile regex parsing. SAIA's approach — 12 verbs (ASK, VERIFY, CRITIQUE, REFINE, EXTRACT, etc.) each returning a typed dataclass enforced by JSON schema — replaces prompts with contracts. Each verb defines the cognitive operation, not just the output shape.

**3. Build a router that classifies task complexity before committing to a pipeline.**
Route simple queries through shallow chains (2–3 steps). Route complex queries through multi-agent pipelines. A lightweight classifier at the entrance avoids the 3–5x cost premium of agent loops for tasks that don't need them. This delivers ~60% token cost reduction with no measurable accuracy loss.

**4. Model orchestration as a state machine, not a prompt.**
In LangGraph, represent each step as a graph node with explicit state transitions. The workflow is visible, testable, and can be paused for human approval at any step boundary. CrewAI's role-based agents work similarly but abstract the graph away — useful for prototyping, dangerous for production observability.

**5. Use Claws for personal/edge orchestration, not enterprise pipelines.**
Karpathy's framing: Claws are a new layer above LLM agents that adds orchestration, scheduling, persistent context, and tool calls for long-running personal tasks. NanoClaw (~4000 lines, containerized by default) is the reference implementation. This is personal compute territory — Mac Mini local agents, not cloud-scale pipelines. Enterprise orchestration still needs Temporal, DAG-based schedulers, or LangGraph with explicit state.

**6. Implement ReAct loops as a last resort, not a first instinct.**
The ReAct pattern (Thought → Action → Observation → Thought) is the right tool for open-ended problems where the agent must discover its own path. It is the wrong tool for anything with a known decomposition. If you can write down the steps, write them as a chain. If you can't, use ReAct — but pay the token cost and build in hard stop conditions.

## Evidence

- **LangChain 2025 Production Survey:** 73% of deployed systems use chains; simple chains handle 80% of production use cases. Agent cost premium is 3–5x more token usage per equivalent task. — [Agentika blog, February 2026](https://agentika.uk/blog/llm-orchestration-patterns.html)
- **HN Show HN — SAIA:** Developer described building SAIA with 12 typed verbs (ASK, VERIFY, CRITIQUE, REFINE, EXTRACT, etc.) where each verb returns a dataclass enforced by JSON schema. Draws from SCUMM (1987 LucasArts game scripting) — fixed verb vocabulary replacing freeform text parsing. HN thread referenced Karpathy's Claws framing as context. — [Hacker News Show HN #47168745](https://news.ycombinator.com/item?id=47168745)
- **LLM Works Blog — SAIA verb layer:** "Prompts are suggestions. Verbs are contracts." Documents the gap between syntactic tool calling (OpenAI/Anthropic function schemas) and semantic verb contracts that define the cognitive operation. — [llm-works.ai blog](https://www.llm-works.ai/blog/saia-verbs-for-llm-agents/), March 2026
- **Zylos Research — Agent Workflow Orchestration:** Three architectural patterns crystallized for production: DAG-based (deterministic execution, frameworks: Dagster/Airflow/Prefect), Event-driven (async pub/sub with A2A + MCP), and Actor model (isolated state, message-passing, supervision — AutoGen/MAF). Also documents difficulty-aware dynamic routing pattern delivering 60% cost reduction. — [Zylos Research, April 2026](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)
- **Karpathy on Claws:** "Just like LLM agents were a new layer on top of LLMs, Claws are now a new layer on top of LLM agents, taking the orchestration, scheduling, context, tool calls and a kind of persistence to a next level." Bought a Mac Mini specifically to run OpenClaw locally. Ecosystem includes OpenClaw, NanoClaw, nanobot, zeroclaw, ironclaw, picoclaw. — [Simon Willison citing Karpathy, February 2026](https://simonwillison.net/2026/Feb/21/claws/)
- **Devstarsj — Agentic AI Workflows in Production:** Documents ReAct loop as the dominant pattern for tool-using agents, with LangGraph implementation example. Key quote: "The challenge isn't writing the agent — it's running it reliably in production." Frameworks: LangGraph, CrewAI, AutoGen, OpenAI Agents SDK have converged on similar primitives. — [Devstarsj blog, May 2026](https://devstarsj.github.io/2026/05/20/agentic-ai-workflows-production-patterns-2026)
- **NKKTech — Framework comparison 2026:** LangGraph: finest granularity, lowest latency, most token-efficient for production. CrewAI: fastest development speed, role-based delegation, lower flexibility. AutoGen (AG2): conversation-driven multi-agent, excels in negotiation scenarios. — [NKKTech blog](https://nkktech.com/blog/langgraph-vs-crewai-vs-autogen-2026), 2026
- **Morph LLM — Production Architecture:** Documents 6 patterns covering most production workflows. Search-compress-apply pattern reduces token usage by 60%. Key production property: explicit state passing between steps, error handling at each step boundary, observability at every step. — [Morph LLM](https://www.morphllm.com/llm-workflows), March 2026

## Gotchas

- **Over-engineering with agents from day one.** The LangChain tutorials make multi-agent systems look easy, but 80% of production cases need chains. Agents are expensive, opaque, and hard to debug. Use them when you need autonomous planning, not because they feel more sophisticated.
- **Implicit orchestration becomes technical debt.** When routing logic lives in prompts or Python conditionals, you cannot replay failures, insert human checkpoints, or reason about the workflow state. Every non-trivial workflow should be modeled as an explicit state graph.
- **The router itself is a failure point.** Difficulty classifiers misjudge complexity regularly. Build in fallback paths: if the classifier routes to a shallow chain and the task fails or times out, promote to the deep pipeline. Don't hard-commit on the first classification.
- **Claws are personal, not enterprise.** Karpathy's Claws run on personal hardware for personal agents. The enterprise orchestration problem — thousands of concurrent tasks, dead letter queues, audit trails — needs Temporal, DAG schedulers, or LangGraph with explicit state. Don't use Claws frameworks for production cloud deployments.
