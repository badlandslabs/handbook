# S-2010 · The Constraint Decay Stack — When Your Agent Prototypes Fine but Falls Apart in Production

Your agent generates a Flask backend from a prompt in seconds. Tests pass. You're impressed. Then you ask for PostgreSQL + SQLAlchemy + JWT auth + role-based access + migration scripts, and the agent starts silently substituting SQLite, forgetting auth middleware, and generating ORM models that don't match the schema. This is not a model quality problem. This is constraint decay — the systematic degradation of an agent's structural compliance as requirements accumulate.

## Forces

- **Functional correctness masks structural failure.** An agent can generate a working API endpoint while violating every architectural convention in your stack. Your functional tests pass. Your code review finds disaster.
- **Benchmarks reward prototype-quality output.** SWE-bench, WebArena, and similar benchmarks reward functionally correct but structurally arbitrary solutions. They are not measuring whether an agent can follow your team's patterns — they're measuring whether it can solve toy problems.
- **Constraint stacking is the norm in production.** Real backend tasks require PostgreSQL, SQLAlchemy ORM, JWT middleware, role-based access, migration scripts, API versioning, and error handling — all simultaneously. Every added constraint reduces agent reliability.
- **Data-layer defects drive ~45% of logic failures.** When agents do fail on constrained tasks, nearly half the failures originate in data-layer code — ORM models that don't match schemas, queries that skip joins, missing foreign key constraints. Agents optimize for what looks like a correct response, not what actually works in your database.
- **The omission constraint decay effect.** Behavioral constraints (prohibitions, access rules) degrade monotonically with conversation depth and context length. The longer a multi-session agent runs, the more likely it is to violate rules it was explicitly given.

## The move

The evaluator-optimizer loop with structural quality gates: separate code generation from structural validation, feed failures back as constraints, and enforce architecture compliance before any generated code reaches review.

- **Structural test suite as the gate, not code review.** Write tests for architectural constraints (ORM models match schema, auth middleware present, correct query patterns) before you generate code. These are the quality gates. The agent must pass them, not just pass a human review.
- **Evaluator LLM scores generated code against a constraint manifest.** Before accepting output, a second LLM (or structured rule-checker) evaluates whether the generated code satisfies each structural requirement: database choice, ORM pattern, middleware stack, error handling approach. This is not the same as running functional tests — it's validating form.
- **Feed constraint failures back to the generator in the next loop.** When structural tests fail, the error output becomes part of the next generation prompt. This is the evaluator-optimizer feedback loop (Anthropic Cookbook) — it forces the generator to confront its structural failures rather than regenerate the same pattern.
- **Use architectural scaffolds as generation context.** Provide the agent with a minimal working scaffold of your target stack — a single correct model, a single correct route — before generation. Research shows this reduces decay significantly because the agent has concrete structural examples to ground against.
- **Cap agent iterations and enforce escalation.** Set hard limits on regeneration attempts (3-5 loops). After N failures, escalate to human review or reject the task as requiring a different approach. Constraint decay is not solvable by more retries — it requires a different strategy.
- **Monitor constraint compliance over conversation depth.** Track per-session constraint violation rates. If an agent's omission constraint compliance drops as context grows (the Security-Recall Divergence pattern), re-inject the constraint manifest mid-session to restore baseline compliance.

## Evidence

- **Research (arXiv 2605.06445):** Systematic study of 10 LLMs × 8 web frameworks × 80 backend generation tasks. Assertion pass rates drop by **30 percentage points average** from unconstrained baseline to fully-specified production tasks. Framework choice compounds the gap — convention-heavy frameworks like Django produce 25-32pp worse results than lightweight ones like Flask, because agents must satisfy more implicit structural rules. Data-layer defects account for **~45% of logic failures**. — [https://arxiv.org/abs/2605.06445](https://arxiv.org/abs/2605.06445)

- **HN Discussion (287 points, 197 comments):** Practitioners confirm the pattern from production experience. One commenter: "My agent will often make over 100 tool calls to sql and git before it finally decides to apply a patch. If I was greenfield, there would be nothing to query or constrain against." The thread consensus: functional tests are necessary but insufficient — structural validation must be explicit and automated. — [https://news.ycombinator.com/item?id=48256912](https://news.ycombinator.com/item?id=48256912)

- **Practitioner Analysis (LucidShark, May 2026):** Confirms the paper's findings and adds mitigation context: the evaluator-optimizer pattern, structural test suites, and architectural scaffolding as the practical response. Notes that constraint decay is "not a benchmark complaint. It is a description of what happens in your codebase every day." — [https://lucidshark.com/blog/constraint-decay-llm-agents-backend-code-quality-gates-2026](https://lucidshark.com/blog/constraint-decay-llm-agents-backend-code-quality-gates-2026)

## Gotchas

- **Writing functional tests is not enough.** Functional tests verify that the API returns the right status code. They say nothing about whether the agent used PostgreSQL or SQLite, whether the ORM models have the right relationships, or whether auth middleware is present. You need structural tests that verify form, not just function.
- **Re-generating the same way produces the same failure.** If an agent fails structural constraints and you just re-prompt without new information, it regenerates the same pattern. The evaluator-optimizer loop requires that failure output feeds back as constraint context — the agent must know *why* it failed, not just that it failed.
- **Convention-heavy frameworks amplify decay.** Django, Rails, and similar batteries-included frameworks impose more implicit structural rules than Flask or Express. Agents working against these stacks face a compounding disadvantage — every convention is a constraint, and constraints decay together.
- **The prompt re-injection mitigation has a cost.** Re-injecting constraint manifests to combat conversation-depth decay increases token usage and context length. This is a tradeoff against the cost of structural violations — you pay either way.
- **Benchmarks will keep claiming agents are "production ready."** They measure the wrong axis. Treat benchmark leaderboard positions as a measure of prototype capability, not production reliability. The gap between the two is exactly constraint decay.
