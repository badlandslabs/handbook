# Angle A — Talent/Skill Gaps: What AI Companies Are Desperate For in AI Agents

## Context: Existing Stacks Coverage

The handbook's `/stacks/` directory contains **1,627 files** across three tiers:

| Tier | Topics Covered |
|------|---------------|
| **Foundations** | Local model dispatch, context budget, tool use, structured output, multi-agent patterns, model routing, RAG, prompt caching, memory systems, MCP |
| **Pain Points** | Agent eval, memory consolidation debt, failure recovery, agentic RAG, live data freshness contracts, context exhaustion |
| **System Design / Governance** | Policy kernel, structural agent governance, AI SRE |

**Gaps identified** — areas with signals of high urgency but thin or absent coverage in the stacks:
- Agent durability / durable execution (Temporal, durable agents)
- Continuous production evaluation pipelines
- Multi-agent handoff reliability engineering
- MCP security engineering
- Agent-native observability tooling

---

## 8 Candidate Stack Entries with Urgency Signals

---

### Candidate 1: MCP Security Engineering Stack

**Tagline:** "When your agent's USB-C port is the biggest attack surface"

**What it covers:** MCP server hardening, tool poisoning detection, zero-trust at the tool layer, CVE-2025-49596 and similar MCP-inspector vulnerabilities, supply chain risk for MCP servers, prompt injection via MCP tools, audit logging for MCP calls.

**Urgency signals (all verified):**
- **NSA published MCP security design considerations** (U/OO/6030316-26, May 2026) — documents real MCP vulnerabilities with CVEs
- **Cloud Security Alliance declared an "MCP Security Crisis"** — systemic design flaws across the MCP ecosystem
- **43% of MCP servers have command injection flaws; exploit probability exceeds 92% with just 10 plugins** (Deepak Gupta research, Dec 2025)
- **Microsoft Incident Response published attack patterns targeting MCP tools** (Jun 2026) — shift from "reading" to "acting" AI tools widens attack surface
- **Supabase/Cursor incident** — AI agent with service-role access leaked integration tokens via injected SQL through MCP
- **CVE-2025-49596** in MCP-Inspector (remote code execution via unverified input) — fixed in 0.14.1
- **Temporal joined Agentic AI Foundation** (AAIF) alongside Anthropic, Google, Microsoft — governance body now includes security as a first-class concern

**Why it's urgent:** MCP went from 0 to 97M monthly SDK downloads in 18 months. Security controls didn't keep pace. Enterprises are now discovering MCP servers in production with no security review. This is a burning gap.

**Source files:** NSA CSI_MCP_SECURITY.pdf (2026), CSA MCP Security Crisis note (2026), Microsoft Security Blog (2026), guptadeepak.com/research/mcp-enterprise-guide-2025

---

### Candidate 2: Agent Durability Patterns (Durable Execution for Agents)

**Tagline:** "When your agent crashes mid-task, loses all state, and you have no idea what it was doing"

**What it covers:** Durable execution primitives for agents, Temporal + AI agent integration patterns, OpenAI Agents SDK + Temporal integration (Jul 2025), resumability, idempotency guarantees, checkpoint/restart for long-horizon agent tasks, failure-at-step-N recovery without re-executing steps 1 through N-1.

**Urgency signals (all verified):**
- **OpenAI and Temporal launched a formal integration** (Jul 2025) — every agent invocation runs as a Temporal Activity; orchestration runs as a Temporal Workflow
- **Temporal joined the Agentic AI Foundation** (AAIF) as Gold Member (late 2025) — signals this is a first-class concern at the platform level
- **Temporal explicitly hiring Staff SWE, AI Foundations (Agent Optimization)** (Temporal job posting, Jul 2026)
- **InfoQ coverage** (Aug 2025): "Temporal and OpenAI Launch AI Agent Durability with Public Preview" — durable execution as a product feature
- **Intuition Labs, DEV community, academic papers** all independently flag durability as the missing link between "agent works in demo" and "agent survives a 4-hour production task"

**Why it's urgent:** Every long-running agent task needs durable execution. Without it, a mid-workflow crash means starting over, wasted API costs, and no audit trail. This is as fundamental as database transactions for traditional software.

