# S-2711 · The MCP-A2A Protocol Axis Failure Stack — When MCP Works but Cross-Agent Coordination Fails

You shipped MCP. Your agent calls tools, queries databases, integrates Slack — everything works. Then your second team deploys a specialist agent on a different framework. You need them to coordinate. You spend three weeks building a custom JSON-RPC bridge, an agent registry, and a shared auth layer. You just re-invented A2A from scratch, badly. MCP is a solved problem. Cross-agent coordination is a different solved problem, and if you don't know the difference, you pay in integration time, production failures, and vendor lock-in.

## Forces

- **MCP and A2A solve different communication dimensions.** MCP is vertical: one agent connecting to tools and data. A2A is horizontal: agents talking to other agents across organizational boundaries. Conflating them produces half a solution. Teams that get MCP working assume A2A is "more of the same" — it isn't.
- **Cross-framework agent coordination is the new integration tax.** In 2026, 71% of organizations have deployed at least one AI agent, but only 11% have agents in production (Deloitte, 2026). A primary blocker: the moment you need two agents built on different frameworks to coordinate, you hit a wall. MCP alone can't bridge it — A2A can, if you built for it.
- **The A2A production inflection is now.** Google launched A2A in April 2025. The Linux Foundation adopted it in early 2026. By August 2026, it has 150+ supporting vendors including UiPath, SAP, and major cloud providers, and hit production-grade status at Google Cloud Next 2026. The protocol is real, stable, and live. The teams that treat A2A as future-tense are building integrations that will need rebuilding.
- **A2A failures are silent and expensive.** TheCodeForge documented a $40k+ incident from a partial A2A handshake where one agent believed it was in HEARTBEAT state while the other was still in DISCOVERY — causing silent message drops with no error raised. This isn't a theoretical failure mode. It's a production incident that already happened.
- **MCP's security model doesn't extend to A2A.** MCP servers expose tools; A2A agents expose capabilities and negotiate work. The trust model, authentication, and authorization surfaces are fundamentally different. An MCP guardrail doesn't protect an A2A handoff.

## The move

**1. Know which problem you're solving before choosing a protocol.**

| Question | Answer → Protocol |
|---|---|
| "My agent needs to call a function / query a DB / access a file" | MCP |
| "My agent needs to delegate a task to another agent" | A2A |
| "My agent needs to share state with another agent" | A2A |
| "My agent needs to discover what another agent can do" | A2A |
| "My agent needs to coordinate a multi-step workflow across agents" | A2A |
| "My agent needs to call tools AND delegate to agents" | Both (MCP inside, A2A across) |

**2. Build A2A readiness into your agent architecture from day one — not as an afterthought.**

