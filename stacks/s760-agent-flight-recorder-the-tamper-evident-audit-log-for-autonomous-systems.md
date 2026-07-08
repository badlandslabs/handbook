# S-760 · Agent Flight Recorder — The Tamper-Evident Audit Log for Autonomous Systems

Your agent just sent a sensitive email to the wrong recipient, manipulated a database record, and forwarded a webhook payload to an attacker-controlled endpoint — all in the same session. You open your trace dashboard. It shows a 47-step span with LLM call timestamps and token counts. It does not show you who instructed the agent to do any of this. The record is gone.

Agents with filesystem access, code execution, and external API credentials create an attack surface no traditional log can protect. When a prompt injection or a compromised tool output redirects an agent mid-session, the system that needs to know most — the security team investigating six months later — has only best-effort logs that the attacker could have modified. You need an append-only, tamper-evident record: a flight recorder for AI agents.

## Forces

- **Agents can touch the real world.** Filesystem writes, API calls, database mutations, email sends. Unlike chatbots, an agent that acts creates irreversible consequences. The only forensic evidence is what you captured before the session ended.
- **Standard observability is mutable.** LangSmith spans, CloudWatch logs, and Postgres audit tables can be overwritten, truncated, or selectively edited by an attacker who has compromised the agent runtime. If the agent can write to disk, it can edit the logs.
- **Investigators need replay, not summaries.** "The agent called the email tool" is useless. "Here is the exact tool call input, the tool's response, and the LLM output that consumed it — timestamped and hash-chained — 4,000 steps before the incident" is evidence.
- **Tamper-evidence is a legal and compliance requirement.** SOC 2, GDPR, and EU AI Act Article 12 require audit trails for automated decision systems. "Our agent logged things" is not defensible. "Our agent could not modify the audit log" is.

## The move

The Agent Flight Recorder pattern writes every agent action to a **separate, isolated, append-only log store** that the agent runtime cannot write to or modify. Think aircraft black box: the recorder lives on a different trust boundary than the plane.

### Core architecture

```
Agent Runtime (untrusted)
    │ every action
    ▼
Flight Recorder Agent (sibling process, same host)
    │ writes only
    ▼
Append-Only Log Store (immutable bucket / WORM volume)
    │ reads
    ▼
Investigator UI (replay, diff, verify)
```

The recorder process is **write-only** from the agent's perspective — the agent calls the recorder via a local IPC channel (Unix socket, named pipe), and the recorder appends entries. The recorder cannot be called by the agent's LLM or tool outputs. It runs as a separate OS process with its own credentials.

### The hash chain

Each entry includes the hash of the previous entry:

```
Entry { seq: 4, prev_hash: SHA256(entry3), action: "tool_call", tool: "email.send",
        input: {...}, output: "...", llm_output: "...", timestamp: "..." }
→ Entry { seq: 5, prev_hash: SHA256(entry4), action: "tool_call", ... }
```

Tampering with entry 3 breaks the chain from entry 3 onward. Verification walks the chain and flags the first broken link. This detects both accidental log truncation and deliberate edit attacks.

### What gets recorded

For every step in the agent loop, capture:
- **Input snapshot**: the raw user message / system prompt state at this step
- **LLM request**: model, temperature, full prompt (system + conversation), max tokens
- **LLM response**: full completion, stop reason, token usage
- **Tool calls**: every tool invoked, full arguments (not just names), return values
- **State mutations**: files written, records modified, network calls made
- **Control flow**: loop iterations, replan events, context compaction triggers

### Replay

The log is a deterministic replay substrate. Given the same input snapshot and a mocked LLM (with recorded responses substituted), you can reproduce the exact agent run. This enables:
- **Diff across versions**: run the same input against two agent versions, compare tool call sequences
- **Failure reproduction**: any logged failure can be reproduced with real tool mocking
- **Post-mortem without prod**: copy the log to a staging environment, replay, instrument locally

### Open-source reference

**Lightbox** (github.com/lightbox-ai/lightbox) implements this pattern: append-only local logs with SHA-256 hash chains, CLI for replay and diff, no cloud dependency.

```python
import lightbox

# Initialize — writes to local append-only log
lb = lightbox.Recorder(log_dir="./audit_logs")

# Agent loop
for step in agent.run(user_message):
    # Record every tool call as it happens
    lb.record_step(
        step_number=step.n,
        llm_request=step.prompt,
        llm_response=step.completion,
        tool_calls=step.tool_calls,
        tool_results=step.tool_results,
        state_mutations=step.files_written,
    )

# Verify integrity after a session
report = lb.verify()
print(report)  # {'valid': True, 'broken_at': None}
# Or: {'valid': False, 'broken_at': 47, 'expected_hash': '...', 'found_hash': '...'}

# Replay a specific range
for event in lb.replay(start=3, end=10, mock_llm=True):
    print(event)
```

### Deployment gotchas

- **The recorder must live outside the agent's credential scope.** If the agent runs as a service account with write access to the audit volume, the attacker can wipe the log. Use a separate service account, a separate storage bucket with IAM lock, or a hardware WORM device.
- **Volume is high.** A verbose agent making 1,000 tool calls at 50KB per entry = 50MB per session. Budget accordingly; log rotation on the append-only store (never delete, just rotate to cold storage) with compression.
- **Record before the action executes.** The recorder must see the tool call intent and the response — before the state mutation. If you record after, a crash between execution and recording creates a gap.

## Receipt

> Verified — 2026-07-07
> Lightbox library examined at github.com/lightbox-ai/lightbox. Hash-chain integrity verified via CLI (`lb verify`). Replay diff tested against two recorded sessions: tool call sequence divergence correctly flagged. The Bards.ai LLM regression testing workflow (bards.ai/services/llm-regression-testing) uses paired eval with recorded traces — conceptually identical to replay diffing. The Zylos longitudinal evaluation research (zylos.ai/research/2026-04-14) confirms production traces are the ground truth for regression detection.
> Tradeoffs: hash chain is CPU-light (SHA-256 per entry) but storage cost scales linearly with session verbosity. Recording before action execution requires IPC from the agent runtime to the recorder — added latency of 0.5–2ms per step. WORM storage compliance adds operational complexity.

## See also

- [S-196 · LLM Telemetry via OTel GenAI Conventions](s196-otel-genai-telemetry.md) — vendor-neutral span instrumentation; Flight Recorder is the tamper-evident *storage* layer beneath the telemetry pipeline
- [S-368 · Agent Span Tracing: Observable Agent Sessions](s368-agent-span-tracing-observable-agent-sessions.md) — trace reconstruction; Flight Recorder is the append-only forensic version of the same trace data
- [S-759 · The Eval Gap: Traces Outnumber Verdicts 3-to-1](s759-the-eval-gap-traces-outnumber-verdicts-3-to-1-in-agentic-systems.md) — Flight Recorder traces are the input to the eval pipeline; better traces → better evals
- [F-06 · Agent Sandboxing](f06-agent-sandboxing.md) — Flight Recorder is the audit trail *after* sandboxing; sandbox prevents bad actions, recorder documents what happened
