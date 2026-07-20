# S-1367 · The Agent Skill Composition Stack

When your agent has access to 50 tools and still picks the wrong one, ignores retry logic, and invents its own workflow — the problem isn't the tools. It's the missing layer between "I have capabilities" and "I know how to apply them."

## Forces

- A tool does one thing. A real task requires sequencing, error handling, conditional routing, and policy awareness. Flat tool registries leave this reasoning to the model — every time.
- The naive fix is a monolithic system prompt that lists every capability. At 30+ tools this becomes unreadable context noise that degrades quality and burns tokens.
- Adding more tools to a flat registry *increases* planning errors, not decreases them. The agent must infer when to use what, in what order, with what retry policy.
- Prompt-based instructions for complex workflows are fragile — a single version change breaks implicit assumptions scattered across a 2,000-line prompt.

## The move

Build a **skill layer** between tools and goals: each skill is a loadable unit that encodes not just *what* a capability does, but *when* to use it, *how* to sequence it, *what* to retry on, and *what* the failure modes look like.

The pattern has three components:

**1. Skill manifest at startup — not the skill body.**
Inject only `name`, `description`, and `trigger conditions` into the system prompt at initialization. The agent gets an inventory, not an encyclopedia.

```yaml
# skill: refund-handler.yaml
name: "Refund Handler"
description: "Process customer refund requests for orders within 30-day window"
triggers:
  - "refund"
  - "return my order"
  - "I want my money back"
  - "cancel and refund"
preconditions:
  - "order_id must be provided or recoverable from context"
  - "agent has confirmed customer identity"
escalates:
  - "order outside 30-day window"
  - "refund amount > $500"
  - "customer disputes charge"
permissions_required: ["read_orders", "issue_refund"]
```

**2. Progressive disclosure at execution time.**
When the agent decides to invoke a skill, it loads the full skill body — operational instructions, retry logic, sequencing, edge cases. This is the "activation" moment. At rest, skills are metadata.

```python
# Skill activation in the agent loop
def activate_skill(agent, skill_name):
    manifest = load_skill_manifest()  # ~50 tokens per skill
    if should_invoke(skill_name, agent.intent):
        skill_body = load_skill_body(skill_name)  # full instructions
        agent.inject_context(skill_body)           # only when needed

def should_invoke(skill_name, intent):
    triggers = manifest[skill_name]["triggers"]
    return any(t in intent.lower() for t in triggers)
```

**3. Skill composition with conflict resolution.**
When one skill's postconditions feed another's preconditions, chain them explicitly. When two skills conflict (both claim an action), resolve with priority weights, not model guesswork.

```yaml
# skill: escalation-pipeline.yaml
composition:
  steps:
    - skill: "refund-handler"
      on_success: "close_case"
      on_escalate: "tier2_transfer"
    - skill: "tier2_transfer"
      preconditions_met: "refund-handler.escalated == true"
  conflict_resolution:
    rules:
      - "refund-initiated + chargeback-filed -> refund takes priority"
      - "duplicate_refund_attempts -> abort, log, alert"
```

## The SKILL.md ecosystem

Anthropic's `SKILL.md` format has become the de facto standard for agentic skill declaration. As of 2026, it has 800,000+ community-contributed skills across 20+ coding agents. The format encodes skill metadata in frontmatter and operational instructions in the body:

```markdown
---
name: weekly-report-check
description: Check team daily report completion and send reminders
triggers:
  - "daily report"
  - "lark-daily-report"
  - "team check-in"
---
# Operational instructions
[Full skill body — loaded only on activation]
```

## Results

Zylos Research (2026-05-12) measured skill composition across 20 production agent deployments:

| Metric | Flat tool registry | Skill composition |
|--------|-------------------|-------------------|
| Planning error rate | baseline | **−42%** |
| Task completion rate | baseline | **+16.2 pp** |
| Avg context at execution | baseline | **−3–8x** |
| New capability onboarding | 2–4 hours | **~20 minutes** |

The key insight: agents don't just need to know *capabilities exist*. They need to know *how capabilities compose* and *when each is the right tool*. Encoding this as data — not prompts — is the leverage.

## Receipt

> Verified 2026-07-19 — Source: [Zylos Research: Agent Skill Composition](https://zylos.ai/research/2026-05-12-agent-skill-composition-modular-capability-architecture) (2026-05-12, quantitative study across 20 production deployments). Format reference: [SKILL.md ecosystem](https://github.com/anthropics/skill-examples) (Anthropic, MIT license). Code patterns reflect standard progressive disclosure architecture from LangChain/Mastra skill activation patterns. No live execution performed.

## See also

- [S-355 · Agent Autonomy Levels](stacks/s355-the-agent-autonomy-levels-stack-when-agents-do-too-much-and-not-enough.md) — where skill activation lives on the autonomy spectrum
- [S-10 · MCP](stacks/s10-mcp.md) — the vertical tool access layer beneath the skill layer
- [S-541 · Agent Drift Detection](stacks/s541-agent-drift-detection.md) — when skill composition degrades silently
- [S-194 · Synthetic Data Generation for Fine-Tuning](stacks/s194-synthetic-data-fine-tuning-pipeline.md) — using production skill traces as training data
