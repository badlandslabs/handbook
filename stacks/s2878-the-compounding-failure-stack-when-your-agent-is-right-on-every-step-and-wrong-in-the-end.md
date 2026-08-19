# S-2878 · The Compounding Failure Stack — When Your Agent Is Right on Every Step and Wrong in the End

Your agent completes 95% of steps correctly. Your monitoring shows green. Then you discover that end-to-end task accuracy is 70% — because each step's output becomes the next step's input, and errors compound multiplicatively across the trajectory. The loop looks healthy. The result is wrong. Nobody catches it until the user does.

## Forces

- **A correct step does not mean a correct trajectory.** Agents fail in sequence, not in isolation. A bad decision at step 3 corrupts step 4's input, which corrupts step 5's reasoning, until the final output is confidently wrong. Traditional output-only evals pass every intermediate smoke test and miss the cascade.
- **Agents don't naturally signal that they're stuck.** Unlike traditional software that throws exceptions, agents "keep trying" — generating plausible next steps that compound the error. The model is designed to produce a continuation, not a halt. Without explicit harness enforcement, there is no natural exit.
- **Observability tells you the loop ran; evaluation tells you whether it was worth running.** Teams confuse uptime monitoring with quality monitoring. Traces show what happened; they don't show whether the outcome was correct. A trajectory can be perfectly formed and entirely wrong.
- **Harness defects cause most agent failures, not model failures.** One survey of enterprise AI production incidents found 65% traced to harness defects (loop guards, context policy, tool gates, budget enforcement) rather than model capability. The model was fine; the infrastructure around it was the problem.
- **Multi-agent pipelines amplify compounding error.** In "bag of agents" topologies, one agent's mistake becomes the next agent's input with no validation at merge points. Errors don't just compound — they decorrelate in ways that make debugging harder.

## The move

Build a failure-aware harness that detects, contains, diagnoses, and recovers from errors before they compound across the trajectory.

### 1. Instrument step-level failure detection, not just end-state checks

The unit of agent failure is the step, not the session. Catch degradation at the step level:

- **Loop detection**: Flag when the same tool is called with identical arguments within N steps (e.g., 3). Flag alternating A→B→A→B patterns. This is deterministic — no LLM needed.
- **Cost slope monitoring**: Track cost-per-step. If the last 5 steps consumed more than 3× the cost of the first 5, something is looping or spinning. Alert and halt.
- **Stop-reason anomaly detection**: Surface when the model returns unusual `stop_reason` values (e.g., `length` truncation in the middle of a reasoning chain) that suggest context overflow or token budget issues.
- **Step budget enforcement**: Set a hard maximum on steps per trajectory (e.g., 20). This is the single highest-ROI harness addition — it prevents the $47,000 eleven-day loop incident.

### 2. Build trajectory-level invariants as deterministic checks

Define what a correct trajectory looks like structurally, separate from whether the output is "good":

- **Tool ordering constraints**: If `verify_identity` must precede `issue_refund` in a refund agent, assert this order in the harness — not in the prompt. Prompts fail silently; assertions fail loudly.
- **Required tool execution**: Assert that certain tools run at least once in a trajectory (e.g., `confirm_user_intent` before any destructive action).
- **Output schema validation**: Check that each tool's output conforms to the expected schema before it is passed to the next step. Schema violations at tool boundaries are a primary failure vector.
- **Goal-pinning checks**: Periodically re-read the original user intent against the current step's reasoning. If the agent is 8 steps in and the current action has no path back to the original goal, catch it.

### 3. Contain failures before they propagate

- **Circuit breakers**: If a tool call fails N times in a row, stop retrying and escalate or halt. Exponential backoff on retries is not enough — you need a hard stop.
- **Write-tool revocation**: If the agent exceeds step budget or enters a loop, revoke write tool permissions immediately. Read-only containment prevents data destruction.
- **Output quarantine**: If a tool returns unexpected output (wrong schema, suspiciously empty, format changed), don't pass it to the next step. Route to a human review queue instead.

### 4. Close the feedback loop: production failures → eval cases

Every production failure should produce a new test case. This is the mechanism by which harness quality compounds:

