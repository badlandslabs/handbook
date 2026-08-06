# S-2254 · The SKILL.md Context Poisoning Stack: When Your Agent's Skill File Is the Attack Vector

Your agent installs a capability package from a marketplace — a coding skill, a security scanner, a data pipeline helper. The install succeeds, the agent loads the new capability, and nobody reads the file. What they don't know: the markdown contains adversarial instructions embedded in prose, Unicode homoglyphs, and external references that the model executes as behavioral directives. This is SKILL.md context poisoning — and it is the agentic equivalent of a malicious npm package, but the attack surface is natural language that humans rarely audit.

## Forces

- **Skill files are trusted context, not code.** Unlike a Python package that gets static analysis or sandboxing, a skill file is injected into the model's context window as instructions. The model reads it as behavioral directive, not as "content to be validated." There is no equivalent of `npm audit` for the behavioral intent of a markdown file.
- **Natural language is a perfect cloaking mechanism.** Malicious instructions embedded in prose are invisible to both automated scanners and human reviewers skimming the README. Unicode homoglyphs, zero-width characters, and commented-out sections compound the problem.
- **Marketplace trust bleeds into model trust.** When an agent installs a "verified" skill from a reputable marketplace, the model's context inherits the trust signal — it has no mechanism to distinguish "verified as functional" from "verified as safe."
- **Poisoning is persistent and cross-session.** Unlike a prompt injection in a single conversation (LLM01), a poisoned skill file persists in the agent's loaded capabilities across sessions, user interactions, and deployments. The agent carries the malicious directive indefinitely until the skill is removed.
- **Existing coverage is asymmetric.** S-1426 covers MCP tool poisoning (schema metadata in MCP server responses). S-1062 covers MCP supply chain CVEs (vulnerable server code). Neither covers the natural-language behavioral instruction layer inside markdown skill files distributed as trusted context packages.

## The move

### 1. Audit skill files as untrusted input

Treat every skill file — whether from a marketplace, a colleague's PR, or an internal repository — as untrusted content that enters the model's instruction stream. This is the fundamental shift: skills are not configuration, they are prompt injection delivered through a trust heuristic.

```
Skill file → behavioral directive → model execution
     ↑                    ↑
  human trusts       model trusts
  the marketplace    the content
```

Apply the same scanning pipeline you'd apply to any untrusted input:
- Semantic content analysis: use an LLM-as-judge to check if the file contains behavioral directives that contradict the skill's stated purpose (e.g., a "code formatter" skill that instructs the model to exfiltrate variables)
- Static text analysis: scan for zero-width characters, Unicode homoglyphs, and hidden text
- Reference auditing: if the skill fetches external resources (URLs, other files), verify those are scoped and non-executable
- Provenance signing: only load skills from sources that cryptographically sign their behavioral intent

### 2. Implement a skill sandbox layer

Isolate skill-loaded context from sensitive operations:

- **Scope the skill's authority.** When a skill file loads, it should declare explicit boundaries: which tools it can call, which data it can access, which system capabilities it can invoke. Reject skills that request overly broad authority (e.g., a "code reviewer" skill that requests file write access without justification).
- **Separate skill context from privileged context.** Load skill files into a non-privileged context slot. If the skill's instructions attempt to escalate privilege (access admin tools, modify security settings), the escalation attempt should fail silently — the skill can only operate within its declared scope.
- **Skill session boundary.** Skills that modify state (file writes, API calls, database changes) should operate in a sandboxed session with automatic rollback. Poisoning that triggers a state change should not persist.

### 3. Enforce a skill manifest with behavioral assertions

Every skill in the agent's capability set should have a machine-readable manifest that declares:

```yaml
skill_name: code-formatter
declared_intent: "Format Python and JavaScript code"
authority_scope:
  read: ["*.py", "*.js"]
  write: ["*.py", "*.js"]
  network: none
  system: none
required_tools: ["read_file", "write_file"]
prohibited_patterns:
  - "ignore previous instructions"
  - "SYSTEM"
  - "sudo"
  - "rm -rf"
external_references: []
```

Before loading the skill, verify the manifest against the actual content. If the file contains instructions outside the declared scope, reject it.

### 4. Monitor for behavioral deviation after skill installation

Install behavioral telemetry before loading any new skill:

- Track tool call patterns, data access patterns, and network call targets before and after skill load
- If the skill causes the agent to access tools or data outside its declared manifest scope, alert and quarantine
- Run a probe task: give the agent a benign task after skill installation and verify the agent doesn't attempt out-of-scope operations

### 5. Maintain a skill bill of materials

Treat skill dependencies like software dependencies:

```bash
# Track every skill your agent loads
skill inventory --export=bom.json
# Compare against known-safe baseline
skill audit --diff=bom.json --baseline=known-good.json
```

The bill of materials lets you respond to a disclosed vulnerability: if a skill file is later found to be malicious, you can enumerate every agent that loaded it and trigger a revocation workflow.

## Receipt

> **Verified 2026-08-06** — Drawn from CSA AI Safety Initiative research (May 2026), Snyk's ClawHub audit finding 37% of skills malicious, and the OWASP ATLAS/ASI06 classification of persistent memory/context poisoning as a distinct attack class. Specific attack primitives confirmed: zero-width Unicode in prose, external URL references in skill bodies, disguised behavioral directives in README sections. No existing handbook entry covers this attack class — S-1426 covers MCP schema poisoning, S-1062 covers MCP CVE supply chain, neither covers natural-language behavioral instruction files as a delivery vector.

## See also

- [S-1426 · The MCP Tool Poisoning Stack](s1426-the-mcp-tool-poisoning-stack-when-your-tool-metadata-is-the-attack-vector.md) — schema-level poisoning in MCP servers
- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — CVE-level supply chain risk
- [S-1127 · The Cross-User Memory Contamination Stack](s1127-the-cross-user-memory-contamination-stack-when-user-b-sees-user-as-private-notes.md) — context bleed between sessions
- [S-1136 · The Context Sanitization Gate Stack](s1136-the-context-sanitization-gate-stack-when-your-agent-treats-retrieval-noise-as-ground-truth.md) — filtering untrusted retrieval noise