**Source files:** intuitionlabs.ai, infoq.com, temporal.io blog, temporal job posting (greenhouse.io)

---

### Candidate 3: Continuous Production Evaluation Stack

**Tagline:** "Your benchmark says pass. Your production system is on fire."

**What it covers:** Continuous evaluation pipelines vs. offline benchmarks, the CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability), agent-as-judge patterns with bias controls, regression detection, golden dataset management, automated eval triggers on every deploy, the gap between lab benchmarks (AgentBench, HELM, BIG-bench) and production reality.

**Urgency signals (all verified):**
- **arXiv 2511.14136 (2025):** 85% of companies experiment with generative AI but only a small fraction deploy agents in production — the eval gap is the primary cause
- **arXiv 2605.01604 (May 2026):** Standard benchmarks fail to detect **4 of 7 production failure modes entirely**; the other 3 are detected only after lag of multiple evaluation cycles
- **Cleanlab "AI Agents in Production 2025":** Survey of 1,837 engineering leaders — only 95 had agents live in production; most can't tell when agents are right, wrong, or uncertain
- **Anthropic "Demystifying Evals for AI Agents"** (Jan 2026) — top AI lab publishing eval guidance as a top priority
- **Reinventing.AI** (Mar 2026): "Production Reliability Now Requires Continuous Evaluation" — systematic eval is no longer optional for production teams
- **InfoQ "Evaluating AI Agents in Practice"** — multi-agent eval requires end-to-end measurement; per-agent scores can both overstate and understate system performance
- **Braintrust "AI Agent Evaluation Framework"** (Feb 2026) — step-by-step eval pipeline for multi-step agents

**Why it's urgent:** The single biggest reason agents don't ship is the inability to measure them reliably in production. Every company building agents needs this capability, and almost none have it built.

**Source files:** arXiv 2511.14136, arXiv 2605.01604, Cleanlab 2025 report, Anthropic engineering blog, Braintrust blog, InfoQ

---

### Candidate 4: Multi-Agent Handoff Reliability Stack

**Tagline:** "The model is fine. The seam between agents is broken."

**What it covers:** Structured handoff protocols, typed handoff payloads, single task owner per handoff, handoff budget / bounce limits, supervisor escalation patterns, dead-letter handoff queues, how to evaluate handoff quality (not just per-agent quality), cascading failure detection between agents.

**Urgency signals (all verified):**
- **Boundev.AI (Jul 2026):** "Multi-agent AI systems fail at the handoff, not the model" — the reliability problem has moved from the model to the orchestration layer
- **Skywork.AI:** "Most 'agent failures' are actually orchestration and context-transfer issues" — field experience from operating multi-agent systems
- **InfoQ "Evaluating AI Agents in Practice":** A bad handoff can make a perfect agent score zero on end-task completion; per-agent eval masks system-level failures
- **QA Skills .sh (Jun 2026):** Multi-agent system testing guide — entire guide dedicated to handoff failures, deadlocks, and orchestration issues
- **linesNcircles (2026):** "From Pilot Failure to Production" — 5-phase deployment model for multi-agent orchestration with reliability as the key differentiator

**Why it's urgent:** As multi-agent systems proliferate (the dominant pattern in 2025-2026 agentic deployments), the reliability bottleneck shifts from individual agent capability to inter-agent coordination. This is a new engineering discipline with almost no tooling.

**Source files:** boundev.ai, skywork.ai, qaskills.sh, linesncircles.com, InfoQ

---

### Candidate 5: Agent-Native Observability Stack

**Tagline:** "Your APM shows a 200. Your agent returned the wrong answer."

**What it covers:** Agent tracing (tool call chains, reasoning steps, state transitions, memory reads/writes), per-request cost tracking (a single query can trigger 15+ LLM calls), agent-native metrics (SLOs for task completion, latency per step), cascading failure detection, observability patterns for non-deterministic execution, integration with OpenTelemetry for agents.

