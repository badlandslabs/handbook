# Human-in-the-Loop Patterns for AI Agents in Production

Research findings on real-world implementations of human oversight, checkpoints, escalation, and intervention in agentic systems (2025-2026).

---

## Framework Natively Supporting HITL

### LangGraph (langchain-ai)
**URL:** https://www.tutorialslogic.com/langgraph/human-in-the-loop

LangGraph is the reference implementation for interrupt-based HITL. The core primitive is interrupt(), which pauses graph execution at any node and persists full state. The reviewer can then approve, edit, or reject before resuming via Command(resume=...). A checkpointer is required for interrupt/resume to work.

Relevant repos:
- https://github.com/KirtiJha/langgraph-interrupt-workflow-template - FastAPI + Next.js template, 29 stars, MIT, June 2025
- https://github.com/marcjimz/lakebase-interrupt-agent - LangGraph on Databricks + Lakebase for HITL persistence, Sept 2025
- https://github.com/shashank-singh-singhania/LangGraph/tree/main/05_human_in_the_loop - Module covering interrupts, approval checkgates, manual state overrides
- https://github.com/leeroopedia/workflow-langchain-ai-langgraph-human-in-the-loop-agent - Runnable LangGraph HITL example
- https://github.com/codeninja2022-create/production-grade-ai-agent - Guardrails + HITL + LangSmith + pytest, April 2026

Docs: https://langchain-ai.github.io/langgraphjs/reference/functions/langgraph.interrupt.html

---

### AutoGen (Microsoft)
**URL:** https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html

AutoGen v0.4 (Feb 2025) supports HITL through UserProxyAgent and HumanInputAgent. During a run, the team decides when to invoke a human via run() or run_stream(). Agents can prompt for human input between turns using human_input_mode="ALWAYS" or "TERMINATE". Pre-execution hooks intercept tool calls before side effects.

Microsoft Agent Framework HITL: https://jamiemaguire.net/index.php/2025/12/06/microsoft-agent-framework-implementing-human-in-the-loop-ai-agents/

---

### OpenAI Agents SDK
**URL:** https://developers.openai.com/api/docs/guides/agents/guardrails-approvals

Released March 2025, 20k+ GitHub stars. Four control layers:

| Control | Trigger Point | Use Case |
|---------|--------------|----------|
| Input guardrails | First agent only | Validate before expensive work begins |
| Tool guardrails | Every tool invocation | Validate tool inputs/outputs |
| Output guardrails | Last agent only | Validate before returning output |
| Human-in-the-loop approvals | Side-effecting actions | Pause before cancellations, edits, shell, MCP |

Docs: https://openai.github.io/openai-agents-python/guardrails/

---

### CrewAI
**URL:** https://inferensys.com/integration/ai-agent-builder-and-workflow-platforms/approval-workflow-automation-with-crewai

CrewAI enterprise platform (AMP) provides visual editor, monitoring, tracing, and role-based access control. Manager agent evaluates worker outputs against business rules and escalates to human-in-the-loop node for final sign-off.

Scale: 450+ million workflows/month; 60 percent of Fortune 500; 4,000+ new sign-ups/week.

AWS Bedrock Guardrails + CrewAI: https://builder.aws.com/content/2yEg4fqxn23rj3zLPPzaZaTMRYb/building-safe-ai-agents-integrating-amazon-bedrock-guardrails-with-crewai

---

### GitHub Copilot Agent + Microsoft Agent Framework
**URL:** https://devblogs.microsoft.com/agent-framework/build-production-ready-agents-with-the-github-copilot-harness-and-agent-framework/

GitHub Copilot agent is backed by Copilot CLI/SDK. Microsoft Agent Framework provides extensibility layer for instructions, tools, streaming, observability, and human-in-the-loop approval. Stable for .NET and Python in 2025.

Copilot Workspace sunset May 2025; rebuilt as Copilot Coding Agent, GA September 2025: https://sirishacherala.substack.com/p/case-study-github-copilot-workspace

---

## GitHub Repositories

| Repo | Description | Stars | Date |
|------|-------------|-------|------|
| KirtiJha/langgraph-interrupt-workflow-template | FastAPI + Next.js LangGraph HITL template with approve/edit/reject | 29 | June 2025 |
| tirth1263/human-in-the-loop-agent | Python agent with per-action approval, retry, rejection + live web demo | - | June 2026 |
| marcjimz/lakebase-interrupt-agent | LangGraph on Databricks + Lakebase for HITL persistence | 2 | Sept 2025 |
| codeninja2022-create/production-grade-ai-agent | Guardrails + HITL + LangSmith + pytest evaluation | - | April 2026 |
| AxmeAI/agent-workflow-with-human-approval | Multi-lang 3-line human approval decorator | - | March 2026 |
| YosefHayim/planpage | Turns agent plans and review gates into HTML with optional approvals | - | - |
| manynames3/infraops-agent-hub | Incident triage with n8n, Postgres audit logging, approval gates | - | - |
| jqaisystems/codex-control-center | Local-first observability with approval-gated workflow review | - | - |

---

## Engineering Blog Posts and Primary Sources

### Veto.so - Human Review for AI Agents (Jan 2026, updated May 2026)
**URL:** https://veto.so/blog/human-in-the-loop-ai-agents

Five production patterns:
1. Pre-action review - Agent proposes, human approves before execution
2. Confidence-based review - Escalate below threshold
3. Sampled review - Random percent reviewed post-execution
4. Tiered review - Internal auto-approve, external-facing escalate
5. Post-action review - Agent acts, human audits afterward

Key quote: "An agent that auto-approves 95 percent of actions and routes 5 percent to a human is faster than one that requires approval for everything, and infinitely safer than one that requires approval for nothing."
