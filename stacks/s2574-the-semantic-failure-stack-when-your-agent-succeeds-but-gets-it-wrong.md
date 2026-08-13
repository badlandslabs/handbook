# S-2574 · The Semantic Failure Stack — When Your Agent Succeeds But Gets It Wrong

Your agent ran for 47 turns, called 12 tools, and produced a polished Slack message saying the deployment was complete. The build actually failed at step 3. No tool returned an error — the agent simply misread the ambiguous yellow warning as success, continued confidently, and generated a false report. This is not a code error. The agent did exactly what it was designed to do. It just decided wrong. This is the **semantic failure problem**: agents fail at intent boundaries, not code boundaries, and the failure is invisible to traditional error handling.

## Forces

- **Agents fail at meaning, not mechanics.** Traditional software fails at clear boundaries — a database timeout, a missing file, an HTTP 500. Agents fail by being confident and wrong: misclassifying ambiguous outputs, hallucinating tool parameters, or completing the wrong task with perfect syntax.
- **Recovery strategy depends on failure type, but most agents only handle one.** Retrying a semantic failure gets you the same wrong answer faster. Circuit-breaking a transient rate limit when the agent is looping on tool selection is wasted effort.
- **Agents can leave systems in undefined state.** A traditional crash is obvious. An agent mid-task that silently starts making incorrect decisions can corrupt downstream data, send wrong emails, or approve wrong decisions — with no exception thrown.
- **Scaffold quality is as important as model quality.** AlphaEval (2026) tested Claude Code, Codex, Copilot, and Cursor across 94 real production tasks from 7 companies. The best configuration (Claude Code + Opus 4.6) scored 64.41/100. The worst scored 39.47/100. Same models, different scaffolding. Evaluation and recovery patterns live in the scaffold, not the model.

## The move

**Build a taxonomy-aware failure handling stack that handles the five failure modes agents actually produce.**

- **Classify failures by type at the orchestration layer, not the application layer.** When a step fails, the orchestrator must determine whether this is: (1) transient model error (rate limit, network, malformed response), (2) tool error (wrong params, unavailable API), (3) orchestration error (wrong tool selected, plan derailed), (4) semantic error (agent produced a confident wrong answer), or (5) loop error (agent repeating without progress). Classifying first, then routing to the appropriate recovery, prevents the common mistake of applying the same strategy to every failure type.

- **Serialize state at every step boundary — not just on checkpoint.** Before each tool call or LLM invocation, persist: the current conversation history, a summary of completed steps, any intermediate outputs, and a step counter. On any failure, inspect the serialized state before deciding whether to retry, restart, or escalate. Reddit practitioners report that checkpointing is the single highest-impact reliability improvement for long-running agent tasks.

- **Use exponential backoff with jitter for transient errors, but cap retries for semantic failures at 1.** Transient errors (rate limits, network timeouts, 503s) are best resolved with retry — but configure it per-error-type. A 429 gets exponential backoff. A 500 gets 2 retries then circuit-break. A semantic mismatch (agent misread the output) gets 0 retries of the same approach: instead, re-prompt with additional constraints or route to a different strategy.

- **Circuit-break at three levels: model, tool, and orchestration.** At the model level: if a provider returns N consecutive errors, switch to fallback provider. At the tool level: if a tool returns N consecutive unexpected outputs, mark it degraded and skip it. At the orchestration level: if the agent's trajectory deviates significantly from the expected plan (checked via a lightweight plan-alignment prompt), trigger a replan from the last good state.

- **For loops and non-progress, implement a step-limit with forced self-reflection.** Track a progress hash — a deterministic digest of completed steps and their outputs. If the hash repeats within N steps, the agent must stop and generate a self-critique before continuing. The AgentWorks team reports this catches the majority of silent loops that would otherwise consume budget indefinitely.

- **Escalation paths are not optional.** For any step that has irreversible consequences (sending an email, approving a payment, merging code), define an escalation threshold: N failures at that step, or any failure after a semantic error, routes to human review. The AgentWorks team frames this as "the demo works; production fails; the gap is escalation."

## Evidence

- **Research paper:** AlphaEval — Evaluating Agents in Production (arXiv:2604.12162, April 2026) — Tested 4 agent products (Claude Code, Codex, Copilot, Cursor) across 94 real tasks from 7 companies in 6 occupational domains. Best score: 64.41/100. Key finding: "The scaffold matters as much as the model" — scaffolding differences explain 25+ point performance gaps. — [https://arxiv.org/pdf/2604.12162](https://arxiv.org/pdf/2604.12162)

- **Engineering blog:** Agent Error Recovery: 5 Patterns for Production Reliability (aiagentsblog.com, March 2026) — Documents the five failure modes of agentic systems with implementations using the Anthropic SDK: exponential backoff, circuit breakers, checkpoint-and-resume, fallback strategies, and escalation queues. Key insight: "Agents leave systems in undefined state — not the clean failure of traditional software." — [https://aiagentsblog.com/blog/agent-error-recovery-patterns](https://aiagentsblog.com/blog/agent-error-recovery-patterns)

- **Engineering blog:** Agent Error Handling and Recovery Patterns: Production-Ready Resilience (AgentWorks, May 2026) — Reports from EU enterprise teams building compliant AI agents. Key findings: try-different-model for persistent failures (not retry-same-model), per-tool recovery handlers, and context degradation (removing noisy tool outputs from context before resuming). "A demo agent that works on the happy path is two months of engineering away from a production agent." — [https://agent-works.ai/insights/agent-error-handling-and-recovery-patterns-production-ready-resilience](https://agent-works.ai/insights/agent-error-handling-and-recovery-patterns-production-ready-resilience)

- **Reddit discussion:** "How are you handling recovery when AI agents fail mid-task in production?" (r/AI_Agents) — 51 responses from practitioners. Common patterns: checkpoint-and-resume (most cited), state persistence in Redis or SQLite, max-step limits with forced human review, and monitoring tools to detect non-progress in real time. One practitioner: "Agents fail more than you think. Build for it from day one." — [https://www.reddit.com/r/AI_Agents/comments/1u0bp9v/](https://www.reddit.com/r/AI_Agents/comments/1u0bp9v/how_are_you_handling_recovery_when_ai_agents_fail/)

## Gotchas

- **Do not retry semantic failures.** Retrying with the same prompt produces the same wrong answer. Instead, change the approach: add constraints to the prompt, provide different tool options, or decompose the task differently.
- **Checkpointing without a restore strategy is useless.** Serializing state is necessary but not sufficient — you need a restore-from-checkpoint path that the orchestrator can execute without manual intervention. Test this path explicitly.
- **Step limits without progress detection are blunt instruments.** Capping at 50 steps prevents runaway loops but also kills legitimate long tasks. Combine step limits with progress hashing: if the agent is making genuine progress (different outputs each step), let it continue.
- **Escalation that requires a human to be online is not escalation — it is a single point of failure.** Define automated fallback actions for escalation: log the failure, notify via a reliable channel, and leave the system in a safe state (do not continue and do not delete partial work).