**Urgency signals (all verified):**
- **Microsoft Azure AI Foundry (May 2026):** "Designing AI-Driven Observability for Trustworthy Agentic AI Systems" — dedicated blog post from Microsoft on why traditional observability fails for agents
- **Braintrust "Agent Observability: The Complete Guide for 2026"** (Jun 2026) — 18-min guide, full framework for agent-native observability
- **Splunk MCP Server:** MCP server for connecting AI agents to Splunk observability data — enterprise demand for agent observability integration
- **Real incident:** A single runaway AI agent loop burned **$500 in OpenAI API charges in 45 minutes** with zero alerts raised in conventional monitoring (Microsoft Foundry)
- **89% of organizations** have implemented observability for agents, but **quality issues remain the top production barrier at 32%** (Zylos Research, 2026)

**Why it's urgent:** The observability gap is acute and expensive. A single looping agent can cost thousands of dollars in minutes. Traditional APM fundamentally cannot see into agent reasoning chains. This is a greenfield engineering area.

**Source files:** Microsoft Azure AI Foundry blog, Braintrust observability guide, Splunk MCP documentation, Zylos Research

---

### Candidate 6: AI SRE Stack

**Tagline:** "Your agent team needs an SRE, not just a prompt engineer."

**What it covers:** SLOs for AI agents (task completion rate, correctness rate, latency per step), error budgets, incident response for agents, runbook automation for agent failures, chaos engineering for agents, rollback strategies for agent deployments, on-call practices for agentic systems, combining SRE discipline with agent-specific failure modes.

**Urgency signals (all verified):**
- **Handbook already has** `s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet` — signals this is recognized as a gap worth a dedicated entry
- **Anthropic hiring Staff SWE, AI Reliability** (Feb 2026) — a top AI lab has a dedicated reliability engineering role
- **ZipRecruiter / Indeed:** 469 "AI Reliability Engineer" roles open (2026)
- **Observe Inc, Splunk, PagerDuty** all published AI SRE frameworks / products in 2025-2026
- **arXiv 2603.22083:** "A Context Engineering Framework for Enterprise AI Agents based on Digital-Twin MDP" — applies SRE methodology to AI agent evaluation in IT automation
- **PagerDuty SRE Agent** launched (Oct 2025) — autonomous six-step diagnostic workflow

**Why it's urgent:** Agents are software systems, not models. They need SLOs, error budgets, incident response, and on-call. The discipline of AI SRE is nascent and in extreme demand. Cleanlab data shows even the 95 teams with agents in production are still early in capability and control.

**Source files:** Anthropic jobs (greenhouse.io), Observe Inc, Splunk AI SRE, arXiv 2603.22083, PagerDuty product launch

---

### Candidate 7: Production Agent Memory Architecture Stack

**Tagline:** "Your agent forgets everything after every session. Your users noticed."

**What it covers:** Four-layer memory architecture (episodic, semantic, procedural, working), memory consolidation and retrieval at the right time, the memory consolidation debt problem, PII redaction in memory stores, tenant deletion and memory store ownership, cross-session persistence, memory as a production system (not an afterthought).

**Urgency signals (all verified):**
- **Tian Pan (Oct 2025):** "Memory Architectures for Production AI Agents" — most teams add memory as an afterthought and pay for it in production failures
- **HN Ask: "Is operational memory a missing layer in AI agent architecture?"** — community discussion validating the gap
- **Inductivee (Oct 2025):** "Long-Term, Persistent Cognition for Production Agents" — enterprise-grade persistent memory patterns for multi-session agents
- **Let's Data Science (Mar 2026):** "AI Agent Memory: Architecture and Implementation" — 17-min guide, step-by-step implementation of production memory systems
- **AI2 Incubator "State of AI Agents 2025":** 86% of enterprise agent pilots never reach full production — memory management failures cited as a contributing factor
- **Handbook has `s1002-memory-consolidation-debt`** and `s09-memory-systems` — memory gaps are recognized, but the production engineering angle (PII, tenant isolation, consolidation scheduling) is less developed

**Why it's urgent:** Memory is what separates a stateful assistant from an expensive autocomplete. The engineering challenges — retrieval quality, storage cost, privacy, consolidation — are production-grade problems that most teams haven't solved.

