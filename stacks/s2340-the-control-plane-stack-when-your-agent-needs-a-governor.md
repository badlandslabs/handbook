# S-2340 · The Control Plane Stack — When Your Agent Needs a Governor

You shipped the agent. It works in staging. It handles the happy path beautifully. Then in production it retries a non-idempotent operation 12 times, hits an API rate limit and loops for 35 minutes, or silently forwards credentials to an attacker-controlled endpoint — and you have no idea any of it happened until the bill arrives or a customer complains.

Production agents need a governance layer. Teams are building it.

## Forces

- **Agents are non-deterministic; infrastructure is not.** LLMs can fail silently, loop, hallucinate tool arguments, or take irreversible actions. Traditional infrastructure has no mechanism to observe or constrain this.
- **Framework lock-in vs. protocol longevity.** AutoGen went into maintenance mode. CrewAI and LangGraph change fast. Building governance on a specific framework means rebuilding when the framework does.
- **Latency vs. safety tradeoff.** Every governance check adds latency. Teams must decide what to guard at step boundaries vs. audit afterward.
- **The observability gap.** Standard APM doesn't capture agent-specific failure modes — tool call sequences, context window pressure, loop detection.

## The move

**Layer a control plane between your agent's decisions and the world.** The pattern that emerges from production teams: governance as middleware, not part of the agent logic itself.

### Core components

- **Step-boundary policy enforcement.** Every tool call is intercepted before execution. The control plane checks: is this operation idempotent? Has it been called N times already? Is the caller authorized? Only then does it proceed or block. AxonFlow implements this as an inline execution authority with per-step policy evaluation.
- **Idempotency guards.** Before retrying, the control plane verifies whether the operation is safe to repeat. This is the most common cause of production incidents — an agent encountering a timeout and retrying a payment, a write, a state change. Guard it at the control plane, not in the agent prompt.
- **Execution logging as a system of record.** Every decision point — tool call, block, approval request, retry — is logged with full context (input, output, timestamp, caller identity). Not for debugging after the fact, but as an auditable trail for regulated environments. Cleanlab's survey found 42% of regulated enterprises are actively adding this.
- **Approval workflows for high-stakes operations.** Define boundaries: operations above $X, writes to production databases, external API calls, data exfiltration attempts. Route these to human approval queues. The control plane pauses execution, awaits approval, then resumes or aborts.
- **Trajectory logging.** Capture the full sequence of LLM calls, tool invocations, and state changes. Not just final outputs — the path. NVIDIA's evaluation guide recommends evaluating full trajectories, not just final answers, because two agents can produce identical outputs via very different execution paths.
- **Loop detection.** Track repeated operations against the same targets. Set thresholds: if this tool has been called 5 times against the same resource in 10 minutes, surface an alert or halt. Deadlock and resource contention account for a significant fraction of multi-agent failures.
- **Observability that speaks agent.** Standard APM metrics (latency, error rate) miss agent-specific failure modes. Instrument: tool call success rate per tool, context window utilization over time, agent-to-agent handoff latency, policy enforcement block rate.

## Evidence

- **Show HN (AxonFlow):** "AxonFlow is a self-hosted control plane that sits inline in the execution path to govern LLM calls, tool calls, retries, approvals, and policy enforcement step by step." Built specifically for teams operating agents under production constraints — addresses retries with side effects, partial failures, and step-level permissions. — [https://news.ycombinator.com/item?id=46692499](https://news.ycombinator.com/item?id=46692499)
- **Engineering Leaders Survey (Cleanlab):** 42% of regulated enterprises plan to add oversight features (vs. 16% of unregulated). 63% of enterprises plan to improve observability and evaluation in the next year. Less than 1 in 3 teams are satisfied with current observability and guardrail solutions. — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **NVIDIA Technical Blog:** "Evaluate full trajectories, not just final answers. Two agents can provide the same answer while behaving very differently: one uses three precise tool calls, while another thrashes through dozens of irrelevant steps. Final-answer grading treats agents as identical, but production behavior does not." Recommends Task Success Rate (TSR) — whether the agent resolved the intent within defined constraints. — [https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)
- **Ask HN Production Orchestration Thread:** Practitioners are split on frameworks — some roll custom control planes with Node.js and V8 isolates, others build on LangGraph with custom orchestrators. Common pattern: keep the control plane decoupled from the orchestration framework itself. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **Control plane latency.** Every inline check adds latency to every tool call. Profile the overhead and cache policy decisions where possible — some checks (is this user authorized?) can be pre-computed and cached.
- **Governance that's too coarse blocks your agent.** A blanket "no external API calls" policy will break legitimate agent capabilities. Define policies at the operation level, not the category level.
- **Logging without analysis is noise.** Trajectory logs only help if you can query them. Invest in the query layer — dashboards, alert rules, anomaly detection — not just the log store.
- **Protocol over framework.** Build governance on stable protocols (MCP for tool access, A2A for agent-to-agent) rather than framework-specific abstractions. The framework you build on today may be in maintenance mode tomorrow — AutoGen already demonstrated this.
