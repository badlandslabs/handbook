# S-2125 · The AgentOps Platform Stack — When Your Framework Lock-In Decides Your Debugging Capabilities

You shipped an agent to production. It failed silently three times last week. Without a trace, you know only that something went wrong — not which step, not which tool, not which model call burned 80% of your latency budget. Agent observability platforms promise to close this gap. But the platform you choose determines what you can and cannot debug, and that choice is made earlier — during framework selection — than most teams realize.

## Forces

- **Agent failures are trajectory failures.** Traditional LLM observability tracks single calls. Agent observability must capture branching, looping, backtracking, and multi-turn state — a fundamentally different data structure.
- **Platform choice is made at framework selection, not later.** LangSmith ships with LangChain/LangGraph. Switching observability platforms mid-production means re-instrumenting every agent. Most teams choose their platform by default, not by evaluation.
- **Scaffolding depth varies wildly.** The same agent can score 11–15 points differently on benchmark tasks depending on its scaffold — the tracing layer is part of that scaffold. What you capture determines what you can debug.
- **Cost attribution is a first-class concern.** A single agent run can make 50+ LLM calls. Per-run cost visibility is not optional at production scale.
- **Eval integration must be native.** Spot-checking traces by hand does not scale. The platform must support LLM-as-judge evaluation, golden dataset regression, and automated trigger-on-deploy.

## The move

### Step 1 — Know what you are choosing between

The four dominant platforms occupy distinct architectural positions:

| Platform | Framework coupling | Self-host | Primary appeal | Latency overhead |
|----------|-------------------|-----------|----------------|-----------------|
| **LangSmith** | Tight (LangChain/LangGraph) | Enterprise only | Deep LangGraph trace fidelity, built-in eval | ~2–5ms |
| **Langfuse** | None (OTel-native) | Yes (MIT) | Framework-agnostic, self-hostable | ~3–8ms |
| **Helicone** | None (HTTP proxy) | Yes | One-line integration, no code change | ~1–3ms |
| **Arize/Phoenix** | None (OTel) | Phoenix free | ML-flavored analytics, embedding quality | ~5–15ms |

### Step 2 — Evaluate on five axes that actually matter for agents

**Axis 1: Trace hierarchy fidelity.** Can the platform represent a trace where the agent loops, backtracks, calls a sub-agent, and resumes? Some platforms flatten this to a linear list. LangSmith's LangGraph integration natively understands state snapshots. Langfuse supports nested spans with custom metadata. Helicone is optimized for single-request capture.

**Axis 2: Semantic correctness evaluation.** Latency and error rate are green/健康. Semantic correctness — did the agent pick the right tool, with the right args, producing the right outcome — is not. The platform needs LLM-as-judge evaluation with configurable rubrics, or you will be manually reviewing traces forever.

**Axis 3: Production eval trigger.** Can it run evaluations automatically on every deploy? LangSmith has native eval runs triggered by dataset updates. Langfuse supports evaluation datasets and model-level scoring. Helicone is primarily a capture tool, not an eval platform.

**Axis 4: Self-hosting and data residency.** If your agent handles EU user data, your traces cannot leave EU jurisdiction. LangSmith SaaS does not currently guarantee data residency. Langfuse self-hosted is the only option in this group that gives you full data control with the same feature parity.

**Axis 5: Cost at scale.** At 100M traces/month: Helicone ~$1.5K–3K, Langfuse ~$2K–4K, LangSmith ~$4K–8K. Self-hosting costs are infrastructure-bound (ECS + S3 + Postgres) and break even around 50–100M events/month depending on your cloud provider.

### Step 3 — Match platform to context

**Use LangSmith when:** You are building on LangGraph, you need deep trace fidelity for complex stateful agents, you want built-in eval runs without extra integration work, and SaaS pricing is acceptable. The tight LangGraph integration means LangSmith understands LangGraph node boundaries, checkpoint saves, and conditional edges natively.

