# S-1762 · The Scale-First Orchestration Stack

When your multi-agent pipeline works flawlessly in staging with 3 agents and degrades silently at 50 — slower responses, duplicate actions, agents that stop mid-task and never recover. You optimized for the demo. The production load revealed that orchestration choices that don't matter at prototype scale become the entire problem at deployment scale.

## Forces

- **Scale dominates complexity.** Both DAG Plan & Execute and ReAct perform similarly on simple and complex tasks — but both collapse at enterprise scale (200+ agents) due to agent discovery noise. Scale is the variable, not task complexity.
- **DAG precision costs overhead.** DAG Plan & Execute offers structured parallelization and higher precision at small scale, but its higher per-task overhead compounds at scale — plan, interrupt, and replan cycles pile up.
- **ReAct handles churn better.** Reactive agents outperform structured ones at enterprise scale because they absorb discovery noise gracefully — but sacrifice deterministic execution guarantees.
- **The protocol layer is maturing beneath orchestration choices.** MCP (97M monthly SDK downloads, 5,800+ servers, 78% enterprise adoption) standardizes tool access; A2A (150+ organizations, Linux Foundation) standardizes agent-to-agent coordination. These layers are now stable enough to stop re-inventing the transport and focus on orchestration logic.
- **Framework lock-in is the hidden tax.** LangGraph, CrewAI, AutoGen, and custom pipelines each implement orchestration differently. Teams that choose a framework before choosing an orchestration pattern pay migration costs when the pattern proves wrong for their scale.

## The move

**Choose your orchestration pattern based on expected agent count, not task complexity.**

- **Single-digit agents (< 10):** DAG Plan & Execute via LangGraph or Temporal. Structured parallelization pays off; overhead is negligible. Explicit state graphs catch errors early. This is the sweet spot for DAG's precision advantage.
- **Double-digit agents (10–80, Department scale):** Hybrid: use DAG for stable, dependency-ordered sub-tasks; use ReAct/event-driven for reactive, event-triggered work. Introduce a Task Manager layer for priority inference, event merging, and preemption.
- **Enterprise scale (80+, especially 200+):** Go fully event-driven. The discovery noise that DAGs create at scale — each plan-and-execute cycle touching more agents — overwhelms the structure benefit. Agents as reactive consumers of an event bus with lightweight coordination beats structured orchestration.
- **Always wire in infrastructure-level guardrails at the framework layer, regardless of orchestration choice:**
  - Per-tool circuit breakers that track failure rates and route around broken endpoints
  - Loop detection: track tool-call signatures; halt when the same call sequence repeats N times
  - Idempotency keys on all tool calls with side effects (payments, emails, API writes) — prevent duplicate execution on retry
  - Timeout hierarchy: child timeouts must be shorter than parent timeouts, with max_retries factored in so the parent can still act after child exhaustion
  - Output validation: pipe tool results through a verifier agent before the workflow continues

## Evidence

- **arXiv paper (June 2026):** SAP researchers evaluated DAG Plan & Execute vs. ReAct across 208 production-derived enterprise scenarios spanning Persona (<10 agents), Department (20–80), and Enterprise (200) scales. Key finding: "scale, not task complexity, dominates orchestration performance — both architectures degrade at enterprise scale as agent discovery noise becomes the primary bottleneck, with simple tasks degrading more sharply than complex ones." DAG Plan & Execute showed higher precision at smaller scales but ReAct proved more robust at enterprise scale. — [arXiv:2606.20058](https://arxiv.org/pdf/2606.20058)
- **Red Hat blog (July 2026):** Documented three production failures from a single LangChain agent in one night — duplicate support tickets (no idempotency guard), credential bleed (no identity boundary), and wrong-answer delivery (no output validation). Conclusion: "The framework choice varies. The gap doesn't." Infrastructure-level failures are not framework concerns. — [Red Hat Blog](https://www.redhat.com/en/blog/why-good-ai-agents-fail-production-missing-infrastructure-layer)
- **GitHub (agentguard-llm):** Open-source library documenting that "AI agents fail at 91%+ rates in production." Addresses infinite loops, silent failures, duplicate actions, rate-limit crashes, and token-limit blindness as systemic problems across LangChain, AutoGen, CrewAI, and custom pipelines — not framework-specific bugs. — [GitHub: maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm)

## Gotchas

- **Over-engineering at prototype scale.** Starting with event-driven architecture or a full actor model when you have 3 agents adds complexity for no benefit. DAG is fine at small scale — only migrate when the pain of discovery noise appears.
- **Confusing framework choice with orchestration pattern.** LangGraph can implement DAG, ReAct, or event-driven patterns. The pattern matters more than the framework. A LangGraph agent running naive ReAct behaves like a ReAct agent regardless of the framework wrapper.
- **Tool governance is orthogonal to orchestration.** MCP standardizes tool access but doesn't solve which tools an agent can call, under what conditions, or with what credentials. That's still an infrastructure problem the protocol doesn't reach.
- **Forgetting that simple tasks fail faster at scale.** Counterintuitive finding from the SAP study: simple tasks degrade more sharply than complex ones at enterprise scale. The "needle in a haystack" problem — distinguishing a relevant agent from noise when hundreds are available — hits deterministic, low-complexity tasks hardest because there's less signal to filter on.
