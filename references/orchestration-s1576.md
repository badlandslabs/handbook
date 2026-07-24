# references/orchestration-s1576.md

**Stack:** S-1576 · The Orchestration Taxonomy Stack (2026-07-24)
**Topic:** Orchestration patterns for multi-agent systems
**Sources:** 6 primary sources cross-referenced

## Key Claims

| Claim | Source | URL |
|-------|--------|-----|
| "Multi-agent systems harder than single agents by order of agent count" | TURION.AI blog (Mar 2026) | https://turion.ai/blog/multi-agent-orchestration-infrastructure-production |
| MAST: 14 failure modes, 3 categories (system design, inter-agent misalignment, task verification) | Cemri et al. arXiv:2503.13657 (Apr 2025) | https://arxiv.org/abs/2503.13657 |
| ChatDev only 33.33% correctness on ProgramDev | MAST paper (Berkeley) | https://arxiv.org/abs/2503.13657 |
| 40% of multi-agent pilots fail within 6 months | Beam.ai / Gartner (Jul 2026) | https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production |
| Gartner 1,445% surge in MAS inquiries Q1 2024→Q2 2025 | Beam.ai citing Gartner | https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production |
| Average 12 agents in production, +67% projected | Beam.ai / Gartner | https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production |
| Cost cut 40–60% by using cheaper models for workers vs. single capable model | Beam.ai (2026) | https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production |
| "Orchestration layer is where most enterprise agent projects succeed or fail" | Thinking.inc (2026) | https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns/ |
| "Over-engineering from day one" — most common mistake | Data-Gate (2026) | https://data-gate.ch/multi-agent-systems-production-lessons |
| Six patterns cover most enterprise use cases | Thinking.inc, QubitTool | https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns/ |
| Production systems combine 2–3 patterns | Thinking.inc (2026) | https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns/ |
| Biggest challenges: workflow integration, employee resistance, not technical | MMC Ventures (Nov 2025) | https://mmc.vc/research/state-of-agentic-ai-founders-edition/ |
| Supervisor scales to 3–8 agents; hierarchical to 10–50+ | QubitTool (May 2026) | https://qubittool.com/blog/multi-agent-orchestration-patterns |
| "Leaky pipeline" anti-pattern: stages pass accumulated context not scoped output | Thinking.inc (2026) | https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns/ |

## HN Discussion Context

- HN thread on MMC research (id=45808308, 107 points): real-world agent deployments, workflow integration cited as main blocker
- HN thread on Anthropic's "Building Effective AI Agents" (id=44301809, 543 points): orchestration patterns discussed at length

## Framework Coverage

- LangGraph: supervisor pattern, explicit state graphs
- CrewAI: hierarchical mode, role-based crews
- AutoGen: conversational multi-agent
- MetaGPT: role-based with SOPs
- OpenAI Swarm: lightweight peer-to-peer

## MAST Failure Modes (Berkeley Taxonomy, arXiv:2503.13657)

14 modes across 3 categories, derived from 200+ traces across 7 frameworks:

**Category 1: System Design**
- Error cascade
- Context loss
- Collective hallucination
- (from truncated paper)

**Category 2: Inter-Agent Misalignment**
- Infinite negotiation
- Goal drift
- (from truncated paper)

**Category 3: Task Verification**
- (from truncated paper)
