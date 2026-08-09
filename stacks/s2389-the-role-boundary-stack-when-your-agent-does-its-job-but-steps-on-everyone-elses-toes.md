# S-2389 · The Role Boundary Stack — When Your Agent Does Its Job But Steps on Everyone Else's Toes

You have a multi-agent system. The planner writes the spec, the researcher gathers data, the coder produces the artifact, and the reviewer validates it. By every internal metric, each agent does its job. But the system produces outputs no single agent would have produced — spec drift, cross-contaminated context, and artifacts that reflect negotiation between agents rather than intent. Role assignments created the agents. Nobody defined the boundaries between them.

## Forces

- **Agents share context but not intent.** When the planner's reasoning is visible to the coder, the coder subtly defers to it rather than treating the spec as a constraint. This is tool-use contamination: the artifact reflects the planner's framing, not the user's goal.
- **Authority conflicts outlast role definitions.** The reviewer fails the coder's output. The coder argues back. In a multi-agent loop, this oscillation can iterate indefinitely unless you hard-wire a termination condition. Most teams discover this when their agent runs 47 iterations on a failed review.
- **Tool permissions are not scope boundaries.** Giving an agent the "right tools" doesn't prevent it from calling tools it shouldn't. An executor with file I/O + code exec + browser access will use all three when the situation feels ambiguous — which is most situations.
- **Context contamination is invisible until it isn't.** When agents share a scratchpad or message history, each agent reads not just the output of prior agents but their reasoning traces. Plausible intermediate conclusions get treated as constraints. The final output is a consensus of the pipeline, not the task.
- **Boundary bleed scales with role similarity.** Agents with overlapping toolkits and similar system prompts gradually converge on the same decision patterns. You don't get the diversity you designed for — you get a committee of clones.

## The move

Define explicit scope boundaries as code, not as system prompt prose:

- **List tools per role, then enforce the list at routing time, not at the prompt level.** The reviewer gets exactly one tool (structured output validation). If the router tries to send a code-fix request to the reviewer, it errors at routing, not at execution.
- **Separate reasoning traces from outputs.** Agents produce artifacts and reasoning. Only artifacts enter the shared context pipeline. Reasoning traces are private scratchpads, never read by downstream agents unless explicitly requested by the orchestrator.
- **Make authority explicit and directional.** The reviewer's output is a verdict, not a suggestion. If the verdict is "fail," the coder receives a specific failure signal with a delta — not a general "try again." The coder does not negotiate; it fixes or escalates.
- **Add a kill-switch at each role transition.** After N iterations of a loop (e.g., coder → reviewer → coder), escalate to a supervisor agent that re-evaluates the original goal, not the current state of negotiation.
- **Document what each role does NOT touch.** The researcher does not produce artifacts. The reviewer does not generate alternatives. These negative constraints catch more errors than the positive tool lists.

## Evidence

- **GitHub repo:** kavin14/multi-agent-workflow — a LangGraph StateGraph pipeline with a four-role schema (Planner/Researcher/Coder/Reviewer) that explicitly lists tools per role in a table. The researcher gets Tavily search + extract only; the coder gets code exec + file I/O only; the reviewer gets structured output validation only. The README notes this separation prevents role drift in longer pipelines. — [https://github.com/kavin14/multi-agent-workflow](https://github.com/kavin14/multi-agent-workflow)
- **GitHub repo:** CrewAI framework — defines agent roles through three fields: role, goal, and backstory. The framework enforces that agents with the same role automatically get similar tool permissions, making role similarity a detectable risk. Production users on r/LangChain report that teams using CrewAI's default role templates get role convergence within 2–3 sprints; the workaround is custom toolkits with explicit tool-level whitelisting per agent. — [https://github.com/joaomdmoura/crewAI](https://github.com/joaomdmoura/crewAI)
- **Reddit r/LLMDevs:** A thread about skeptical-critic agents catching planner hallucinations — the finding is that a dedicated critic agent with no production tools (only a model and a structured output schema) catches planner reasoning errors that the planner itself won't surface. The key design insight: the critic has zero tool access, which forces it to work only from the artifact, not from the planner's reasoning trace. This prevents the critic from deferring to the planner's framing. — [https://www.reddit.com/r/LLMDevs/comments/1rizhc2/](https://www.reddit.com/r/LLMDevs/comments/1rizhc2/)

## Gotchas

- **System prompt role descriptions drift.** After a few agent updates, the planner's system prompt no longer reflects what the planner actually does. The tool routing is still correct; the reasoning is not. Re-audit role descriptions quarterly, not just tool lists.
- **Orchestrator authority is under-specified.** The supervisor agent is usually the weakest link in a multi-agent design — it has the most context but the fewest tools, and its "re-evaluate the goal" instruction is usually prose, not a structured decision tree. Without a clear escalation schema, supervisors become bottlenecks.
- **Context window allocation between roles is a hidden bottleneck.** If the reviewer runs in the same context window as the coder, the full history is visible. If the reviewer runs in a fresh context with only the artifact, it catches different errors — less context about intent, more focus on the artifact itself. Both modes are valid; teams rarely decide consciously which they want.
