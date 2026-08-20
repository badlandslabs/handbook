# S-2890 · The Scoped Harness Stack — When Your Company Has an Agent Workforce Without an Organizational Chart

Y Combinator open-sourced [QM](https://github.com/yc-software/qm) on July 31, 2026 — the system it built after running 50+ individual Hermes agents internally and discovering that the personal-assistant model breaks the moment you give agents to a whole company. The lesson was architectural, not operational: the problem was not *which* agent to use. It was *how to organize agents the way you organize people* — with scopes, isolation, and explicit collaboration protocols. The 2026 scoped harness pattern solves this by treating scope as the primary security primitive.

## Situation

You want to give every employee an AI agent. Your first instinct is to provision one shared agent for the company, or one personal agent per employee and let them figure out collaboration. Both fail. The shared agent has blast radius proportional to its access. The personal agents can't collaborate without sharing credentials. What you actually need is the organizational chart pattern applied to agents: each employee gets a scoped workspace, collaboration happens through explicit channels, and every agent's blast radius is bounded by its scope.

## Forces

- **Personal agents can't collaborate.** A personal agent has one employee's identity, tools, and memory. When two employees need their agents to coordinate — one drafting a contract, another reviewing it — there is no shared protocol. They share credentials, which means they share blast radius.
- **Shared agents can't isolate.** One agent serving the whole company means every employee's data, tools, and credentials live in the same context. One prompt injection in one Slack thread compromises all of them.
- **Fleet management comes after the architecture problem.** [S-1223](s1223-the-fleet-cockpit-stack-when-you-have-12-agents-and-no-idea-what-any-of-them-are-doing.md) (Fleet Cockpit) governs deployed agents. The scoped harness pattern is the architectural layer that makes fleet governance tractable — because every agent has a defined scope, every policy maps to a scope boundary.
- **Vendor lock-in is an organizational risk.** If your agent harness is tied to one model provider, switching models means re-scoping every agent. The core must be harness-agnostic so the organizational structure is independent of the reasoning engine.
- **Security posture is per-scope, not per-agent.** An employee's agent should have access to *that employee's* tools, not the company's. Scope defines the blast radius before the agent is even prompted.

## The move

Build a scoped harness — an agent architecture where scope is the primary organizational unit, not an afterthought.

### 1. Scope as First-Class Primitive

Every agent runs inside a named, isolated workspace. Scopes are hierarchical:

```
org/
  company-wide/     ← shared knowledge, company policies, public data
    team-finance/   ← team shared scope
      alice/        ← alice's personal scope (extends team scope)
      bob/          ← bob's personal scope (extends team scope)
    team-engineering/
      carol/
      david/
```

A personal scope *inherits* from its parent team scope. Alice's agent can access team-finance context plus her personal context. It cannot access bob's personal scope without explicit cross-scope protocol.

### 2. Per-Scope Resources

Each scope owns:

| Resource | Scope-level | Example |
|----------|-------------|---------|
| Memory | Personal | Alice's preferences, ongoing tasks, Slack history |
| Files | Personal | Alice's drafts, uploaded documents |
| Keychain | Personal | Alice's API credentials, OAuth tokens |
| Permissions | Scoped | Alice's Zephyr read, Notion write, billing read |
| Crons | Scoped | Nightly digest for Alice's projects |
| Sandboxes | Per-task | Durable execution environments, isolated per task |

This means the same agent model can run as Alice's assistant (with Alice's permissions) or as the finance-team agent (with team permissions). The model doesn't change. The scope does.

### 3. Collaboration Through Explicit Channels

Agents collaborate by operating in shared scopes, not by sharing personal credentials:

- **Channels** — a shared scope for a team or project. All agents in the channel see the shared memory, files, and context. Any agent can act on behalf of the channel with channel-level permissions.
- **Projects** — temporary shared scopes for cross-functional work. Engineering and legal collaborate on a contract review in a project scope; when the project ends, the scope is archived.
- **Cross-scope protocol** — an agent in Alice's scope requesting access to Bob's scope triggers a formal protocol: Alice's agent sends a scoped request, Bob (or Bob's agent) approves, a temporary cross-scope token is issued with a TTL.

This is the key architectural difference from personal-assistant agents: collaboration is a first-class construct, not an accidental sharing of credentials.

### 4. Vendor-Agnostic Core

The harness core must be model-agnostic. The scope configuration, tool definitions, permission policies, and collaboration protocols are all harness-independent. You can swap Pi for Claude Code without redefining the organizational structure:

```typescript
// Scope definition — model-agnostic
const scope = {
  id: 'alice',
  parent: 'team-engineering',
  resources: {
    memory: 'pg://scopes/alice/memory',
    files: 's3://scopes/alice/files',
    keychain: 'vault://scopes/alice/credentials',
  },
  permissions: [
    { tool: 'linear_read', scope: 'project/*' },
    { tool: 'github_read', scope: 'org/repos/engineering' },
  ],
  agent: { harness: 'claude-code', model: 'claude-sonnet-4-20250514' },
};
```

