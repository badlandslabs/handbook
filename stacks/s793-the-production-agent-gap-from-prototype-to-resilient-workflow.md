# S-793 · The Production Agent Gap: From Prototype to Resilient Workflow

Your agent works in the demo. It breaks in production — mid-transaction, on network failure, across a cluster restart. The gap isn't the agent logic; it's the infrastructure around it: state persistence, failure recovery, and observability. This is the prototype-to-production gap that Dapr Agents, Agent Audit, Regent, and the ops tooling ecosystem are converging on.

## Forces

- **Agents restart from scratch when infrastructure fails.** Most agent frameworks treat a crash as a clean slate — state is lost, workflows may double-charge, context evaporates. Durable execution is the fix, but it's not built into most frameworks.
- **Security holes scale with tool access.** Every tool an agent can call is a potential attack surface. `eval()` on LLM outputs, `subprocess.run(shell=True)` with unvalidated inputs, and prompt injection in user-controlled context are common — and traditional SAST tools don't catch them in agent context.
- **Agents are unobservable by default.** You know the agent ran. You don't know which tools it called, which session failed, or where context was lost — because there's no audit trail for agent activity, only for the files it produced.
- **Eval without recovery is theater.** S-790 covers measuring quality; this stack covers what happens when quality fails — how the system repairs itself, rolls back, or degrades gracefully.

## The move

**Build around durable execution and instrument everything before shipping.**

- **Durable state survives process death.** Dapr Agents v1.0 (CNCF, GA March 2026, backed by NVIDIA) wraps agent workflows in Dapr's state management — workflows checkpoint at each step, survive machine restarts, and retry from the last successful state. Persistent state across 30+ databases. SPIFFE-based workload identity for secure agent-to-agent communication. Scale-to-zero so specialized agents activate on demand without burning idle resources.
- **Security lint before every deploy.** Agent Audit (HeadyZhang/agent-audit, MIT, PyPI: `pip install agent-audit`) runs 72 rules mapped to the OWASP Agentic Top 10 (2026) — catches prompt injection paths, MCP misconfigurations, unsafe tool inputs (`eval`, `subprocess` with shell=True), and semantic secret detection. Covers LangChain, CrewAI, AutoGen. g0 adds behavioral scanning: 1,180 rules across 12 security domains, real-time monitoring, and compliance reporting for MCP servers and OpenAI Agents SDK deployments.
- **Track agent actions like git tracks code.** Regent (regent-vcs/re_gent, 745 stars, public alpha) records every prompt, tool call, session, and workspace state. You can `rgt log` to see what your agent did, `rgt blame` to find which prompt modified a given line, `rgt undo` to roll back agent work across files and sessions. The core insight: Git tracks what developers changed; Regent tracks what prompts changed what. Alternative: use Jujutsu (jj) VCS with agent-aware workflows — jj's op-log stores every operation, enabling `rewind` and `bisect` at the action level.
- **Ops visibility for running agents.** Hydra (Show HN, 1 point) is a macOS desktop app showing real-time status of Claude Code, Codex, Cursor, and Gemini agents running locally — because Activity Monitor and htop provide no context for agent activity. For teams, built-in OTEL (OpenTelemetry) tracing from Dapr Agents covers logs, metrics, and distributed traces across multi-agent workflows.

## Evidence

- **CNCF Blog:** Dapr Agents announcement — "guaranteed task completion" via durable execution, scales to thousands of agents on a single core, SPIFFE identity, 30+ database backends — [https://www.cncf.io/blog/2025/03/12/announcing-dapr-ai-agents/](https://www.cncf.io/blog/2025/03/12/announcing-dapr-ai-agents/)
- **Show HN (129 points):** Regent / re_gent — "Git tracks what developers changed; Regent tracks what prompts changed what" — tools: `rgt log`, `rgt blame`, `rgt undo`, `rgt bisect` for AI coding sessions — [https://news.ycombinator.com/item?id=48063548](https://news.ycombinator.com/item?id=48063548)
- **GitHub / OWASP:** Agent Audit — 72 rules, OWASP Agentic Top 10 (2026) mapped, covers LangChain/CrewAI/AutoGen — [https://github.com/HeadyZhang/agent-audit](https://github.com/HeadyZhang/agent-audit)
- **MorphLLM comparison (June 2026):** 8 SDKs compared — CrewAI 52.4k stars / ~2B agent executions/year, Microsoft Agent Framework 1.0 GA unified AutoGen + Semantic Kernel — [https://www.morphllm.com/ai-agent-framework](https://www.morphllm.com/ai-agent-framework)
- **Show HN:** VS Code Agent Kanban — Markdown-as-source-of-truth for agent task plans, version-controlled alongside code, leverages existing IDE harness rather than bundling its own — [https://news.ycombinator.com/item?id=47307169](https://news.ycombinator.com/item?id=47307169)

## Gotchas

- **Durable execution adds latency.** Dapr's checkpoint mechanism adds ~3ms per step activation. For latency-sensitive workflows, design for scale-to-zero with lazy activation rather than always-on agents.
- **Security scanning is static, not runtime.** Agent Audit catches code-level vulnerabilities before deploy but cannot detect prompt injection at runtime — you still need input sanitization and tool-level guardrails in production.
- **Agent VCS tooling is early.** Regent is public alpha; APIs and commands may change. Treat agent audit logs as supplementary to (not a replacement for) traditional application logging.
- **Scale-to-zero and multi-agent coordination need careful design.** A planning agent that spins up task-specific agents on demand sounds elegant but introduces cold-start latency and potential race conditions — model this interaction before committing to the architecture.
