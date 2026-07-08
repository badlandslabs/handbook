# S-817 · The Trajectory Eval Stack: Testing the Path, Not the Answer

Your agent passes every output check. The JSON is valid, the schema matches, the final response looks correct — and the agent skipped a mandatory database write, hit the same tool in an infinite loop, and routed through the wrong sub-agent. Output-only testing misses the failure mode that matters most in production: getting the right answer via the wrong path.

## Forces

- **The output is a red herring.** Standard eval frameworks — BLEU, ROUGE, exact-match string diff — score the final text. They cannot detect that the agent skipped a security check, called tools in the wrong order, or fell into a loop. In LangChain's State of Agent Engineering 2026 survey, 89% of teams have agent observability, but only 37.3% run online evals in production — leaving a 52-point gap where the most consequential failures hide.
- **Agents are state machines, not pipelines.** A traditional LLM app: prompt → response → check. An agent: prompt → N tool calls → M file reads → K command executions → state mutation → final output. The evaluation must span all of these.
- **The right answer via the wrong path is still a failure.** Skipping mandatory guardrails, bypassing authorization checks, or iterating 47 times to do what should take 3 — these are production incidents, not acceptable edge cases.

## The move

### 1. Capture the full transcript, not just the final output

Define evaluation atoms that match how your agent actually operates:

```
Task   = single test with defined inputs and success criteria
Trial  = one attempt at a task (run multiple for variance)
Grader = logic scoring an aspect of performance; contains assertions/checks
Transcript (trace/trajectory) = complete record: all tool calls, state mutations,
                                 intermediate results, reasoning steps
Outcome = final environment state after the trial
```

From Anthropic's eval framework (Jan 2026). The transcript is the ground truth of what the agent *did*, not just what it said.

### 2. Build a trajectory harness for your agent framework

Wrap your compiled agent in a harness that auto-detects state and captures execution traces:

```python
from fasteval_langgraph import harness

agent = build_support_agent()
graph = harness(agent)

result = await graph.chat(user_input="reset password for user 42")
# result = ChatResult(final_response, state, execution_trace)
```

Evaluate three things per trajectory:
- **Route correctness** — did the agent visit the right nodes?
- **Path completeness** — did it hit every required checkpoint?
- **Efficiency** — did it converge without looping?

A prompt tweak that improves output quality can simultaneously cause the agent to start hallucinating tool calls or skipping security nodes. Trajectory evaluation catches these regressions deterministically.

### 3. Layer deterministic assertions over tool-call mechanics

Control-plane evals verify that the *right machinery fired* — no model call required. Four deterministic assertions (from Dik Rana's Claude Code eval writeup, May 2026):

```python
# 1. Skill was invoked
assert "skill:code-review" in trace.skill_invocations

# 2. Correct MCP server was called
assert any("mcp_server_id:github" in tc for tc in trace.tool_calls)

# 3. Tool call sequence is valid (no skipped prerequisites)
assert trace.tool_calls == expected_sequence

# 4. No infinite loop (bounded step count)
assert len(trace.steps) <= MAX_ITERATIONS
```

These are fast, deterministic, and catch regressions that only show up under specific conditions.

### 4. Use LLM-as-judge for semantic dimensions the machine can't verify

Classifying content is simpler than generating it — this asymmetry lets smaller models verify outputs from larger ones. Stack two tiers:

| Tier | Model | Use case |
|------|-------|----------|
| **Fast inline gate** | Small distilled judge (Luna-2 3B, Prometheus 2 7B, Patronus Lynx 8B) | High-throughput inline checks, tone, relevance |
| **Deep verification** | Large proprietary (GPT-4o, Claude 3.7 Sonnet) | Low-scoring samples needing deeper analysis, safety, hallucination |

From Zylos Research (Apr 2026): 57%+ of production agent teams now use judge LLMs at runtime — not just in eval harnesses, but as load-bearing production infrastructure for quality gating and hallucination defense.

### 5. Grade the transcript at every tool boundary, not just at the end

Run graders after each tool call, not just at completion. Catch failures early:

```python
for step in transcript.tool_calls:
    grade_tool_selection(step)      # Did it pick the right tool?
    grade_intermediate_output(step) # Is the tool output valid?
    grade_state_mutation(step)      # Did state change correctly?
    if grade_tool_selection(step).score < 0.5:
        abort_early("Tool selection fell below threshold")
```

This is the difference between "eval at the end of a 3-hour run" and catching the failure after 30 seconds.

## Evidence

- **Anthropic Engineering Blog:** Defines the core taxonomy (task/trial/grader/transcript/outcome) and argues that "the capabilities that make agents useful — autonomy, intelligence, flexibility — also make them harder to evaluate." — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Medium (FastEval/LangGraph):** "If your agent gives the right answer but takes the wrong path — perhaps skipping a mandatory database check or hitting the same tool in an infinite loop — that is a critical failure." Documents the FastEval trajectory harness pattern for LangGraph agents. — [medium.com/@mohith0495/testing-langgraph-agents](https://medium.com/@mohith0495/testing-langgraph-agents-route-verification-and-trajectory-evaluation-with-fasteval-afb39f197a69)
- **Zylos Research:** "LLM-as-judge has crossed from evaluation harness territory into load-bearing production infrastructure." Documents the bifurcation into large proprietary judges vs. small distilled judges, with six distinct deployment patterns. — [zylos.ai/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/research/2026-04-10-llm-as-judge-production-agent-verification-2026)
- **Dik Rana / dikrana.dev:** "Observability ships in two days. Evals ship in two months: a corpus, ground truth, a harness, a regression discipline." Documents four deterministic control-plane assertions for Claude Code agents, sourced from LangChain State of Agent Engineering 2026. — [dikrana.dev/blog/claude-code-agent-evals](https://dikrana.dev/blog/claude-code-agent-evals)
- **Amazon AI Blog:** In multi-agent systems, HITL becomes critical because of "increased complexity and potential for unexpected emergent behaviors that automated metrics might fail to capture" — specifically inter-agent communication, coordination failures, and conflict resolution. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Promptfoo / Codex:** Documents trajectory assertions for Codex CLI agents — three dimensions: correctness (did it produce the right output?), trajectory (did it behave correctly en route?), and efficiency (what did it cost?). — [codex.danielvaughan.com/2026/04/11/evaluating-codex-agents-promptfoo-trajectory-assertions](https://codex.danielvaughan.com/2026/04/11/evaluating-codex-agents-promptfoo-trajectory-assertions)

## Gotchas

- **Output-only eval gives false confidence.** A passing final output check tells you nothing about the 47 tool calls, 12 state mutations, and 3 routing decisions that produced it. The path is where agents fail.
- **Intrinsic self-correction is unreliable.** Models cannot reliably check their own work without external grounding. A separate judge model — with its own context and no shared blind spots — catches failures the generating model misses.
- **Latency budget conflicts with thorough grading.** Running a full LLM-as-judge on every intermediate step destroys latency. Size your judge to the consequence: fast deterministic checks for the common case, slow deep verification for anomalies and production sampling.
- **Eval coverage decays.** Agents evolve; evals rot. Without regression gates in CI, a prompt update that passes the test set can silently degrade behavior on edge cases that weren't in the corpus. Treat evals as first-class CI citizens, not post-launch hygiene.
