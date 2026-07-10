# S-923 · Five Ways Multi-Agent Systems Coordinate

You need multiple LLM calls to finish a task. You have a choice: chain them in a single agent, or split across agents. If you split, the next question is how they communicate. The answer determines your latency ceiling, failure blast radius, and debuggability.

## Forces

- Multi-agent systems outperform single agents by 35–60% on soft reasoning tasks (Stanford HAI, 2026), but only when the coordination overhead is justified by the task structure.
- Five distinct coordination patterns exist, each emerging from the same distributed systems constraints that shaped microservices: coordination cost, failure isolation, throughput, and observability. Most production systems are hybrids.
- Framework choice (LangGraph, CrewAI, AutoGen) is secondary — the coordination topology is primary. The wrong pattern with the best framework still fails.
- The most common mistake is reaching for multi-agent before establishing that a single agent genuinely can't solve the median input.

## The move

Match the coordination pattern to the task topology. Five patterns cover most real-world cases:

### 1. Orchestrator-Worker (Supervisor)
A central agent decomposes a task and delegates sub-tasks to specialized workers. The orchestrator holds global state; workers are stateless.

- **Use when:** Fan-out over heterogeneous tools, task decomposition is complex, you need a single point of visibility.
- **Shopify's pattern:** Sidekick evolved from flat tool-calling to hierarchical agent groups as they hit 20–50 tool complexity — a single orchestrator couldn't route reliably, so they organized tools into semantic clusters with a supervisor per cluster (Shopify Engineering, Aug 2025).
- **Gotcha:** The orchestrator is a single point of failure. If it hallucinates a routing decision, all sub-agents work on bad inputs.
- **Frameworks:** LangGraph (natural fit — supervisor node routes to worker nodes), CrewAI (built-in hierarchical process with manager agent).

### 2. Sequential Collaboration (Chain)
Agents pass output directly to the next agent in a fixed order. A writer → editor → formatter pipeline is the canonical example.

- **Use when:** Workflow is linear, each step builds on the previous, and the order is fixed by business logic.
- **Covers ~70% of CrewAI deployments** — the framework shines here because the mental model (Roles → Goals → Crews) matches the linear case exactly.
- **Gotcha:** No parallelism. If step 3 can run before step 2, you shouldn't be using a chain.
- **Frameworks:** CrewAI (sequential process), LangGraph (linear edges).

### 3. Parallel Collaboration
Multiple agents work on the same artifact simultaneously — a writer, editor, and fact-checker all annotating a draft — then a synthesis step merges outputs.

- **Use when:** Independent facets of a problem can be explored in parallel; latency matters more than sequential refinement.
- **Gotcha:** Merge conflicts. If two agents modify the same field, you need a reconciliation step. Stateless reducers in LangGraph handle this explicitly.
- **Frameworks:** LangGraph (parallel edges + state reducer), AutoGen v0.4+ (async group chat model handles concurrent agents naturally).

### 4. Supervisor / Router
A lightweight model (or rule) inspects the input and routes to the appropriate agent — no recursive decomposition, just a one-level dispatch.

- **Use when:** Task categories are known and stable; you want different models for different task types (fast/cheap for simple, slow/powerful for complex).
- **Real pattern from JPMorgan deployments:** Triage agent routes incoming requests to specialized sub-agents. LangGraph's conditional edges make this explicit and auditable (Gheware, April 2026).
- **Gotcha:** The routing taxonomy must be maintained. New task types need new routes. Brittle if the router is a single LLM call with no fallback.

### 5. Swarm / Peer-to-Peer
Agents communicate directly with each other, negotiating and handoff-ing work with no central controller. Emergent coordination through message passing.

- **Use when:** Exploration, research gathering, or scenarios where the task graph can't be known in advance.
- **Gotcha:** Debugging is hard. No central trace means you can't replay a failure. Amazon's evaluation framework notes that swarm-like coordination is the hardest to evaluate automatically — they rely on human-in-the-loop (HITL) assessment for inter-agent communication quality.
- **Frameworks:** AutoGen (group chat model is purpose-built for this), OpenAI Swarm (lightweight, narrow suitability — not a full orchestration framework for production).

