# S-1645 · The Production Controllability Stack

Your agent can plan 50 steps ahead. Your production system cannot survive it.

The dominant mental model for AI agents is unbounded autonomy — systems that plan, execute, and iterate without human involvement. The empirical reality of production deployments is the opposite: the most successful agents are deliberately bounded. Teams are not building more capable agents. They are building more controllable ones.

## Forces

- **More autonomy multiplies the failure surface.** Each additional step an agent takes compounds error probability. A 20-step agent does not fail 2x more than a 10-step agent — it fails in ways that are harder to detect, diagnose, and recover from.
- **Evaluation is the hardest part.** Teams know how to build agents. They struggle to measure whether the agent is actually working. This creates a feedback vacuum that makes agents drift in unpredictable directions.
- **Autonomy and reliability are in tension.** The agents that impress in demos — long reasoning chains, self-correction, multi-tool orchestration — are precisely the agents that burn budget and produce silent failures in production.
- **Human judgment is still the ground truth.** Automated evals are cheap and fast. They are also systematically gamed by agents that optimize for the metric rather than the task.

## The Move

The MAP/CAP study (306 practitioners, 20 in-depth case studies, 26 domains) provides the empirical anchor. Here is what production teams actually do:

- **Cap agent steps before human intervention.** 68% of production agents execute at most 10 steps before a human in the loop. This is not a limitation — it is the primary reliability mechanism. Treat step limits as a feature, not a bug.
- **Prefer predefined workflows over freeform tool chaining.** 80% of deployments use constrained orchestration — workflow graphs with explicit routing, not dynamic tool selection. This trades raw capability for predictability.
- **Use prompting over fine-tuning.** 70% of production agents rely on prompting off-the-shelf models. Fine-tuning is expensive, slow, and fragile. Prompt engineering with structured output validation is the dominant production approach.
- **Default to human evaluation.** 74% of teams evaluate agent quality primarily through human review. Automated evals (LLM-as-judge, trajectory metrics) supplement human judgment — they do not replace it.
- **Design for recovery, not prevention.** Agents will fail. Build systems that detect failure early (step-count limits, cost guards, semantic validation), escalate gracefully, and preserve state so the human reviewer has context.

## Evidence

- **Survey + Case Study (306 practitioners, 20 interviews, 26 domains):** "Production agents are typically built using simple, controllable approaches: 68% execute at most 10 steps before requiring human intervention, 70% rely on prompting off-the-shelf models instead of weight tuning, and 74% depend primarily on human evaluation." — *Measuring Agents in Production (MAP), arXiv:2512.04123v1, UC Berkeley / Stanford / UIUC / IBM Research, April 2026* — https://arxiv.org/html/2512.04123v1
- **Survey + Case Study (same dataset):** "We find that production agents are built using simple, controllable approaches" with 80% of deployments using constrained orchestration over open-ended dynamic tool use. — *Characterizing Agents in Production (CAP), IBM Research for ICML 2026* — https://research.ibm.com/publications/characterizing-agents-in-production
- **Engineering blog / framework design:** Pydantic AI (60k+ stars, Python agent framework) explicitly prioritizes type safety, structured outputs, and observability over autonomy — designed for teams that need to control what the agent does, not maximize what it can do. — Samuel Colvin, AI Engineering Podcast, 2025 — https://www.aiengineeringpodcast.com/pydantic-ai-type-safe-agent-framework-episode-63

## Gotchas

- **Demos reward autonomy; production rewards reliability.** The step-limit constraint feels wrong during development. It is the thing that makes the agent safe to run unattended.
- **Human eval is expensive at scale.** The 74% human-eval finding is a target, not a ceiling. As agent count grows, this becomes a bottleneck. Budget for eval infrastructure before scaling agent count.
- **Simple stacks are not lazy stacks.** The finding that 70% of agents use prompting over fine-tuning is not a sign of immaturity — it reflects that prompting is more controllable, faster to iterate, and easier to debug in production.
- **The CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) is emerging for teams that need multidimensional evaluation beyond task completion.** — *Measuring Agents in Production* — cost variations of 50x for similar precision were observed across different evaluation strategies.
