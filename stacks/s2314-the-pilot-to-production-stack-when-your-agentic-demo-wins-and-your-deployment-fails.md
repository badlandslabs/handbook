# S-2314 · The Pilot-to-Production Stack — When Your Agentic Demo Wins and Your Deployment Fails

Your pilot was flawless. The executive demo landed. Your agent read invoices, queried databases, and drafted responses in a controlled sandbox. Six weeks into production, it's returning hallucinated table names, misrouting requests to the wrong downstream system, and nobody can trace why the billing agent approved a $47,000 charge. The demo wasn't lying — it was measuring the wrong distribution. This is the pilot-to-production gap: the architectural distance between an agent that works in a curated environment and one that survives real-world scale, noisy data, and organizational complexity.

## Forces

- **Pilots run on curated data; production runs on adversarial distribution.** Pilot environments use clean inputs, stable tool responses, and predictable user intent. Real users provide typos, ambiguous requests, missing fields, and inputs that the agent has never seen. The agent's behavior in the pilot was correct; the distribution it was tested against was not representative.
- **Enterprise workflows are not agent-native — they were designed for humans.** Agents bolted onto human-designed workflows inherit implicit assumptions: humans check before deleting, ask clarifying questions when confused, and maintain institutional memory. Agents skip these steps by default. The architectural fix requires rethinking the workflow, not just the agent.
- **60–70% of agentic pilots fail to reach production** (Deloitte, NVIDIA 2026). Gartner projects 40%+ of agentic AI projects will be cancelled by 2027. The failure mode is not the model — models perform as expected. The failure is the integration layer: missing error handling, ungoverned tool access, unmonitored cost accumulation, and no rollback path when the agent misbehaves.
- **Pilot success metrics don't translate.** Demo success is measured by whether the agent can complete the task. Production success requires measuring how it fails, how often, at what cost, and whether failures are recoverable. These are different measurement frameworks entirely.
- **Governance and safety requirements only become visible in production.** Pilot environments skip compliance checks, audit logging, and approval workflows. When the agent goes live, it encounters authorization gates, data residency constraints, and policy enforcement points it never encountered during development.

## The move

The pilot-to-production stack is a **five-phase architectural migration** that closes the gap before it closes your project:

### Phase 1 — Production-infrastructure-first agent design

Design the agent for production failure modes, not demo success. This means:

- **Instrument before you deploy.** Add OpenTelemetry tracing with `gen_ai.*` semantic conventions at every LLM call, tool invocation, and decision branch. Without per-span token accounting, you cannot answer "which step caused the cost spike." Langfuse, Arize Phoenix, or Honeycomb provide production-grade backends.
- **Build a dead-letter queue for failures.** Every agent action should have a defined failure path that routes to human review rather than silently degrading. Tool call failures, confidence drops below threshold, and ambiguity flags should land in a queue, not a void.
- **Cost attribution from day one.** Tag every agent request with a cost center, task type, and caller identity. MintMCP (2026) documented a single runaway loop generating $47,000 in charges — preventable with request tagging and rolling budget alerts at 75%/90%/100% thresholds.

### Phase 2 — Schema-gated tool access

- **Pin tool schemas at lock time.** MCP servers can change tool definitions at runtime. Pin the tool manifest (name, parameters, return schema) at the version your agent was tested against. Any drift between the pinned schema and the live tool should trigger a re-eval gate, not a silent failure.
- **Response sanitization before context injection.** Every MCP tool response is simultaneously data (consumed by the agent) and a potential instruction injection vector. Sandblast the output before it enters the context window: strip non-schema fields, type-validate return values, and reject responses that don't conform to the expected contract.
- **Egress filtering.** Production agents need outbound network restrictions. A code-execution agent should not be able to reach external APIs it doesn't own. Least-privilege egress is not optional — it's the difference between a sandboxed failure and a data exfiltration incident.

### Phase 3 — Multi-agent boundary hardening

- **Typed handoff contracts.** Agents in a multi-agent pipeline must exchange structured artifacts, not prose. Define the schema of each inter-agent message: task input, expected output shape, validation rules, and status enum. An agent receiving a task should validate the contract before acting on it.
- **State consensus before action.** Two agents operating on shared state need a mechanism to agree on the current state before either acts. Optimistic locking with a version header, or a delivery-log that reconstructs read-sets from HTTP middleware, prevents the divergence that looks like hallucination but is actually a race condition.
- **Trace context propagation.** Propagate W3C trace context across agent-to-agent boundaries so that a single trace ID chains all agent invocations together. Without this, debugging a cross-agent failure means correlating logs by hand.