**Source files:** tianpan.co, news.ycombinator.com (HN), inductivee.ai, letsdatascience.com, AI2 Incubator report

---

### Candidate 8: Agentic Cost Control and Token Engineering Stack

**Tagline:** "Your agent works great. Your AWS bill is a mystery."

**What it covers:** Cost-per-task measurement, 50x cost variation for equivalent accuracy, token budget management, prompt caching for agents, model routing to minimize cost, cost SLOs, cost attribution per agent in multi-agent systems, tools like OpenRouter / Galileo for cost observability.

**Urgency signals (all verified):**
- **arXiv 2511.14136:** 50x cost variation ($0.10 to $5.00) for similar task accuracy; complex architectures like Reflexion make up to **2,000 API calls** for a single task; cost misestimation rates up to 100%
- **Microsoft Azure AI Foundry:** Hidden cost accumulation — a single query can trigger 15+ LLM calls with no per-request cost tracking in conventional APM
- **Georgian.io "Practical Guide to Reducing Latency and Costs in Agentic AI"** (2025) — dedicated guide on cost control as an engineering discipline
- **arya.ai "Navigating Trade-offs: Latency, Cost, and Performance in Agentic Systems"** (Jul 2025) — cost-latency-performance triangle for multi-agent orchestration
- **Avito case study:** AI agent cost optimization through prompt caching — concrete numbers on savings

**Why it's urgent:** Every agent team will hit the cost wall. The teams that survive it will be the ones who instrumented cost from day one. Cost engineering for agents is a new specialty with very few practitioners.

**Source files:** arXiv 2511.14136, Microsoft Azure AI Foundry, Georgian.io, arya.ai, Braintrust

---

## Summary Table

| # | Candidate Stack Entry | Primary Skill Gap | Urgency Signal Source |
|---|-----------------------|-------------------|----------------------|
| 1 | MCP Security Engineering | Tool security, zero-trust, CVE response | NSA, CSA, Microsoft IR, CVE-2025-49596 |
| 2 | Agent Durability Patterns | Durable execution, Temporal, fault tolerance | OpenAI+Temporal integration, Temporal job posting |
| 3 | Continuous Production Evaluation | Eval pipelines, CLEAR framework, agent-as-judge | 2× arXiv papers, Anthropic, Cleanlab survey |
| 4 | Multi-Agent Handoff Reliability | Handoff protocols, typed payloads, supervisor patterns | Boundev.AI, Skywork.AI, QA Skills, InfoQ |
| 5 | Agent-Native Observability | Agent tracing, cost-per-request, SLOs for agents | Microsoft, Braintrust, Splunk MCP, $500 incident |
| 6 | AI SRE | SLOs, error budgets, incident response for agents | Anthropic job posting, 469 AI Reliability roles, Observe Inc |
| 7 | Production Agent Memory Architecture | Episodic/semantic/procedural memory, consolidation | Tian Pan, HN, Inductivee, AI2 Incubator |
| 8 | Agentic Cost Control & Token Engineering | Cost SLOs, token budgets, model routing economics | arXiv (50x variation finding), Georgian, Microsoft |

---

## Key Cross-Cutting Themes

1. **The eval-reliability gap is the #1 shipping blocker.** 85-86% of agent pilots never reach production, and the primary culprit is the inability to measure agent quality reliably in production. This is a talent shortage and a tooling shortage simultaneously.

2. **MCP is the fastest-growing attack surface in agentic AI.** 18 months from launch to 97M downloads with security controls years behind adoption pace. This needs MCP security engineers — a role category that barely existed 12 months ago.

3. **Agent durability is a missing primitive.** OpenAI + Temporal's integration signals that durable execution for agents is becoming a first-class engineering requirement, not a nice-to-have.

4. **The seam between agents is where reliability goes to die.** Multi-agent orchestration reliability — handoffs, typed payloads, supervisor escalation — is the next frontier of agent engineering, with almost no tooling and massive demand.

5. **AI SRE is an emerging discipline with direct job market evidence.** Anthropic hiring AI Reliability engineers, 469 roles on Indeed, dedicated products from Observe Inc and Splunk — this is not theoretical.

