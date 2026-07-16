# S-1118 · The Skill-Driven Engineering Stack — When Your AI Coder Writes Code That Compiles But Shouldn't Have

Your AI coding agent ships code. Tests pass. Then a production incident reveals the change introduced a subtle race condition, ignored a dependency deprecation, and didn't update the corresponding test fixtures. The agent was never taught the *discipline* of software engineering — it was only taught the mechanics of coding. This is the gap between a coding assistant and a production-grade AI engineer.

## Forces

- AI coders optimize for completing the task, not for the engineering contract around the task
- Engineering discipline (security review, regression testing, changelog updates, deprecation awareness) lives in institutional knowledge that lives nowhere the agent can read it
- Naive agents treat "tests pass" as a signal to ship, missing the gates between "compiles," "works," "is correct," "is safe," "is maintainable"
- Every team has different conventions — adding them to the system prompt bloats context and degrades quality
- Skill encoding must be task-triggered, not session-scoped — the agent shouldn't apply a security review skill to a documentation change

## The move

**Encode engineering discipline as executable skills that activate at the right lifecycle phase.**

The reference architecture comes from `addyosmani/agent-skills` (78K GitHub stars, MIT, Feb 2026), which maps the full software development lifecycle as six triggered phases:

```
  DEFINE          PLAN           BUILD          VERIFY         REVIEW          SHIP
 ┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐
 │ Idea │ ───▶ │ Spec │ ───▶ │ Code │ ───▶ │ Test │ ───▶ │  QA  │ ───▶ │  Go  │
 │Refine│      │  PRD │      │ Impl │      │Debug │      │ Gate │      │ Live │
 └──────┘      └──────┘      └──────┘      └──────┘      └──────┘      └──────┘
```

Each phase maps to one or more **executable skills** — a `SKILL.md` with YAML frontmatter plus optional scripts and references. The agent doesn't load all skills at once; it activates the relevant skill when the slash command fires.

### The seven slash commands

| Command | Activates | What it enforces |
|---------|-----------|-----------------|
| `/define` | Requirements interrogation skill | Asks one question at a time; kills ambiguous requirements before code is written |
| `/plan` | PRD creation skill | Creates structured spec with acceptance criteria, non-goals, edge cases |
| `/build` | Implementation + convention skill | Applies project coding standards, naming, architecture alignment |
| `/test` | TDD enforcement skill | Red-green-refactor cycle; refuses to write implementation before tests |
| `/review` | Five-axis QA skill | Scores correctness, security, performance, maintainability, test quality |
| `/refactor` | Refactoring safety skill | Chesterton's Fence check before removing code; Beyonce Rule (change must pass existing tests) |
| `/ship` | Release gate skill | Changelog update, version bump, rollback plan, stakeholder notification |

### The five-axis review

When `/review` fires, the skill instructs the agent to score the change across five dimensions:

1. **Correctness** — Does the code do what the spec says?
2. **Security** — Are inputs sanitized, auth checks in place, secrets not hardcoded?
3. **Performance** — Any O(n²) patterns, missing indexes, unbounded loops?
4. **Maintainability** — Is logic clear, naming consistent, coupling reasonable?
5. **Test quality** — Are edge cases covered, assertions meaningful, no no-op tests?

Each axis gets a score and a one-line justification. Any axis below threshold blocks the `/ship` command.

### Engineering principles as executable rules

Skills encode Google-style engineering wisdom as actionable rules, not prose:

- **Hyrum's Law**: If a behavior is observable, someone depends on it — the skill asks "who depends on this behavior?" before any change
- **Chesterton's Fence**: Before removing or changing code, explain why the fence exists
- **Beyonce Rule**: If you liked it, you should've put a test on it (don't break what you can't verify)
- **Shift Left**: Catch errors at the earliest possible phase — a security concern caught in DEFINE costs 10x less than one caught in SHIP

```markdown
# skill/code-review-and-quality/SKILL.md
---
name: code-review-and-quality
description: Five-axis quality review before any code change merges
trigger: /review
---

## Five-Axis Review Protocol

For every file changed, score each axis. Any axis < 3/5 requires comment.

### Correctness
- Does the implementation match the spec acceptance criteria?
- Are error paths handled, not just happy paths?

### Security
- User input: sanitized, validated, parameterized?
- AuthZ check: present AND at the right scope?
- Secrets: referenced via env var or secret manager, never hardcoded?

### Performance
- Query inside loop? N+1 pattern? Unbounded result set?
- Cache opportunities missed?

### Maintainability
- Function length < 40 lines?
- Cyclomatic complexity < 10?
- Naming: intention-revealing?

### Test Quality
- Coverage: new code paths have corresponding tests?
- Assertion quality: testing behavior, not implementation?
- Edge cases: nil, empty, boundary, error?

## Blocking conditions
- Any security axis < 3 → BLOCK with recommendation
- Any axis < 2 → BLOCK unconditionally
- No test for changed behavior → BLOCK
```

## Receipt

> Verified 2026-07-14 — Created S-1118 with full six-phase lifecycle, five-axis review rubric, and engineering principles. `agent-skills` repo (addyosmani, 78K stars) is the canonical reference. Pattern confirmed: coding agents need lifecycle-gated discipline, not just capability packages. Slash commands provide the activation mechanism; skills provide the discipline content. This is orthogonal to S-20 (skill architecture) and S-10 (MCP tool protocol) — it operates one layer above: the *workflow contract* that governs how tools are used in sequence.

## See also

- [S-20 · Agent Skills](s20-agent-skills.md) — The general skill architecture that SKILL.md sits on
- [S-10 · MCP](s10-mcp.md) — The capability layer that skills supplement
- [S-1103 · The Agent-Eval Stack](s1103-the-agent-eval-stack-when-passfail-tests-are-a-lie.md) — Eval rigor that complements skill-gated workflows
- [S-1010 · The Agent Eval Stack](s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — Test quality patterns
- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — Post-incident patterns for when skill-gates were bypassed