### Phase 4 — Production eval harness (PAEF-aligned)

- **Continuous evaluation on live traffic.** PAEF (Production Agentic Evaluation Framework, arXiv:2605.01604, Pandey 2026) proposes five dimensions: task completion, trajectory safety, cost efficiency, behavioral consistency, and failure recoverability. Run lightweight eval probes on a sampled slice of production requests — not just on your curated benchmark.
- **Track drift, not just accuracy.** Production drift (S-1062) is when your lab evals pass but your production trajectory degrades silently. Measure trajectory-level scores over rolling windows. Alert on sustained degradation, not just individual failures.
- **Regression gates on behavioral change.** Every agent update should be evaluated against the last 100 production trajectories before deployment. A new model version that improves benchmark scores but degrades on your specific task mix should not ship.

### Phase 5 — Rollback and human-override infrastructure

- **Deterministic session restore.** Agent sessions should be resumable from a checkpoint, not from scratch. Store the conversation state, tool-call history, and intermediate artifacts in a durable store. On failure or rollback, resume from the last validated checkpoint rather than losing the session.
- **HITL escalation tier.** Define stakes thresholds: low-stakes tasks execute autonomously, medium-stakes require human acknowledgment, high-stakes require explicit human approval. The escalation friction is a feature — it forces you to articulate what "high stakes" means for your domain, which is itself a governance act.
- **Runbooks as code.** Document every failure mode with a corresponding automated response. A runbook that requires a human to read and execute is not a runbook — it is a hope. Automated rollback triggers, re-eval gates, and notification workflows replace hope with reliability.

```python
# Production agent wrapper with dead-letter routing
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)

class ProductionAgent:
    def __init__(self, agent, dlq_client, cost_tracker, eval_store):
        self.agent = agent
        self.dlq = dlq_client  # dead-letter queue
        self.cost = cost_tracker
        self.eval = eval_store

    async def run(self, request: AgentRequest) -> AgentResponse:
        ctx = trace.get_current_span()
        ctx.set_attribute("request.cost_center", request.cost_center)
        ctx.set_attribute("request.task_type", request.task_type)

        # budget gate
        if self.cost.rolling_cost(request.cost_center) >= self.cost.threshold_pct(0.75):
            ctx.set_attribute("execution.gate", "budget_warning")
            await self._alert_ops(request.cost_center, "75% budget threshold")

        try:
            response = await self.agent.execute(request.task, request.context)

            # confidence gate — route ambiguous outputs to DLQ
            if response.confidence < 0.70:
                await self.dlq.enqueue({
                    "type": "confidence_threshold",
                    "request": request,
                    "response": response,
                    "confidence": response.confidence,
                    "trace_id": ctx.get_span_context().trace_id,
                })
                ctx.set_attribute("execution.outcome", "dlq_routed")
                return response

            # store eval sample
            await self.eval.record(request, response)
            return response

        except ToolCallError as e:
            await self.dlq.enqueue({
                "type": "tool_failure",
                "request": request,
                "error": str(e),
                "trace_id": ctx.get_span_context().trace_id,
            })
            ctx.set_status(Status(StatusCode.ERROR, str(e)))
            raise

        except Exception as e:
            ctx.set_status(Status(StatusCode.ERROR, str(e)))
            ctx.record_exception(e)
            await self.dlq.enqueue({
                "type": "unhandled",
                "request": request,
                "error": str(e),
                "trace_id": ctx.get_span_context().trace_id,
            })
            raise
```

## Receipt

> Receipt pending — 2026-08-08. The above code pattern is synthesized from production agent patterns documented in Stack Pulsar (Jun 2026), Red Hat OpenTelemetry guide (Apr 2026), and LangChain Agent Development Lifecycle documentation (2026). The specific wrapper interface is illustrative; adapt the `dlq_client`, `cost_tracker`, and `eval_store` interfaces to your infrastructure. The 0.70 confidence threshold and 75% budget threshold are starting values — calibrate against your domain's actual distribution.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — typed handoff contracts and state consensus
- [S-1062 · The Production Drift Stack](s1062-the-production-drift-stack-when-your-lab-evals-pass-and-your-production-fails-silently.md) — trajectory-level monitoring and silent degradation
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — production monitoring and SLO framing for agents
- [S-1053 · The Evaluation Gap Stack](s1053-the-evaluation-gap-stack-when-your-agent-passes-all-tests-and-still-fails-in-production.md) — static benchmarks vs. production requirements