YC QM supports Pi, OpenCode, Codex, and Claude Code interchangeably through this abstraction.

### 5. Governance Envelope

The org-level configuration layer sits *above* scopes, not inside them:

- **Security posture** — org-wide policy: no agent may send data to unapproved destinations, all file writes require audit log, PII access requires human approval gate.
- **Harness availability** — which harnesses are approved for which teams.
- **Tool allowlists** — which tools are permitted at org, team, and personal scope.
- **Audit trail** — every action is logged with `[scope, agent, action, timestamp, tool, resource]`. Bob's agent cannot exfiltrate Alice's files without both scopes appearing in the audit log.

### 6. The Threat Model

Scoped harnesses have two primary failure modes:

**Resource leakage across scopes.** A compromised or misprompted agent in Alice's scope tries to read Bob's memory. Mitigation: zero-trust per-scope enforcement. Every resource access checks scope membership. No implicit inheritance of cross-scope resources.

**Over-privileged agent.** An agent with too many tools or too broad permissions uses one to escalate. Mitigation: least-privilege scope provisioning. Start with the minimum tools for the stated purpose. Add tools through explicit approval, not default.

The governance envelope catches both through the audit trail — because every action is scope-tagged, privilege escalation shows up as a scope boundary crossing that wasn't through the formal cross-scope protocol.

## Contrast with Related Patterns

| Pattern | What it governs | Scoped harness adds |
|---------|-----------------|---------------------|
| [S-1223 Fleet Cockpit](s1223-the-fleet-cockpit-stack-when-you-have-12-agents-and-no-idea-what-any-of-them-are-doing.md) | Fleet-level visibility and registry | Architecture layer that makes fleet governance tractable (every agent has a defined scope) |
| [S-2847 Non-Human Identity Void](S-2847-the-non-human-identity-void-stack-when-your-agent-has-no-birth-certificate-no-passport-and-full-admin-access.md) | Agent identity and credential lifecycle | Scope provides the identity container — each scoped agent has a defined identity tied to its scope, not to a shared service account |
| [S-2885 Agent Tool Stack](s2885-the-agent-tool-stack-when-the-model-is-capable-but-the-agent-is-powerless.md) | What tools the agent can use | Scoped harnesses define tool access at scope level, not per-agent — a capability property, not an architectural primitive |
| [S-2883 Agent Memory Stack](s2883-the-agent-memory-stack-when-your-context-window-is-not-persistent-storage.md) | Persistent memory architecture | Scoped memory: personal scope memory is private, team scope memory is shared, cross-scope memory access follows the collaboration protocol |

## Implementation Sketch

```typescript
// Minimal scoped harness boot
import { createHarness } from '@qm/core';
import { createSlackPlugin } from '@qm/plugin-slack';

const harness = createHarness({
  core: { storage: 'postgres', sandbox: 'durable' },
  plugins: [createSlackPlugin({ channels: true })],
});

// Provision a personal scope
await harness.scope.provision({
  id: 'alice',
  parent: 'team-engineering',
  harness: 'claude-code',
  permissions: ['linear_read', 'github_read', 'docs_read'],
});

// Alice's agent is now scoped — can access team context + personal context,
// cannot access other personal scopes without cross-scope protocol
```

Start with two scopes: `personal` and `company-wide`. Add `team` scopes when the first cross-functional collaboration is needed. The hierarchy grows with organizational need, not architectural complexity.

## Receipt

> Verified 2026-08-19 — YC QM (github.com/yc-software/qm) open-sourced July 31, 2026, MIT license, 7,500+ stars in 3 days. Pattern distilled from QM architecture (TypeScript/Fastify/Postgres core, Slack Bolt plugin, per-scope memory/files/keychain/permissions, vendor-agnostic core supporting Pi/OpenCode/Codex/Claude Code). QM's key claim: twice as much code governs access control as drives the model — validating that the governance envelope is the primary engineering investment, not the agent itself. Cross-validated against S-1223 (fleet governance), S-2847 (non-human identity), S-2885 (tool scope), S-2883 (scoped memory).

## See also

- [S-1223 · The Fleet Cockpit Stack](s1223-the-fleet-cockpit-stack-when-you-have-12-agents-and-no-idea-what-any-of-them-are-doing.md) — fleet-level governance built on top of scoped architecture
- [S-2847 · The Non-Human Identity Void Stack](S-2847-the-non-human-identity-void-stack-when-your-agent-has-no-birth-certificate-no-passport-and-full-admin-access.md) — identity becomes tractable when each scope has a defined identity
- [S-2885 · The Agent Tool Stack](s2885-the-agent-tool-stack-when-the-model-is-capable-but-the-agent-is-powerless.md) — tool scope as a capability property, not an architectural primitive
