# S-725 · Multi-Agent Coordination: The Patterns That Actually Hold Up

[Multiple agents in production fail for the same reason single agents do — unstructured communication and no recovery strategy. The solution isn't more capable models; it's smarter handoff design, implicit coordination through shared state, and hard circuit breakers on token spend. The coordination pattern matters more than the framework choice.]

## Forces

- **Direct agent-to-agent messaging is a cost and latency trap.** Every explicit handoff multiplies token usage (5× overhead reported for CrewAI multi-agent vs single-agent) and creates serialization bottlenecks where agents wait idle for each other.
- **Pre-defined DAGs collapse under ambiguous goals.** Teams that script every handoff end up with a fragile chain, not a multi-agent system. Real multi-agent tasks require agents to decompose and route dynamically.
- **Hallucination propagates downstream.** One bad output from a subagent poisons every agent that consumes it, with no natural recovery boundary unless you've explicitly designed one.
- **The babysitting problem is real.** Autonomous multi-agent setups require constant human monitoring or they compound errors indefinitely. Teams need to choose between autonomy and safety — most settle for constrained autonomy.

## The move

**Match coordination topology to task structure, not to model sophistication.**

### 1. Use stigmergy for stateless parallel work
Stigmergy — indirect coordination through shared environment (a shared memory store, a message board, a results table) — eliminates serialization. Agents write outputs to a shared space and move on; other agents read and react independently. One team on Reddit reported **~80% token reduction** compared to direct agent messaging by replacing synchronous handoffs with a shared results store and polling.

**When to use:** Parallel research, web scraping, independent data extraction, triage where agents don't need each other's immediate output.

### 2. Reserve supervisor/hierarchical for high-stakes synthesis
A lead agent decomposes the task, spawns specialist subagents, and synthesizes results. Anthropic's own Research system uses this: Opus 4 as the lead planner, Sonnet 4 subagents for parallel web searches, then Opus 4 again for synthesis. They measured **+90% quality improvement** vs single-agent on complex research queries — at the cost of higher latency and token volume.

**When to use:** Research synthesis, strategic planning, complex document review, anything where a senior agent needs to validate and integrate specialist work.

### 3. Build validator gates, not trust chains
Every agent output that feeds a downstream agent needs a validation checkpoint — not a human review, but a lightweight critic model or a structured schema check. This breaks hallucination propagation by adding a rejection boundary. Zylos Research recommends a **token budget + critic loop** pattern: if the evaluator rejects the output after N iterations, compress context and retry, or escalate.

**When to use:** Always, as a baseline. The cost of a validator is far lower than a hallucinated output reaching a customer or triggering a downstream action.

### 4. Add circuit breakers on every agent's token budget
Runaway agent loops have cost teams from **$15 in 10 minutes to $47,000 over 11 days** (Zylos Research). The fix is simple: every agent invocation gets an explicit token budget and max-iteration count. If exceeded, the agent returns a safe fallback — not an error, a fallback.

**When to use:** Any production agent, immediately. This is not optional.

### 5. Prefer peer coordination for loosely-coupled equal agents
When agents share a common goal but have independent capabilities, a router or classifier agent (or a simple rules engine) decides which specialist handles each sub-task. This is the helpdesk pattern: a triage agent routes incoming requests to specialized sub-agents. No agent waits for another; the router is the only serialization point.

**When to use:** Customer service, internal tooling, any queue-based task distribution.

## Evidence

- **Engineering blog:** Anthropic's production multi-agent system uses a lead agent + parallel subagent topology, with Opus 4 lead and Sonnet 4 subagents — measured +90% quality improvement on complex research tasks. — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system) (June 2025)
- **Community post:** A practitioner using indirect stigmergy coordination (shared memory store instead of direct messaging) achieved ~80% token reduction vs direct agent communication — [Reddit r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1qv3o3o/p_stigmergy_pattern_for_multiagent_llm/) (4 months ago)
- **Research:** Production multi-agent token overhead is significant: CrewAI multi-agent runs consume 5× tokens vs a single-agent equivalent. Enterprise teams average $85,521/month in AI ops costs. Runaway loops have cost teams $15 in 10 minutes to $47,000 over 11 days. — [Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/) (May 2026)
- **Framework analysis:** LangGraph leads enterprise production deployments by footprint; CrewAI has the fastest prototype-to-demo ergonomics; AutoGen/AG2 leads academic/research adoption. Framework choice is less consequential than model selection, evaluation infrastructure, and checkpoint design. — [Presenc AI Research](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026) (May 2026)

## Gotchas

- **Calling it "multi-agent" doesn't make it autonomous.** Most frameworks implement pre-scripted handoffs — the agents don't self-organize. True autonomous coordination requires the system to define task decomposition dynamically, which most teams don't actually need.
- **Multi-agent ≠ better quality.** Splitting work across agents adds overhead. If a single model with two tools handles the task, use that instead. Splitting only pays off when the sub-tasks genuinely require different context windows or different capability levels.
- **Parallelism sounds free but isn't.** Parallel subagent execution requires each to have its own context window loaded, multiplying input token costs even when latency is lower. Budget for this.
- **Human-in-the-loop placement is a design decision, not an afterthought.** Determine at which point human approval is required before building the handoff graph — retrofitting checkpoints into an existing multi-agent system is painful.