## The Decision Tree (from Malaka Venugopal Reddy, April 2026)

Before adding a second agent, apply this filter:

1. **Can a single agent solve this for median input?** → Ship that first with evals, revisit.
2. **Where does single-agent fail?** (latency, quality, context overflow, parallelism)
3. **Would multi-agent structurally fix it — or just hide it?** Hallucinations don't disappear with a verifier; they move.
4. **Are you adding agents for workload reasons or aesthetics?**
5. **Is at least one of `{parallelism, specialized model, context isolation, trust boundary}` clearly true?** → If none, stop.

> *"I have killed more multi-agent designs in step 5 than I have approved."*

## Framework Alignment

| Pattern | LangGraph | CrewAI | AutoGen |
|---------|-----------|--------|---------|
| Orchestrator-Worker | ★★★ Best fit | ★★ Built-in manager | ★★ Group chat |
| Sequential Chain | ★★★ Edges | ★★★ Best fit | ★ Usable |
| Parallel Collaboration | ★★★ Reducers | ★★ Parallel tasks | ★★★ Best fit |
| Supervisor/Router | ★★★ Conditional edges | ★ Role-based routing | ★ Flexible |
| Swarm | ★ Manual | ★ Limited | ★★★ Best fit |

Presenc AI's 2026 survey: LangGraph has the largest enterprise production footprint; CrewAI dominates prototype-to-first-deploy; AutoGen leads research/academic multi-agent debate and verification patterns.

## Evidence

- **Engineering blog:** Multi-agent systems outperform single agents by 35–60% on soft reasoning tasks (Stanford HAI Lab, cited by Fungies.io, April 2026) — https://fungies.io/multi-agent-orchestration-frameworks-2026
- **Engineering blog:** Shopify Sidekick hit a tool complexity wall at 20–50 tools; evolved to hierarchical agent groups with semantic tool clustering (Shopify Engineering, August 2025) — https://shopify.engineering/building-production-ready-agentic-systems
- **Engineering blog:** JPMorgan enterprise deployments use supervisor/router pattern with conditional LangGraph edges for auditable routing; LangGraph dominates enterprise Kubernetes deployments in 2026 (Gheware, April 2026) — https://devops.gheware.com/blog/posts/langgraph-multi-agent-orchestration-enterprise-2026.html
- **Primary research:** Five coordination patterns emerge from distributed systems constraints; most production systems are hybrids (gurusup.dev, March 2026) — https://dev.to/jose_gurusup_dev/agent-orchestration-patterns-swarm-vs-mesh-vs-hierarchical-vs-pipeline-b40
- **Research comparison:** Framework mental models: CrewAI = team of specialists, LangGraph = finite-state machine, AutoGen = async group chat (hjLabs.in, 18 months production experience) — https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison
- **Research report:** LangGraph = largest production deployment footprint; CrewAI = best demo-to-prototype; AutoGen = research/academic leader (Presenc AI, May 2026) — https://presenc.ai/research/multi-agent-orchestration-frameworks-2026
- **Primary research:** The 5-step "should this be multi-agent" filter; four production patterns: collaboration, competition, delegation, peer negotiation (Malaka Venugopal Reddy, April 2026) — https://malakavenu.com/articles/multi-agent-orchestration-2026

## Gotchas

- **Orchestrator is a SPOF** — if the central agent makes a bad routing call, all sub-agents work on bad inputs. Add explicit state validation at the orchestrator boundary.
- **Non-determinism compounds** — each LLM call introduces variance; chained agents multiply it. What works at 2-agent scale breaks at 5-agent scale.
- **Framework choice is less important than the coordination topology** — the wrong pattern with LangGraph still fails. Evaluate the topology first.
- **Swarm systems lack central observability** — you can't replay a failure without explicit trace instrumentation. Build this before you need it.
- **Amazon HITL finding:** Multi-agent coordination quality (inter-agent communication coherence, conflict resolution) cannot be reliably scored by automated metrics. Budget for human evaluation in your agent loop.
