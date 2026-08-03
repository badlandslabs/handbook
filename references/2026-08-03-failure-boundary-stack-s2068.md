# Evidence Bank: S-2068 — Failure Boundary Stack

## Sources

| Source | Type | URL |
|--------|------|-----|
| Ask HN: Testing AI agents (Harper Labs) | HN | https://news.ycombinator.com/item?id=47325105 |
| agent-watchdog circuit breaker library | GitHub | https://github.com/woodwater2026/agent-watchdog |
| Reflexion: Language Agents with Verbal Reinforcement Learning | Paper | https://arxiv.org/abs/2303.11366 |
| Reflexion GitHub (3,217 stars) | GitHub | https://github.com/noahshinn/reflexion |
| Show HN: Hive self-evolving agent framework | HN | https://hn.nuxt.dev/item/46979781 |
| The Hidden Recovery Problem in Agentic AI | Blog | https://www.commvault.com/blogs/the-hidden-recovery-problem-in-agentic-ai |
| AI Agent Self-Healing and Failure Recovery | Research | https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery |
| Circuit Breakers for Agent Loops (AgentPatterns.ai) | Pattern | https://www.agentpatterns.ai/observability/circuit-breakers |
| AI System Design Guide: Error Handling and Recovery | GitHub | https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md |
| Self-Healing Agent Pipelines 2026 | Blog | https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery |
| Practical AI Agent Failure Recovery Methods | Blog | https://agentreviews.dev/blog/ai-agent-failure-recovery-methods |
| Bonjoy: Why 88% of AI Agents Fail in Production | Article | https://bonjoy.com/articles/why-ai-agents-fail-production/ |

## Key Claims

- **Silent failure is the dominant failure mode** — agents produce HTTP 200 while failing; consequences are subtle misclassifications, not crashes (AgentReviews, 2026)
- **Compound unreliability** — 10-step pipeline at 85% reliability = ~20% end-to-end success (Zylos, 2026)
- **Verbal self-reflection outperforms naive retry** — Reflexion (NeurIPS 2023) showed storing failure explanations in episodic memory and retrying with different intent beats retry-without-reflection (Shinn et al.)
- **External circuit breakers needed** — agents cannot be trusted to stop themselves; loop detection, budget guards, iteration limits enforced externally (agent-watchdog, AgentPatterns.ai)
- **Exception as observation** — treating stack traces as context signals rather than crashes enables self-correction without restart (Hive HN discussion, 2026)
- **Checkpoint without idempotency = side-effect duplication** — Temporal-style durable execution is the correct pattern for side-effecting steps (OpenAI, Scale AI, Replit production use)

## Coverage vs. Skill Bank
- failure-handling-patterns: **WRITTEN — S-2068** (2026-08-03)
