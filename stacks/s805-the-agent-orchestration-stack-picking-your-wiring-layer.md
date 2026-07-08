# S-805 · The Agent Orchestration Stack: Picking Your Wiring Layer

You have working agents. They call tools, they reason, they produce outputs. Then you need five of them working together — on a pipeline, with conditional branches, fault recovery, and state that persists across the run. The agents aren't the hard part anymore. The wiring is. This is the layer where most production agent projects succeed or fail.

## Forces

- **LLM-as-orchestrator vs. deterministic routing.** Letting the LLM decide what to call next is flexible but expensive and non-deterministic. Hard-coding the flow is reliable but rigid. The production answer isn't one or the other — it's layered.
- **Token cost compounds through the graph.** Every hop adds context. Token duplication across agents (MetaGPT reports 72%, CAMEL 86%) inflates costs with no corresponding quality gain.
- **Observability is the #1 production barrier.** When a multi-agent run fails, you need to know: which agent ran, what it received, what it returned, and where the chain broke. Single-agent frameworks make this trivial; multi-agent frameworks make it genuinely hard.
- **Pattern mixing is the norm, not the exception.** Production workflows combine 2–3 orchestration patterns — a Supervisor that fans out to parallel agents, then sequences them into an Evaluator-Optimizer loop. No single pattern covers real workloads.
- **72% of enterprise AI projects now involve multi-agent systems** (up from 23% in 2024), according to Zylos Research — but the tooling ecosystem is still fragmented across six major frameworks with fundamentally different mental models.

## The Move

### Know the six core patterns and when to reach for each

**Supervisor** — one orchestrator agent decomposes the task, delegates to specialists, monitors progress, and assembles output. Best for: complex, open-ended tasks requiring different skill domains (research → analysis → writing). Single point of failure is the tradeoff.

**Sequential Pipeline** — agents execute in a fixed order, each consuming the prior agent's output. Best for: linear workflows where order matters and outputs are tightly coupled (crawl → extract → transform → load). Inflexible if mid-stream branching is needed.

**Parallel Fan-Out / Fan-In** — a trigger dispatches tasks to multiple agents simultaneously; results merge at a convergence point. Best for: independent subtasks that can execute concurrently (batch URL analysis, parallel research queries). Requires merge logic; token costs multiply.

**Router** — a classifier agent (often small/fast) directs incoming requests to the right specialist agent or workflow. Best for: high-volume, diverse request types (customer support triage, skill routing). The routing agent must be small and fast — its only job is classification, not execution. Arcee Conductor formalizes this with LLM-powered routing between domain-specialized agents, routing 3 calls across GPT-5, Claude Sonnet 4, and Gemini 2.5 Pro with a 7B orchestrator — the economics are routing economics, not multi-agent economics.

**Hierarchical Delegation** — a supervisor spawns sub-supervisors, each managing a team. Scales to 20+ agents. Best for: large enterprise workflows with multiple domains. Coordination overhead is the real cost.

**Evaluator-Optimizer Loop** — the agent produces output, a separate evaluator agent judges it against criteria, and the original agent iterates until the evaluator passes. Best for: code generation, content creation, any domain where "good enough" is measurable. Stripe's Minions use a 2-round max CI cycle before human handoff — a production variant of this pattern.

### Choose your framework based on your stage

| Framework | Best fit | Production readiness | Audit trail |
|---|---|---|---|
| **LangGraph** | Strict deterministic requirements, regulated industries | Enterprise-grade (LangSmith full trace/replay) | Full state replay, step-by-step |
| **CrewAI** | Fast prototyping, role-based pipelines | Medium (most teams migrate to LangGraph for prod) | Minimal (3rd-party: Langfuse, Arize) |
| **AutoGen 0.4+** | Microsoft/Azure shops, conversational research | Medium (Enterprise tier needed) | Conversation logs only |
| **Conductor (Microsoft, open source)** | Workflows where structure is fixed at definition time, token budget is constrained | High (deterministic YAML, zero tokens in orchestration) | YAML-defined, deterministic execution |
| **Custom / raw** | Teams with unique constraints, willing to own maintenance | Varies | Roll your own |

### The *nix Tool Pattern: when function calling is the wrong abstraction

A former Manus backend lead (1,300+ Reddit upvotes) argues that the industry-standard typed function schema pattern — `tools: [search_web, read_file, write_file, run_code, ...]` — creates cognitive overhead that degrades accuracy. His replacement: a single `run(command="...")` tool exposing Unix-style CLI commands. The argument has three parts:

