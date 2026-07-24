# S-1536 · The Durable Execution Stack — When LangGraph Gives You the Agent and Temporal Gives You the Guarantee

Your LangGraph agent works in demo. In production, a pod gets evicted after 38 minutes of a 45-minute workflow. The checkpoint state is intact. The LLM call that was mid-flight is not. When the agent restarts, it replays from checkpoint — spending another $14 in LLM calls — and silently resumes without knowing what it already did. The workflow eventually completes. Your invoice is $28 for a task worth $4. The agent crashed twice, recovered once, and confused itself once. No alert fired. No human knew.

The gap is not checkpointing. LangGraph has checkpointing. The gap is durable execution: the architectural discipline that makes checkpoints matter across crashes, timeouts, infrastructure failures, and human interruptions — without rewriting your agent logic.

## Forces

- **LangGraph gives you the agent. Temporal gives you the guarantee.** LangGraph is an agent *framework* — it defines what your agent does. It leaves the production concerns (crash recovery, human-in-the-loop pauses, runs that survive infrastructure failures) as exercises for the reader. Temporal is a durable execution *engine* — it guarantees that any step that starts will complete, retry on failure, and wait indefinitely for human input at pause points. The two are complementary; combining them closes the gap neither closes alone.

- **Crash recovery without durable execution re-plays the expensive part.** Checkpointing alone saves state — it does not replay work. When a pod dies mid-LLM call, you have the graph state but not the LLM result. Without Temporal's activity-level durability, the agent restarts the call. With 500-step workflows at $0.02/step, three crashes mean $30 instead of $10.

- **Human-in-the-loop is structurally incompatible with standard LangGraph.** Approval gates, exception escalation, and policy checks require the workflow to *pause* — sometimes for hours or days — and resume from the exact resume point. Standard LangGraph runs in-process; if the process dies, the pause dies with it. Temporal stores workflow state durably and waits at pause points across any infrastructure event.

- **LangGraph's retry logic is local. Temporal's is systemic.** LangGraph can retry individual nodes. It cannot retry a failed step *and all downstream steps* atomically, or compensate for partial side effects (an email sent, a database written) across a crashed workflow. Saga compensation requires workflow-level durability that a graph library cannot provide.

## The move

### The two-layer architecture

The integration pattern that works: **LangGraph defines the agent's logic (nodes, edges, state schema); Temporal runs it durably (activities, workflow orchestration, retries across crashes).**

```
LangGraph layer          Temporal layer
─────────────────        ─────────────────
  Node = activity        Activity = durable function
  Edge = transition      Workflow = sequence of activities
  State = schema          State = Temporal workflow state
  Checkpoint = memory     Checkpoint = persistence + replay
  Interrupt = pause      Signal = named pause + resume
```

### Step 1 — Install Temporal's LangGraph plugin

```bash
uv add "temporalio[langgraph]"
```

The plugin bridges LangGraph's state graph definition to Temporal's workflow engine. Your agent's nodes, edges, and state schema stay in LangGraph. The execution runtime moves to Temporal.

### Step 2 — Define your agent as a Temporal activity

```python
from temporalio.workflow import workflow
from langgraph.graph import StateGraph
from my_agent import AgentState, agent_nodes, agent_edges

@workflow
class AgentWorkflow:
    async def run(self, input_data: dict) -> dict:
        # Build LangGraph inside Temporal's durable context
        graph = StateGraph(AgentState)
        graph.add_nodes(agent_nodes)
        graph.add_edges(agent_edges)
        app = graph.compile()

        # Temporal guarantees: crash → replay from last checkpoint
        # No LLM call is lost without replaying the work
        return await app.ainvoke(input_data)
```

### Step 3 — Use Temporal signals for human-in-the-loop

```python
from temporalio.workflow import signal

@workflow
class ApprovalWorkflow:
    async def run(self, task: dict) -> dict:
        # Temporal waits here — no pod required, no polling
        approval = await self.wait_for_approval(task["id"])

        # Approval arrives as a Temporal signal
        # Workflow resumes exactly at this line — no replay of prior steps
        if not approval.approved:
            raise TaskRejected(approval.reason)

        return await self.execute(task)
```