Register agent capabilities in a machine-readable format (A2A's `AgentCard` JSON). This is the discovery mechanism A2A is built on — agents use it to negotiate without hardcoding endpoints.

```python
# agent_card.json — A2A discovery document
{
  "name": "code-review-agent",
  "version": "1.0.0",
  "capabilities": {
    "streaming": True,
    "pushNotifications": False,
    "stateTransitionReports": True
  },
  "skills": [
    {"id": "python-review", "name": "Python Code Review",
     "description": "Reviews Python code for correctness, style, and security"},
    {"id": "pr-summary", "name": "PR Summary",
     "description": "Generates human-readable PR summaries"}],
  "defaultInputModes": ["text", "application/json"],
  "defaultOutputModes": ["text", "application/json"]
}
```

**3. Implement A2A alongside MCP — don't retrofit it.**

```python
# Minimal A2A server (Python, a2a-python-sdk)
from a2a.server import A2AServer
from a2a.types import AgentCard, Skill, TextPart, Part

class CodeReviewAgent(A2AServer):
    def __init__(self):
        super().__init__(
            agent_card=AgentCard(
                name="code-review-agent",
                version="1.0.0",
                capabilities={"streaming": True, "stateTransitionReports": True},
                skills=[
                    Skill(id="python-review", name="Python Code Review",
                          description="Reviews Python code"),
                    Skill(id="pr-summary", name="PR Summary",
                          description="Generates PR summaries")
                ],
                default_input_modes=["text"],
                default_output_modes=["text"]
            )
        )

    async def handle_task(self, task):
        # Your agent logic here
        review_result = await self.review_code(task.input)
        await task.submit_output([Part(TextPart(text=review_result))])

# Pair with MCP for tools:
# MCP handles: read_file, execute_command, create_review_comment
# A2A handles: delegate to sec-scan-agent, coordinate with pr-summarizer-agent
```

**4. Set handshake timeouts explicitly — the $40k failure mode.**

A2A uses a state machine (DISCOVERY → NEGOTIATION → WORKING → HEARTBEAT → CLOSED). The most common production failure is a partial handshake where one agent times out waiting for state transition confirmation. Set timeouts explicitly:

```python
# A2A handshake with explicit timeout enforcement
from a2a.server import A2AServer, TaskHandler
from a2a.types import (
    SendTaskRequest, SendTaskResponse,
    TaskStatus, TaskStatusValue, Part, TextPart
)
import asyncio

class TimeoutTaskHandler(TaskHandler):
    HANDSHAKE_TIMEOUT = 30  # seconds — prevents the $40k partial handshake
    TASK_TIMEOUT = 300      # seconds per task

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        task_id = request.params.task_id

        # Enforce handshake resolution before accepting task
        handshake = asyncio.create_task(
            self.wait_for_state_transition(task_id, target_state="WORKING")
        )
        done, pending = await asyncio.wait(
            [handshake],
            timeout=self.HANDSHAKE_TIMEOUT
        )
        if handshake not in done:
            # Partial handshake — reject with evidence for debugging
            raise RuntimeError(
                f"A2A handshake timeout for task {task_id}: "
                f"expected WORKING state, current state unknown. "
                f"Check both agents' AgentCard compatibility and network path."
            )

        # Enforce task-level timeout to prevent runaway delegation chains
        task = asyncio.create_task(self.process_task(request))
        done, pending = await asyncio.wait(
            [task],
            timeout=self.TASK_TIMEOUT
        )
        if task not in done:
            task.cancel()
            return SendTaskResponse(
                task_id=task_id,
                status=TaskStatus(state=TaskStatusValue.TIMEOUT_EXPIRED)
            )
        return task.result()

    async def wait_for_state_transition(self, task_id: str, target_state: str):
        """Poll for state transition confirmation."""
        while True:
            state = await self.get_task_state(task_id)
            if state == target_state:
                return
            await asyncio.sleep(0.5)
```

**5. Monitor both protocol layers separately.**

MCP and A2A have different failure modes. Track them distinctly:

| Metric | Protocol | Alert Threshold |
|---|---|---|
| Tool call latency | MCP | > P99 per tool |
| Schema size per call | MCP | > 15% of context window |
| A2A task queue depth | A2A | > 50 pending tasks |
| Handshake duration | A2A | > 30s |
| State transition latency | A2A | > 5s between states |
| Cross-framework delegation success | A2A | < 95% |

**6. Handle partial A2A failures with idempotent retry.**

If an A2A delegation fails mid-handshake, re-send with the same `task_id`. A2A tasks are identified by ID — the receiving agent skips duplicate submissions.

```python
# Idempotent A2A delegation
import uuid

async def delegate_with_retry(agent_client, task: dict, max_retries=3):
    task_id = str(uuid.uuid4())  # Stable ID for idempotency
    for attempt in range(max_retries):
        try:
            result = await agent_client.send_task({
                "task_id": task_id,
                "input": task["input"],
                "skill_id": task["skill_id"]
            })
            return result
        except A2AHandshakeError as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
        except A2AMessageDropError:
            # Silent message drop — retry with same task_id (idempotent)
            continue
```

## Receipt

> Verified 2026-08-15 — A2A protocol (Linux Foundation, v1.0) confirmed production-stable as of March 2026. 150+ vendor support including UiPath, SAP, Google Cloud (Cloud Next 2026). Handshake timeout pattern validated against TheCodeForge $40k incident (A2A partial handshake silent drop). Protocol axis distinction (MCP vertical vs A2A horizontal) validated against ZenML distributed systems case study (Databricks, 2026) and Redis agent architecture guide (2026). MCP + A2A stacked architecture validated against ninelayer.in agentic mutex analysis (June 2026). A2A AgentCard schema from official agent2agent.info specification.

## See also

- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — the original framing of MCP vs A2A as the two complementary standards
- [S-2692 · The MCP-A2A Protocol Axis Stack](s2692-the-mcp-a2a-protocol-axis-stack-when-your-agents-cant-agree-on-how-to-talk-to-each-other.md) — the protocol axis taxonomy; this entry covers the operational failure when teams only implement one half
- [S-2709 · The MCP Schema Inflation Trap](s2709-the-mcp-schema-inflation-trap-when-your-protocol-tax-costs-more-than-your-queries.md) — MCP-specific token overhead; sibling entry on the other half of the protocol stack
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents; A2A's shared task context addresses this
- [S-700 · Parallel Agent Shared-State Divergence](s700-parallel-agent-shared-state-divergence-the-silent-coordination-breakdown.md) — parallel execution coordination failures; A2A's task lifecycle management helps prevent these
