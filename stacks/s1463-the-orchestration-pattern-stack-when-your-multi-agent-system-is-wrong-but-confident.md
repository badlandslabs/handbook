# S-1463 · The Orchestration-Pattern Stack — When Your Multi-Agent System Is Wrong but Confident

You've added a second agent to your pipeline. Then a third. You've got a supervisor, two workers, a critic, and a router. The system scores well on benchmarks. In production, it's confidently incorrect, sycophancy-cascading through five rounds of agreement, and burning 2× the cost of a single-agent approach. The agents are fine. The pattern is wrong for the problem.

## Forces

- **More agents doesn't mean better results.** Multi-agent systems show +2.1 percentage points accuracy over single-agent on benchmarks but cost ~2× — and 40% of multi-agent pilots fail within six months of production deployment (Beam.ai, July 2026). Teams reach for multi-agent because it *sounds* like the right answer, not because they've mapped the pattern to the problem.
- **Each orchestration pattern has a specific failure mode.** Orchestrator-worker systems fail when the orchestrator's routing degrades under ambiguous inputs. Supervisor-worker systems fail through central bottleneck. Peer-to-peer group chat fails through sycophancy cascading — agents agreeing with wrong majority positions. Voting ensembles fail when errors correlate across agents. Dynamic handoff fails when agents lack context to decide when to transfer.
- **Benchmark accuracy is not production accuracy.** A single agent matches or beats multi-agent on 64% of benchmark tasks (Beam.ai). The 36% where multi-agent wins are specific: tasks requiring genuinely distinct expertise, parallel independent work, or adversarial self-critique. Teams apply multi-agent universally and pay the cost everywhere.
- **Sycophancy cascading is the hardest failure to detect.** Agents trained to agree reinforce each other's errors. Five rounds with three agents means 15 LLM calls and a result that *sounds* authoritative because it has broad consensus. No error flags it — the agents all agreed.

## The move

Match the orchestration pattern to the task topology, not the team size.

- **Orchestrator-worker** when you have decomposable tasks with known sub-types. The orchestrator uses a capable model; workers use cheaper, task-specialized models. Best for pipelines where the orchestration logic is stable and workers are interchangeable.
- **Supervisor-worker** when a central agent must approve each step. Use for regulated environments where human-in-the-loop review is required per decision, not per pipeline. The supervisor is a gatekeeper, not a router.
- **Sequential pipeline** when tasks have a strict dependency chain. Agent B cannot start until Agent A finishes. Simpler to debug and cheaper than orchestrator patterns. Reach for this before adding a supervisor.
- **Voting ensemble** for independent parallel work where multiple perspectives improve a single answer — code review, content critique, data analysis. Require ≥3 agents with genuinely different system prompts or model providers. If agents share the same base model and system prompt, voting adds cost without diversity.
- **Dynamic handoff** when you genuinely cannot predict which specialist is needed upfront — customer support where a billing issue turns into a technical one mid-conversation, or research where the relevant domain only emerges during exploration. HCLTech reported 40% faster case resolution with dynamic agent handoff (Beam.ai).
- **Difficulty-aware routing** — classify query difficulty at intake and route to shallow (single agent, fast) or deep (multi-agent pipeline) based on the classification. This delivers significant cost reductions without accuracy loss by not running every query through a full multi-agent pipeline (Zylos Research, April 2026).

## Evidence

- **Blog post:** 6 Multi-Agent Orchestration Patterns for Production — Beam.ai analyzed production deployments across six patterns and found 40% of multi-agent pilots fail within six months, with 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025). Single agent matches multi-agent on 64% of benchmark tasks. — [beam.ai/agentic-insights/multi-agent-orchestration-patterns-production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Research blog:** Agent Workflow Orchestration Patterns — Zylos Research documents difficulty-aware dynamic routing and federated orchestration as emerging 2026 patterns, noting that routing by task difficulty (shallow vs. deep pipeline) delivers cost reduction without accuracy loss. — [zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)
- **Benchmark analysis:** Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems (arXiv:2511.14136) — Found critical gap between benchmark performance and production deployment success; enterprises require evaluation across cost, reliability, security, and operational constraints, not just task completion accuracy. — [arxiv.org/html/2511.14136v1](https://arxiv.org/html/2511.14136v1)
- **Engineering blog:** Production Benchmarks: LangGraph vs AutoGen vs CrewAI — Tacavar deployed all three frameworks and found LangGraph best for stateful graph-based workflows with fine-grained control, AutoGen for research-heavy conversational multi-agent systems, CrewAI for rapid prototyping and role-based agent teams. Each breaks differently in production. — [tacavar.com/blog/ai-agent-frameworks-compared-2026](https://tacavar.com/blog/ai-agent-frameworks-compared-2026)

## Gotchas

- **Adding an agent to fix a broken agent compounds the problem.** If a single agent is failing, a second agent reviewing its output doubles cost and introduces a new failure mode (sycophancy) without fixing the root cause. Diagnose whether the failure is expertise (agent doesn't know enough), capability (model is too weak), or context (agent has wrong information).
- **Voting ensembles require real diversity.** Three agents using the same model with slightly different system prompts produce correlated errors. True diversity means different model families, different tool access, or different reasoning approaches — not three copies of Claude with different personalities.
- **Centralized patterns bottleneck at the coordinator.** An orchestrator or supervisor handling all routing decisions becomes the single point of failure. If it degrades under load, the entire pipeline degrades. Build idempotency and retry at the coordination layer.
- **Sequential pipeline is underrated.** Before reaching for a supervisor or orchestrator, ask whether your task is actually a strict pipeline. Most tasks are — A then B then C. Sequential is cheaper, more predictable, and easier to debug than hierarchical patterns for linear dependencies.
