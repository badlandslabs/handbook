# S-1172 · The Agent Eval Harness Stack — When Your Agent Scores 97% on Benchmarks and Explodes in Production

Your agent scores 97% on your internal eval suite. You ship it. Within a week you've had a duplicate refund, an agent that skipped an approval gate, and a support escalation where the agent confidently fabricated a customer ID. Your eval suite missed all of them because it was testing whether the final answer was right, not whether the agent did the right thing to get there.

## Forces

- **Benchmarks test capability. Production tests reliability.** SWE-bench, GAIA, and MMLU validate what an agent can do in controlled conditions. They don't test whether it will call the right tool, with the right parameters, in the right order, every time — or whether a retry produces duplicate side effects.
- **Offline evals have a sampling bias.** You test prompts you thought of, inputs that look reasonable, tool schemas that match your documentation. Production users ask questions you never imagined, in formats you didn't anticipate, hitting APIs that return schemas you haven't seen.
- **Agent traces have dimensions benchmarks don't measure.** Tool call sequence correctness, parameter validity, idempotency under retry, approval gate compliance, and cost-per-task all require instrumentation that's absent from standard eval frameworks.

## The Move

Build an **agent eval harness**: a test suite that runs realistic task scenarios against your agent, asserts expected traces and behaviors (not just final outputs), and gates deployment on harness results. It sits between offline benchmarks and production monitoring — catching the failure modes neither can.

### The four harness layers

1. **Behavioral assertions on traces.** Write code-level assertions over agent execution traces: `assert tool_sequence == ["lookup_customer", "check_policy", "draft_reply"]`, `assert "refund" not in tool_calls or approval_gate_triggered == True`. These catch wrong-tool selection, parameter hallucination, and skipped steps that produce correct-looking answers via broken paths.

2. **Idempotency regression tests.** Run the same task twice with identical inputs. Assert zero duplicate side effects (no two emails, two refunds, two DB writes). Agents that retry on failure often re-execute the final action instead of resuming from the failure point — this is invisible without a replay test.

3. **Approval gate audit.** If your agent has human-in-the-loop checkpoints, test that they actually fire. Run scenarios calibrated to trigger every gate, assert the agent pauses and surfaces a human decision before proceeding. A gating mechanism that silently skips because the model was "confident enough" is a compliance and safety gap.

4. **Cost-per-task regression baseline.** Track median and P95 cost per task type in staging. Set a deployment gate: if swapping a model or changing a prompt increases cost-per-task by >20% without outcome improvement, block the deploy. Cost regressions are often the first signal of a prompt regression or model degradation — before quality metrics surface it.

### Harness trigger points

- **On every model change:** run the full harness against both old and new model; block if new model has more trace violations or higher cost-per-task.
- **On every prompt/tool change:** run the relevant task subset; assert the change didn't introduce new tool calls or alter sequences.
- **On a schedule (nightly):** catch silent regressions that emerge from upstream API changes (schema drift, new response formats).

## Evidence

- **Company engineering post (PrismBase, July 2026):** "Agent Evaluation Harnesses: How to Test Agents Before Production" — details the four failure modes unit tests and chatbot evals miss: wrong tool selection, parameter hallucination, duplicate side effects on retry, and silent approval gate skips. Recommends trace-level assertions as the corrective pattern. — [prismbase.ai/insights/agent-evaluation-harnesses-production](https://www.prismbase.ai/insights/agent-evaluation-harnesses-production)
- **Blog post (TuringPulse, 2026):** "Safe Agent Deployments" — documents how standard Kubernetes health checks mark catastrophically degraded agents as healthy because they return HTTP 200 with well-formed JSON. Proposes shadow mode (parallel execution, logged-only responses) and canary rollouts with behavioral diff alerts as the production-grade alternative. — [turingpulse.ai/blog/safe-agent-deployments](https://turingpulse.ai/blog/safe-agent-deployments)
- **Blog post (Nexus, April 2026):** "Tracking Token Costs for AI Agents in Production" — a single 3-second trace costs between $0.001 and $0.15 depending on model and prompt. Recommends recording token usage as span metadata on every LLM call, aggregating by agent ID, and alerting on cost-per-task spikes as a leading indicator of regressions. — [nexus.keylightdigital.dev/blog/ai-agent-token-cost-tracking](https://nexus.keylightdigital.dev/blog/ai-agent-token-cost-tracking)

## Gotchas

- **Writing good trace assertions requires reading traces first.** Before writing assertions, instrument your agent to emit structured traces (tool name, parameters, timestamps, intermediate outputs). Without this, you have nothing to assert against.
- **Over-asserting kills flexibility.** Assert on the properties that matter (sequence correctness, parameter validity, no duplicate side effects) without asserting on phrasing, word choice, or intermediate reasoning. Over-specification makes the harness brittle and causes false failures on benign model updates.
- **The harness doesn't replace production monitoring.** A harness catches known failure modes. Production surfaces the ones you haven't thought of yet. Run both: harness as a gate, production monitoring as a signal for new test cases.
