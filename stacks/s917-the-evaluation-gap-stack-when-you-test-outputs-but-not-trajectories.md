# S-917 · The Evaluation Gap

You ran the agent 20 times. It answered correctly 19 times. You shipped it. On week three in production, a customer triggers a Unicode name edge case and the agent issues a $47,000 fraudulent refund through a customer support bot. Your eval suite passed. The agent failed in a way your tests never modeled.

This is the **Evaluation Gap** — the structural mismatch between what agent evals measure and what actually causes production failures. Most teams test whether agents produce correct outputs. Few test whether agents take correct paths to those outputs, handle edge cases in their tools, or recover gracefully when things go wrong.

## Forces

- Final-output evaluation misses trajectory quality — an agent can reach the right answer through a broken reasoning chain, or fail to reach it through a mostly-correct one
- Agent behavior is non-deterministic across runs, so pass/fail on a small eval set is statistically meaningless
- Traditional software testing (unit tests, integration tests) cannot model the emergent behaviors that arise from LLM-tool interactions
- The 40%+ predicted failure rate for AI agent projects (Gartner) is partly a measurement artifact — teams ship agents that "seem to work" because they never tested the failure modes
- Context window dynamics cause silent degradation — an agent that works at 95% context fills up and silently misbehaves at 100%, with no error message

## The Move

Structure evaluation across three layers, not one:

**1. End-to-end task completion** — Did the agent complete the task correctly? Use deterministic assertions for exact outcomes (tool names called, parameters passed, final state reached). Use LLM-as-a-judge for context-dependent quality (tone, relevance, helpfulness).

**2. Trajectory evaluation** — Was the path correct and efficient? Track tool-call counts, retry loops, planning steps, and handoffs. An agent that's right but takes 47 tool calls is still a production failure. AgentEvals scores trajectories from OpenTelemetry traces against golden eval sets (strict, unordered, subset, or supermatch modes). Microsoft Foundry converts production traces into evaluation datasets for this purpose.

**3. Component-level correctness** — Which specific part broke? Isolating failures to a specific tool, reasoning step, or handoff is what makes debugging tractable. Amazon's AI agent evaluation library operates across all three layers simultaneously, generating metrics for final output, individual agent components, and the agent's reasoning trace.

**4. Golden eval sets with adversarial cases** — Build a test suite of known failure modes before shipping: Unicode names (O'Brien, José, 北京), null values, empty fields, concurrent requests, and prompt injection attempts. Teams on HN report that unicode reliably passes through commercial firewalls that skip this step.

**5. Red-teaming as first-class eval** — Model adversarial intent, not just known attack signatures. Prompt injection is the highest-risk failure mode for agents that process external content, and it cannot be caught by pattern-matching.

**6. HitL periodic audits** — Even with full automation, schedule human review of agent trace subsets. Amazon uses this as a standard practice in their agent evaluation workflow: builders define rules for performance degradation alerts and schedule periodic human audits of trace subsets.

## Evidence

- **AWS ML Blog (Bai et al., Feb 2026):** Amazon's agent evaluation framework runs across three layers — final output metrics, component-level assessment of individual agent parts, and trajectory/process evaluation — with an automated workflow generating default and user-defined evaluation metrics, S3-backed result storage, and human-in-the-loop periodic audits. S3 dashboard visualizes agent trace observability alongside evaluation results. — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/

- **Hacker News (ID 47325105, ~4 months ago):** Community discussion on agent testing surfaced 7 core failure modes: hallucination under unexpected inputs, edge case collapse (unicode names, nulls, empty fields), prompt injection, context limit surprises, over-trust in tool outputs, cascading failures, and false task completion. The $47,000 fraudulent refund via prompt injection (January 2026) was cited as a documented incident. — https://news.ycombinator.com/item?id=47325105

- **Confident AI (Jun 2026):** LLM agents are harder to evaluate than regular LLM applications because every plan, tool call, reasoning step, and handoff can change the outcome. Core metrics span task completion, step efficiency, argument correctness, tool correctness, plan adherence, plan quality, reasoning quality, answer relevancy, faithfulness, safety, latency, and cost. Tracing ties each score back to the span that produced it. — https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide

- **ODSEA CTO post (May 2026):** After evaluating LangGraph, CrewAI, and AutoGen in production conditions, LangGraph has the strongest documented production record (Klarna, LinkedIn, Uber, Elastic, Replit, 90M+ monthly downloads). AutoGen is in maintenance mode, CrewAI lacks verified production deployments. Framework choice affects evaluation surface area — LangGraph's graph-based architecture with checkpoint/resume primitives (stateful rollbacks) makes failure recovery testable in ways that linear chains cannot. — https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production

## Gotchas

- **Offline evals miss production failures.** A held-out benchmark and a final-answer pass/fail cannot capture trajectory quality, tool-call correctness, looping behavior, or recovery. You need production traces feeding back into eval sets.
- **Context window dynamics are invisible in small eval sets.** An agent that works at 95% context fills up and silently misbehaves at 100% — no error, no exception. Test at context limits, not just typical inputs.
- **Non-determinism makes small eval sets statistically meaningless.** 20 test runs of a non-deterministic agent give you no meaningful confidence interval. Use trajectory matching and golden eval sets that evaluate the *structure* of behavior, not just the outcome.
- **Framework choice shapes what's testable.** LangGraph's checkpointing primitives make stateful rollback testable. Linear chains don't expose retry or recovery paths until production. Evaluate the failure recovery path, not just the happy path.
- **LLM-as-a-judge introduces judge bias.** A model evaluating another model's output can be wrong in correlated ways. Use deterministic checks wherever possible; reserve LLM-as-judge for context-dependent criteria where ground truth is unavailable.
