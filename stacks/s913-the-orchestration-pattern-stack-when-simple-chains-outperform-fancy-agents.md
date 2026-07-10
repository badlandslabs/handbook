# S-913 · The Orchestration Pattern Stack — When Simple Chains Outperform Fancy Agents

Most teams reaching for multi-agent loops would have been better off with a sequential pipeline. LangChain's 2025 production survey of 1,340 practitioners found that 73% of production systems use simple chains, and those chains handle roughly 80% of actual production use cases. The agent cost premium — 3–5x per task over chains — rarely pays off unless you genuinely need multiple specialized models or parallel execution. The orchestration pattern stack gives you a decision framework: match the pattern to the problem shape, not to the hype.

## Forces

- **Demo complexity vs. production simplicity** — Multi-agent loops look impressive in demos and often fail in production due to compounded error rates, harder debugging, and 3–5x higher inference costs. The LangChain survey found 57% of teams have agents in production, but the majority are using chains, not agents.
- **Single-agent ceiling vs. multi-agent overhead** — One overloaded agent with too many tools and responsibilities hits a quality ceiling. Splitting into specialized agents introduces coordination costs, message-passing complexity, and harder debugging. The rule of thumb from practitioners: if you can't name what each agent does in one short sentence, you're not ready to split the work yet.
- **Inference cost compounding** — A 4-agent supervisor-worker workflow costs $5–8 per complex task. Each agent pass adds latency and dollars. Parallel fan-out helps with throughput but multiplies cost. Budget modeling before architecture commitment is non-negotiable.

## The move

Six patterns cover the vast majority of enterprise use cases, ordered by complexity. Start at the top. Move down only when the simpler pattern genuinely can't handle the workload.

**1. Sequential Pipeline** — Linear chain where each agent processes the output of the previous one. The workhorse: research → draft → edit → publish, extract → transform → validate → load, plan → implement → test → review. This is what 73% of production systems actually use. Start here always.

**2. Router / Dispatcher** — A classifier at the top decides which specialized path handles the request. Use when task types are predictable and disjoint — routing a support ticket to billing vs. technical vs. returns. Cheaper than running every task through the most capable model; a high-volume classification step doesn't need the same model as deep financial reasoning.

**3. Parallel Fan-Out** — Multiple agents execute independent tasks simultaneously, results aggregated at the end. Use when you have N independent sub-tasks and waiting for sequential execution would be too slow. State coordination is the hard part — file locking, shared memory, or message passing must be explicit or you'll get silent conflicts.

**4. Supervisor / Hierarchical** — A single orchestrator agent receives requests, creates execution plans, delegates to specialist workers, monitors progress, and assembles the final output. Anthropic's Agent Teams feature (experimental, launched Feb 2026) uses this architecture: a team lead Claude session coordinates separate teammate instances via a shared task list and peer-to-peer messaging.

**5. Evaluator-Optimizer Loop** — An agent produces output; an independent reviewer criticizes it against fixed criteria; the original agent revises. Repeat until quality threshold. This self-critique pattern catches far more errors than having the same agent review its own work. Used in high-stakes document generation, code review, and financial analysis where independent verification matters.

**6. Agent Loop (ReAct-style)** — The agent iteratively calls tools, observes results, and decides next steps until reaching a terminal state. Use only for open-ended problems where the path can't be predetermined — exploration, research synthesis, complex troubleshooting. Implement hard step limits; unbounded loops are the most expensive failure mode.

Production systems typically combine two or three patterns within a single workflow. A content pipeline might use a router to classify input, a parallel fan-out to gather source material from multiple feeds, a sequential pipeline to draft and edit, and an evaluator-optimizer loop for final quality review.

## Evidence

- **LangChain Production Survey:** 73% of production systems use simple chains; simple chains handle ~80% of production use cases; agent cost runs 3–5x higher than chain cost. 1,340 practitioners surveyed, November–December 2025. — https://www.langchain.com/state-of-agent-engineering
- **Gartner Multi-Agent Surge:** Enterprise inquiries about multi-agent systems grew 1,445% from Q1 2024 to Q2 2025, while Gartner forecast 40% of enterprise apps will include task-specific AI agents by 2026 (up from under 5% in 2025). — https://www.claritywithai.org/2026/06/multi-agent-ai-orchestration-guide-2026.html
- **GitHub — Hive (Aden):** Production AI multi-agent harness with 10.6k stars, DAG compilation for coordinated workflows, self-healing failure capture, and zero-setup model-agnostic execution. Built from 4 years of ERP automation for construction (PO/invoice reconciliation). Core thesis: "Chatbots aren't for real work. Accountants don't want to chat; they want the ledger reconciled while they sleep." — https://github.com/aden-hive/hive
- **arXiv:2512.08769 — Agentic AI Workflows Practical Guide:** arXiv paper (December 2025) from a multi-institution team documenting multi-agent patterns across 11 contributing organizations. Provides a full implementation of a multimodal, multi-agent news-to-media workflow and an extensible blueprint for organizations adopting agentic AI in production. — https://arxiv.org/pdf/2512.08769
- **Microsoft Semantic Kernel:** Sequential, parallel, and hierarchical orchestration patterns implemented as first-class primitives with full documentation. — https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/sequential

## Gotchas

- **The supervisor is a single point of failure.** A buggy or hallucinating supervisor agent corrupts the entire workflow. Add explicit checkpointing and rollback at supervisor handoff boundaries.
- **Parallel fan-out needs explicit state coordination.** Multiple agents writing to the same shared resources without locking produces silent corruption — the output looks plausible but is internally inconsistent. Implement file locks or message-passing coordination before parallelizing.
- **"If you can't name it in one sentence, you're not ready to split."** Before adding a second agent, write a one-sentence description of what each does. If you can't, the split is premature and the coordination overhead will exceed the specialization benefit.
- **Cost compounds per agent pass.** Model the inference economics before committing to multi-agent architecture. 4-agent workflows at $5–8 per task are viable for low-volume high-value tasks but destroy margins on high-volume classification.
- **Framework choice has diverged.** LangChain users (42% of survey respondents) use built-in abstractions. Others build pure-Python DAG orchestrators with zero framework dependencies. Neither is wrong — but the ecosystem is fragmented and switching costs are real.