`wait_for_approval` is not a blocking loop. Temporal persists the workflow state and waits *in the database*. The pod can die. When it restarts, Temporal replays the workflow to the signal wait and delivers the approval. No cost, no polling, no re-execution.

### Step 4 — Configure retry policies at the activity level

```python
from temporalio.workflow import retry_policy

@activity.defn
async def llm_call(activity_fn):
    # Retry up to 3× with exponential backoff
    # Each retry replays from the last Temporal checkpoint
    # LLM timeouts are handled transparently
    return await call_llm_with_timeout(activity_fn.input)
```

This is the architectural difference from LangGraph alone: retry is not a try/catch in your node code. It is a Temporal activity configuration that guarantees exactly-once semantics across infrastructure failures.

### Step 5 — Build Saga compensation for multi-step workflows

When Temporal runs your agent across a multi-step task, partial side effects (API writes, database commits, email sends) can leave inconsistent state on failure. The Saga pattern coordinates compensating actions in reverse order:

```
Step 1: Reserve inventory    ✓
Step 2: Process payment     ✗ → compensate Step 1 (release inventory)
Step 3: Send confirmation    skipped (Step 2 failed)
```

Temporal's `continue_as_new` lets a failed workflow spawn a compensation workflow with the same run ID, executing compensating activities in reverse order — without replaying the successful steps.

## When to reach for this

- **Multi-hour agent workflows** where infrastructure failures mid-run are not edge cases
- **Compliance workflows** that require human approval at checkpoints (payments, data exports, deployment gates)
- **High-stakes multi-step tasks** where partial completion is worse than no completion (financial transactions, regulatory filings)
- **Cost-sensitive deployments** where crash → replay means duplicate LLM calls at scale

## When to skip it

- **Simple single-call agents** where the cost of Temporal's infrastructure outweighs the failure risk
- **Stateless request/response agents** with no meaningful intermediate state to recover
- **Teams without Temporal expertise** — the integration is production-ready but has an operational learning curve

## The core insight

The failure mode that kills LangGraph agents in production — crash mid-workflow, checkpoint lost, LLM call replayed, state confused — has one root cause: **LangGraph runs in-process, and in-process state dies with the process.** Temporal's durable execution model separates *what the agent does* (LangGraph) from *when and how reliably it gets done* (Temporal). This is not a workaround. It is the right separation of concerns for production agents. The agent definition and the execution guarantee belong to different layers.

## Key sources

- [Temporal Blog — "LangGraph in Production: Temporal's LangGraph Plugin" (Jul 16, 2026)](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) — authors: Ethan Ruhe, David Hyde, Brian Strauch
- [AI Workflow Lab — "AI Workflow Orchestration in Production: Durable Agent Pipelines with LangGraph and Temporal" (Feb 22, 2026, updated Jun 2, 2026)](https://aiworkflowlab.dev/article/ai-workflow-orchestration-in-production-building-durable-agent-pipelines-with-langgraph-and-temporal)
- [LangChain — "LangGraph vs Temporal: AI Agent Orchestration Compared" (Jun 6, 2026)](https://www.langchain.com/resources/langgraph-vs-temporal)
- [arXiv:2605.20173 — "A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM Agents" (Srinivasan, May 2026)](https://arxiv.org/abs/2605.20173) — foundational SDB framework

## See also
- [S-357 · Long-Running Agent Orchestration (Planner-Worker Temporal Layers)](s357-long-running-agent-orchestration-planner-worker-temporal-layers.md) — temporal layer design
- [S-1523 · The Agent Fleet Registry Stack](s1523-the-agent-fleet-registry-stack-when-you-have-47-agents-and-no-idea-what-theyre-doing.md) — fleet-level observability for Temporal-managed agents
- [S-1532 · The Failure Governor Stack](s1532-the-failure-governor-stack-when-your-agent-runs-forever-and-your-cloud-bill-quadruples.md) — human-readable cost tracking for Temporal activity retry budgets
