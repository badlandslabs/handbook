# S-2534 · The Agent Authorization Stack — When Your Agent Proposes but Nobody Checks

Your agent decides to send an email to the CEO. It decides to delete 50,000 rows from the production database. It decides to transfer money. In every production agent framework, the model proposes a tool call and the framework executes it. There is no authorization gate between intent and side effect. Most agent systems are fail-open by default — once the model chooses an action, it runs. This is the agent authorization problem: the missing security layer between model decision and world-changing side effects.

## Forces

- **Generality vs. control** — agents need broad tool access to be useful, but broad access means every wrong decision can fire
- **Latency vs. safety** — policy evaluation adds per-call latency; skipping it means unbounded blast radius
- **Framework-level vs. application-level** — neither the LLM provider nor the orchestration framework enforces what the agent is allowed to do in context; that is the application's job, and most applications don't have it
- **Authorization vs. alignment** — alignment keeps the model from wanting to do wrong things; authorization keeps it from doing them even when it thinks they are right
- **Hardcoded allowlists vs. dynamic policy** — static allowlists break under tool schema changes; dynamic evaluation based on runtime context requires infrastructure

## The move

The agent authorization layer is a pre-execution gate: it sits between the model's tool-call decision and the tool's actual execution, evaluating a policy against the call's parameters, the agent's role, and the current session context.

**Architecture:**

- **Pre-execution hook** — the enforcement point: after the model outputs a tool call, before side effects occur. This is the correct boundary, not output filtering or post-hoc logging.
- **Fail-closed default** — deny-by-default with explicit allowlist for each agent/role. FailWatch (GitHub, Ludwig1827) implements this as a circuit breaker pattern: any uncaptured tool call trips the breaker.
- **Policy engine** — evaluates tool name, parameter values, session context (is the user present? what is the dollar amount?), and role bindings. The Open Agent Passport (OAP) standard from aport.io defines the structured policy format for this.
- **Three-tier enforcement response:** allow (proceed), reject_content (block but continue with a message to the model), raise_exception (halt execution entirely).
- **Role-based scoping** — instead of per-action allowlists, assign agents roles; each role carries a policy document that enumerates permitted tool categories and parameter constraints. This survives tool schema evolution.
- **Parameterized constraints** — policy not just on tool name but on parameter values: "can call `send_email` but `recipient` must match `@company.com$`."

## Evidence

- **Engineering blog:** Anthropic's multi-agent research system (Jun 2025) — "A multi-agent system consists of multiple agents (LLMs autonomously using tool loops) working together" — describes tool design as the critical engineering surface, with subagents acting as "intelligent filters" that compress findings before handoff. This positions tool interface design as a first-class security and reliability concern, not an implementation detail. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Primary source (HN Show HN):** Aport.io's authorization layer post — documents the fail-open problem explicitly: "Most agent systems today are 'fail-open': the model proposes an action, the framework executes it." Proposes OAP standard with pre-execution enforcement. HN thread 47235484, Mar 2026. — [news.ycombinator.com/item?id=47235484](https://news.ycombinator.com/item?id=47235484)
- **Security research:** Wiz.io's LLM guardrails taxonomy — categorizes guardrails across input, output, and tool-execution layers; identifies the enforcement point distinction (pre-execution catches side effects, not just bad outputs). Notes that prompt injection is the primary bypass mechanism, and that "provider-level content filters" are intentionally generic and insufficient for application-specific policy. — [wiz.io/academy/ai-security/llm-guardrails](https://www.wiz.io/academy/ai-security/llm-guardrails)
- **Open-source implementation:** FailWatch (Ludwig1827) — a fail-closed circuit breaker for AI agents; any tool call not explicitly captured in the allowlist triggers an exception rather than executing. GitHub + HN thread 46529092. — [github.com/Ludwig1827/FailWatch](https://github.com/Ludwig1827/FailWatch)
- **Framework layer:** Guardrails AI — production guardrails framework with per-tool-call hooks, structured response types (allow/reject_content/raise_exception), and integration across LLM providers. — [guardrailsai.com](https://guardrailsai.com/)

## Gotchas

- **Authorization is not authentication** — knowing who the agent is answers nothing about what it is allowed to do. These are separate layers and must be designed separately.
- **Post-hoc logging is not authorization** — logging what the model did after the side effect occurs is audit, not enforcement. By the time you log, the email is sent or the row is deleted.
- **Allowlists rot** — a static allowlist tied to tool names breaks when the framework version bumps and the tool schema changes. Tie policies to tool categories and parameter patterns, not exact names.
- **The model can be socially engineered** — prompt injection can induce the model to call a permitted tool with malicious parameters (e.g., send_email with a forged recipient). Parameter-level policy constraints (regex on values, not just tool names) catch this.
- **Sandboxing is not authorization** — running the agent in a sandbox prevents some classes of damage but not all (wrong data operations, spam, financial transactions within permitted surfaces). Authorization and sandboxing are complementary, not substitutes.