**Use Langfuse when:** You need framework independence, self-hosting for compliance, or you want to own your trace schema. Langfuse's OpenTelemetry native design means any agent — CrewAI, custom, AutoGen, raw API — emits the same trace structure. Self-hosted Langfuse on a single VPS handles ~10M events/month comfortably.

**Use Helicone when:** You need the fastest time-to-value on a greenfield project and want to capture LLM API call traces without changing your code. The HTTP proxy approach means zero instrumentation code. The tradeoff: limited to HTTP-call-level traces; you cannot see internal agent state, tool argument parsing, or sub-agent orchestration.

**Use Arize/Phoenix when:** Your team has existing ML observability infrastructure, you need embedding quality analysis for RAG-heavy agents, or you want to correlate agent performance with upstream data distribution shifts. Phoenix is free and self-hosted. The ML-ops depth is higher than the other three; the agent-specific ergonomics are lower.

### Step 4 — Instrument before you need it

Do not instrument after the first production incident. Add tracing to every agent at the MVP stage, even if the traces are going nowhere. The cost is minimal (a callback or OTel exporter), the schema decisions made early persist, and you have baseline traces to compare against when things break.

```python
# Langfuse — instrument any agent with OTel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from langfuse.opentelemetry import LangfuseSpanExporter

provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(LangfuseSpanExporter())
)
trace.set_tracer_provider(provider)

# Every agent tool call is now a named span
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("tool_execute") as span:
    span.set_attribute("tool.name", tool_name)
    span.set_attribute("agent.step", step_number)
    span.set_attribute("run.id", run_context.run_id)
    result = tool.execute(**tool_args)
    span.set_attribute("tool.success", result is not None)
    span.set_attribute("output.tokens", estimate_tokens(result))
```

### Step 5 — Define your semantic exit gate

Not every trace matters equally. Define the one invariant per tool that, if violated, means the tool output is wrong regardless of whether it errored. Log a structured `tool_verdict` field on every span:

```python
# Example: semantic verdict for a file-write tool
{
    "span": "tool_execute",
    "tool": "write_file",
    "path": "/app/reports/weekly.csv",
    "semantic_verdict": "PASS",
    "invariant_checked": "row_count >= input_row_count",
    "actual_rows": 847,
    "expected_min": 847,
    "verdict_reason": "rows preserved"
}
```

Platforms that surface these verdict fields in their trace UI let you filter runs by semantic correctness, not just error status.

## Receipt
> Verified 2026-08-04 — Sources: aiagentrank.io "AI Agent Observability 2026" (May 2026, live extraction), geodocs.dev "Langfuse vs LangSmith vs Helicone" (live extraction), techstackvs.com "LangSmith vs Langfuse vs Helicone" (live extraction), particula.tech "Helicone vs Langfuse vs LangSmith pricing" (live extraction), Langfuse OpenTelemetry documentation (langfuse.com, live extraction). Benchmark gap stat: AlphaEval arXiv:2604.12162 (best agent scores 64.41/100, scaffold variance 11–15 points). Platform pricing at 100M traces: Helicone $1.5K–3K, Langfuse $2K–4K, LangSmith $4K–8K. Langfuse self-hosting: single VPS handles ~10M events/month (documented on langfuse.com/docs). LangSmith integration requires LangGraph/LangChain; alternative frameworks need custom instrumentation. All claims traceable to cited sources.

## See also
- [S-760 · Agent Flight Recorder](/stacks/s760-agent-flight-recorder-the-tamper-evident-audit-log-for-autonomous-systems.md) — tamper-evident logging requirements that complement observability platforms
- [S-193 · LLM-as-Judge Eval Pipeline](/stacks/s193-llm-as-judge-eval-pipeline.md) — eval methodology you wire into your observability platform
- [S-246 · Production Eval Pipeline](/stacks/s246-production-eval-pipeline-the-four-stage-loop.md) — the continuous eval loop your traces should trigger
- [S-2124 · Permission Inheritance Stack](/stacks/s2124-the-permission-inheritance-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — permission violations that observability traces should surface early
