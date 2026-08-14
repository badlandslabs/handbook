# S-2637 · The Agent-That-Fails-Silently Stack — When Your Agent Loops Forever and No One Knows

You shipped the agent. It passed every test. Three weeks in, you're fielding support tickets about a workflow that worked last Tuesday and now hangs silently — or worse, one that succeeds visibly and corrupts data invisibly. The agent didn't crash. It didn't throw an exception. It just... kept going, or kept going wrong. That's the new failure mode. Agents fail differently than software: they fail without raising exceptions, without crashing, without any signal the old monitoring stack was built to catch.

## Forces

- **Agents own the logic layer — and can be wrong without failing.** Conventional microservices fail via crashes or unreachable dependencies. AI agents can produce wrong outputs, drift from goals, loop on retry, or silently degrade in quality, and the system keeps running. The failure surface is behavioral, not architectural.
- **The compounding math is brutal.** Specification failures (~42% of multi-agent failures) and coordination breakdowns (~37%) compound in multi-agent pipelines. A single unchecked error in one agent propagates through the entire system.
- **Production tokens + agent autonomy = catastrophic blast radius.** When an agent has API access to production systems — which it needs to be useful — a single prompt misfire, a wrong tool invocation, or a goal-drift episode can issue destructive mutations before a human intervenes. The Railway database deletion is the canonical example: the agent had production credentials, no least-privilege scoping, and the ability to delete everything.
- **Evaluation doesn't catch what it wasn't designed to catch.** Green eval scores don't guarantee correct behavior in production. Silent failures — wrong data in the right shape, correct output in the wrong context — look identical to automated checks that only validate structure.
- **Human oversight becomes the last line of defense — but it's also the bottleneck.** Checkpoint-and-review human-in-the-loop patterns slow agents down and limit autonomy. Teams must choose between speed and safety, and the wrong call on either end is costly.

## The move

**Design for failure as a first-class system property, not an edge case.**

### 1. Instrument before you orchestrate

Add execution tracing (step-level logging, token usage per call, tool invocation sequences) *before* adding agent complexity. You cannot debug what you cannot see. Helicone, LangSmith, or equivalent observability tooling is table stakes — not optional. Every tool call, every LLM response, every state transition gets a log entry with a trace ID that ties back to the originating request.

### 2. Scope permissions like an SRE, not a developer

Treat every agent credential as a production secret with blast radius. Least-privilege scoping: agents get tokens scoped to the minimum required actions and environments. Separate credentials per environment. No production tokens in the same execution context as agent tooling unless absolutely necessary — and if necessary, add mutation-blocking guardrails (confirm-before-action checkpoints for destructive operations: delete, drop, truncate, overwrite). The Railway incident's root cause was not the AI — it was a production token in the agent's environment.

### 3. Build dead-man switches into long-running loops

Agents can loop forever on ambiguous tasks. Implement hard limits: maximum steps per workflow (10-20 is typical), maximum retries per tool call (2-3), and wall-clock timeouts with graceful degradation. When a limit is hit, the agent should surface the failure state clearly — return partial results, flag the failure mode, and halt rather than continue guessing. This is not a sign of weakness; it is the system's self-preservation mechanism.

### 4. Use checkpoint human-in-the-loop for irreversible actions

For destructive or high-stakes operations (database mutations, payment APIs, deployment triggers), insert a mandatory human checkpoint before execution. The agent prepares the action and the human approves or rejects. This is not a workflow blocker — it's the mechanism that lets you give agents real autonomy on reversible work while retaining control on irreversible work. Anthropic recommends this explicitly in their agent design guidance: agents handle the routine; humans handle the irreversible.

### 5. Validate outputs against behavioral specifications, not just structure

Structure validation (JSON schema, response format) catches syntax errors. Behavioral validation catches semantic failures: did the agent reach the right answer, or did it reach an answer in the right shape? Use LLM-as-judge for behavioral checks — a second model call that evaluates whether the primary output is correct, complete, and appropriate for the task. This is the "Agent-as-a-Judge" pattern: use a critic agent to evaluate the executor agent.

### 6. Implement graceful degradation for multi-agent coordination failures

When one agent in a multi-agent pipeline fails or times out, the system should degrade to a safe state rather than cascade failures. Microsoft's ISE team documented supervisor pattern (single coordinator with error escalation) and hierarchical pattern (nested coordinators for larger systems) as two approaches. Choose based on scale: supervisor for <10 agents, hierarchical for enterprise-scale. Both require explicit error propagation paths — dead-letter queues, fallback agents, and circuit breakers that isolate the failing component.

## Evidence

- **Anthropic Engineering (Dec 2024):** "The most successful implementations use simple, composable patterns rather than complex frameworks." Recommends starting with single LLM calls, only escalating to agentic loops when the complexity is justified. Emphasizes that checkpoint human-in-the-loop is essential for irreversible actions in any agentic deployment. — [Anthropic — Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Zylos Research (May 2026):** Six failure categories unique to agents: tool misuse, context loss, goal drift, retry loops, cascading errors in multi-agent systems, and silent quality degradation. Galileo (2025) production data: specification failures account for ~42% of multi-agent failures, coordination breakdowns ~37%, verification gaps ~21%. Agent failures are qualitatively different from conventional software failures — the agent is the logic layer and can behave incorrectly without exceptions. — [Zylos — AI Agent Self-Healing and Failure Recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Hacker News / PocketOS incident (2025):** An AI agent in Cursor (Plan mode, Claude Opus 4.6) deleted a production database and its backups on Railway. Root cause: Railway API token stored in the same environment as staging, discoverable by the agent. Railway tokens grant blanket permissions — no least-privilege scoping. Backups were stored in the same volume as primary data. Community consensus: operators bear primary responsibility. — [HN — An AI agent deleted our production database](https://news.ycombinator.com/item?id=47911524)

- **Microsoft ISE Developer Blog (June 2026):** Documents evolution from modular monolith router pattern (single agent per request) to microservices-based coordinator pattern enabling multi-agent collaboration. Four orchestration patterns with trade-offs: Supervisor (simple, single point of failure), Hierarchical (scales to 20+ agents, coordination overhead), Peer-to-peer (fault-tolerant, slower consensus), Swarm (50+ agents, emergence complexity). Case study: 80% reduction in insurance claims processing. — [Microsoft — Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **MMC Ventures — State of Agentic AI, Founder's Edition (Nov 2025):** Survey of 30+ AI agent startups and 40+ enterprise practitioners. 52% build infrastructure in-house. Top deployment challenges: workflow integration and human-agent interface. Only 66% of startups achieve ≥70% autonomy in production. — [MMC Ventures — State of Agentic AI](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)

## Gotchas

- **Green evals don't mean safe agents.** Eval suites encode engineer assumptions. Silent failures — wrong content in the right format — pass automated checks. Behavioral validation with LLM-as-judge catches what structure checks miss.
- **The blast radius scales with agent autonomy.** The more powerful the agent, the more catastrophic a failure. Treat every capability increase as a risk increase that requires proportional safeguards.
- **Loops are the most common silent failure.** Without hard step limits, agents retry ambiguous tasks indefinitely. Add limits. Log the loop state. Surface it clearly when limits are hit.
- **Coordination failures in multi-agent systems are not visible from individual agent monitoring.** You need cross-agent tracing to detect when agents drift out of sync or when a failure in one propagates to others.
- **"Agent deleted our production DB" is not an AI failure — it's an architecture failure.** The AI did exactly what it was asked. The system design gave it the capability to do something catastrophic. Fix the permissions model, not the prompt.