1. Catch the failure in production (via monitoring, user complaint, or alert)
2. Reconstruct the full trajectory trace (requires session replay capability — no replay means blind fixing)
3. Add the failure case to the versioned eval dataset
4. Run the eval suite; assert the failure mode is now caught
5. Verify the fix before the next deploy

Without this loop, you fix bugs with one-off prompt edits that don't generalize. With it, each production failure makes the eval suite more representative and the next failure more likely to be caught.

### 5. Use staged evaluation gates, not a single pass/fail

Evaluate agents at multiple layers of the stack:

| Layer | What it catches | How |
|---|---|---|
| **Component** | Individual tool calls, argument correctness | Deterministic checks |
| **Trajectory** | Step ordering, required steps, loop detection | Assert-based harness |
| **Outcome** | Did the task actually complete correctly? | LLM-as-judge or human review |
| **Regression** | Did a change break what was working? | CI against versioned golden dataset |

Answer-only evals (checking only final output) are a smoke test. Trajectory evals catch the failure mode that answer-only misses: a correct-looking answer produced via a broken reasoning chain.

## Evidence

- **Engineering blog:** The $47,000 loop incident — four LangChain agents ran 11 days with no per-agent budget cap, alternating between content generation and analysis requests. No termination mechanism. No step budget. Cost tracked only after the invoice arrived. — [Rahul Kashyap, "Harness Failure Modes" (May 2026)](https://rahulkashyap.dev/blog/harness-failure-modes.html)
- **Industry survey:** 65% of enterprise AI production failures trace to harness defects (context drift, schema misalignment, state degradation) rather than model capability. Teams instinctively reach for prompt changes or model swaps; the model is usually fine. — [Rahul Kashyap, "Harness Failure Modes" (May 2026)](https://rahulkashyap.dev/blog/harness-failure-modes.html)
- **Production case study:** An agent reporting "95% task completion" was found to have only 70% actual correctness when outputs were properly evaluated. Step-level success masks trajectory-level error compounding. — [Vindler Blog, "Agent Evaluation at Scale: Lessons from 2025's Production Failures" (Dec 2025)](https://vindler.solutions/blog/agent-evaluation-at-scale)
- **Engineering post:** "Answer-only evals catch total breakage and miss everything else." Trajectory evaluation catches the specific failure mode where `lookup_order → issue_refund → final_answer` passes answer-only checks but fails because `verify_identity` was never called. — [Slava Dubrov, "AI Agent Evaluation in Production: Traces to Test Suites" (Jun 2026)](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)
- **LangChain survey (1,340 respondents, late 2025):** 57.3% have agents in production; 32% cite quality as the primary production blocker. Of teams with some observability (89%), only 37.3% run online evals. The gap between monitoring and evaluation is where compounding failures hide. — [LangChain State of Agent Engineering Survey 2025](https://www.langchain.com/state-of-agent-engineering)

## Gotchas

- **Don't fix with prompts what needs fixing in the harness.** When a bad trajectory occurs, resist immediately editing the prompt or swapping models. Check loop guards, context policy, tool gates, and termination logic first. Most failures are infrastructure problems, not model problems.
- **LLM-as-judge needs calibration before you trust it.** Judges are good for outcome evaluation but unreliable for trajectory structural checks. Use deterministic assertions for tool ordering and loop detection; use judges only where interpretation is required. Calibrate judges against human-labeled samples before deploying them at scale.
- **Session replay is not optional for diagnosis.** If you cannot reconstruct the exact context state at step 17 of a failed trajectory, you will fix bugs by tweaking prompts blindly. Replay capability is harness engineering, not ML research.
- **Step budgets prevent catastrophes; they don't catch slow degradation.** A step budget stops the infinite loop, but a 12-step correct trajectory that delivers a subtly wrong answer still needs trajectory-level invariant checks. Budget + invariants are complementary.
- **Multi-agent pipelines need validation at merge points.** When two agents' outputs are combined as input to a third, validate the merged output's schema and content before it enters the next agent. Without merge-point checks, one agent's error silently becomes the next agent's assumption.