1. **LLMs are text-native.** Unix was designed for text streams. LLMs consume and produce text. These two systems, designed 50 years apart, are structurally compatible — LLMs already have vast CLI patterns in their training data.
2. **Discovery beats catalog.** Instead of selecting from a tool catalog (accuracy drops as tools are added), the agent discovers tools through `--help`, `man pages`, and stderr — the same way a human operator would.
3. **Exit codes + consistent metadata** let the agent self-correct without re-prompting. Every tool result is appended with exit code and timing: `file1.txt file2.txt dir1/ [exit:0 | 12ms]`. When stderr is visible, the agent knows *why* something failed on the first call instead of blindly guessing 10 different package managers.

### Combine patterns at the workflow level

Stripe's Minions illustrate this: a Slack emoji (human trigger) → a sequential coding pipeline inside a Devbox (isolated AWS EC2, warm pool <10s provisioning) → parallel test runs in CI → evaluator loop (max 2 rounds) → PR. That's Supervisor + Sequential + Fan-Out + Evaluator-Optimizer combined. The orchestration complexity is real; the payoff is 1,300+ PRs/week with zero human coding.

## Evidence

- **Engineering post:** "Conductor: Deterministic Orchestration for Multi-Agent AI Workflows" — Microsoft open-sources Conductor (MIT), a YAML-driven CLI where routing is deterministic, zero tokens are consumed by orchestration, and Jinja2 templates handle conditional branching. Solves the "LLM-as-orchestrator burns tokens on routing decisions" problem for fixed-structure workflows. — [https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows](https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows)

- **Primary source / practitioner account:** Former Manus backend lead publishes detailed critique of typed function calling, documents the *nix single-tool approach across three production agents (Manus, Pinix, agent-clip). Reports stderr visibility as the highest-impact change — "10 calls with blind guessing → 1 call with visible failure reason." — [https://gist.github.com/thoroc/973bef1770387e1986876ab6c6d20947](https://gist.github.com/thoroc/973bef1770387e1986876ab6c6d20947) / [https://www.reddit.com/r/LocalLLaMA/comments/1rrisqn](https://www.reddit.com/r/LocalLLaMA/comments/1rrisqn)

- **Primary source / production metrics:** Stripe engineer Steve Kaliski documents the Minions system: 1,300+ PRs/week, Devbox warm pool <10s, max 2 CI rounds before human handoff, ~500 tools in Toolshed, multi-million-line Ruby codebase. Engineers trigger via Slack emoji. — [https://analyticsindiamag.com/ai-news/stripes-autonomous-coding-agents-generate-over-1300-prs-a-week](https://analyticsindiamag.com/ai-news/stripes-autonomous-coding-agents-generate-over-1300-prs-a-week) / [https://www.chatprd.ai/how-i-ai/stripes-ai-minions-ship-1300-prs-weekly-from-a-slack-emoji](https://www.chatprd.ai/how-i-ai/stripes-ai-minions-ship-1300-prs-weekly-from-a-slack-emoji)

- **Framework comparison (March 2026):** Gheware DevOps AI blog benchmarks LangGraph, AutoGen, and CrewAI across 12 dimensions including observability, Kubernetes support, audit trails, and GitHub stars. LangGraph leads on observability (LangSmith) and audit depth; CrewAI leads on onboarding speed; AutoGen leads in Azure environments. — [https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-autogen-vs-crewai-comparison-2026.html)

- **Orchestration taxonomy:** The Thinking Company (Bartek Pucek) documents the six core patterns with architecture diagrams and real-world mapping. Key finding: production systems combine 2–3 patterns. — [https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns)

## Gotchas

- **Don't let the LLM orchestrate everything.** Use LLMs for routing only when the task genuinely requires dynamic judgment. Fixed-sequence workflows should be YAML-defined — you'll save tokens and get replay for free.
- **Token duplication kills budgets silently.** CAMEL-style architectures report 86% token overlap across agent messages. Profile your graph before deploying. The fix is content-aware routing and selective context passing.
- **Observability isn't optional at 3+ agents.** LangSmith (LangGraph), Langfuse (CrewAI), or custom instrumentation — pick one before you hit production. Without step-level traces, debugging a failed multi-agent run is archaeology.
- **The Supervisor pattern has a real single-point-of-failure risk.** If your orchestrator agent fails or misroutes, the entire workflow fails. For critical paths, add a deterministic checkpoint layer (Conductor-style YAML guardrails) over the LLM supervisor.
- **Exit codes and stderr are not cosmetic.** The Manus practitioner's most-upvoted insight: agents that can't see stderr waste inference budget guessing failure modes. Always include them in your tool result schema — this is not optional for production reliability.
