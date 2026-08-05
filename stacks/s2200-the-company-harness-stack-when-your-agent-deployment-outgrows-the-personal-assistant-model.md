# S-2200 · The Company Harness Stack: When Your Agent Deployment Outgrows the Personal Assistant Model

Your demo worked on one laptop. Your company wants it to work for 300 people. Now every employee needs their own memory, every shared channel needs scoped access, every cron needs approval gates, and your "agent" has become infrastructure. The personal assistant paradigm — one agent per person — doesn't survive contact with an org.

## Forces

- **Isolation vs. collaboration tension.** Personal workspaces need strict isolation so one employee's agent doesn't bleed into another's context. But teams also need shared rooms, group projects, and cross-scope memory. Both requirements exist simultaneously and conflict.
- **Security surface explodes with every new user.** When an agent has access to your company's Slack, email, database, and code — and you give that to every employee — access control becomes the primary engineering challenge, not the agent logic.
- **Fleet management replaces agent tuning.** At 50+ agents, individual agent quality matters less than the infrastructure that manages them: deployment, monitoring, permission propagation, credential rotation, and incident response across the whole fleet.
- **Governance is load-bearing, not optional.** Personal agents can be whimsical. Company agents that touch accounting, legal, and engineering need audit trails, approval workflows, and org-level policy enforcement that aren't afterthoughts — they're the product.
- **Vendor lock-in compounds at scale.** A personal agent harness tied to one model provider is an acceptable risk. A company-wide deployment locked to one provider is a procurement problem and a continuity risk.

## The Move

The move is building an **organizational harness** — a governance and coordination layer that wraps the agent loop, not just wrapping the agent itself.

- **Scope-based isolation as the default architecture.** Every employee, project, and department gets an isolated agent workspace with its own memory, files, keychain, permissions, and durable sandbox. Nothing crosses scope without an explicit grant.
- **Separate the agent loop from the coordination shell.** Keep the core agent logic clean and model-agnostic (YC's QM runs Pi, OpenCode, Codex, and Claude Code interchangeably against the same core). Put identity, policy, scheduling, and fleet management in the outer shell. The shell is TypeScript; the agent is swappable.
- **Governance dominates the codebase.** YC's QM has 26 access-control files vs. 13 for the model-calling loop. When you count the files that matter in a company harness, security and policy outnumber the AI code. Budget for this ratio.
- **Human-in-the-loop as a first-class primitive.** Not as a fallback, but as a scheduled skill and an approval gate. Crons and watches run work autonomously, but high-stakes actions (deploying code, sending external email, touching financial data) require human confirmation. Build this into the skill system, not as an afterthought.
- **Shared skills with org-gated promotion.** Skills are scope-owned initially and promotable to the whole org with admin approval. This lets teams experiment with agent capabilities without requiring org-wide review of every experiment.
- **Durable state in Postgres.** Sessions, memory, and queue all live in Postgres. This gives you auditability, replay, and the ability to replay any agent action. It's not optional for a company harness — it's the compliance layer.
- **Multi-surface access (Slack + web) with a single identity.** The same agent identity and configuration must work identically whether the user is in Slack or the web app. Split-brain identities break user trust and create security gaps.

## Evidence

- **GitHub/Primary source:** Y Combinator open-sourced QM (quartermaster) on July 31, 2026 — the exact harness it runs across accounting, legal, events, and engineering. 11,600+ GitHub stars in under a week. Architecture: TypeScript core on Node, Postgres for sessions/memory/queue, Slack + web UI, vendor-neutral agent drivers (Pi/OpenCode/Codex/Claude Code), scoped workspaces with org-gated skill promotion, crons + watches for background work, and 26 access-control files in a codebase of ~60 core modules. Used QM to build QM itself. — [https://github.com/yc-software/qm](https://github.com/yc-software/qm)
- **Primary source (YC project page):** YC traces its evolution: basic Ruby agent loop → Hermes personal agents for 50+ employees (hit fleet management ceiling) → QM as a company-wide multiplayer harness. Explicitly frames QM as the solution to "managing a fleet of even this size became challenging." The design lesson: personal assistant tools don't scale to orgs without structural redesign. — [https://qm.ycombinator.com/](https://qm.ycombinator.com/)
- **News/Discussion:** The HN thread on QM received 672 points and 165+ comments within days. Commenters with production experience flagged the critical gaps: "The moment you have >5 users, your agent needs role-based access control, audit logs, and the ability to impersonate users" — validating that org-scale requirements are qualitatively different from personal use. — [https://news.ycombinator.com/item?id=49126604](https://news.ycombinator.com/item?id=49126604)

## Gotchas

- **Don't copy the personal assistant model and call it company software.** Adding more users to a single-agent deployment doesn't produce an org harness — it produces a shared chaos. Scoping, isolation, and governance are structural requirements, not features.
- **The skills system will become your most politically charged code.** Who approves skills? Who can promote them org-wide? Who audits what a skill can access? These questions will consume more engineering time than the agent loop itself.
- **Vendor neutrality sounds free but costs integration.** Running Claude Code and OpenCode against the same core sounds elegant. The reality is normalizing tool schemas, handling different context windows, and mapping different failure modes across providers. Build the abstraction, but budget for the surface area.
- **Durable state is not optional for compliance.** If your agents touch regulated data (finance, legal, healthcare), Postgres-backed sessions with full replay capability aren't a nice-to-have — they're the audit trail your legal team will demand during the first incident.
