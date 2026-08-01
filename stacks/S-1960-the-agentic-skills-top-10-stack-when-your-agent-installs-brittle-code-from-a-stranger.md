# S-1960 · The Agentic Skills Top 10 Stack — When Your Agent Installs Brittle Code from a Stranger

You shipped a coding agent to your engineering team. Someone installed a skill from the registry that generates test fixtures. Three weeks later, the skill starts sending API keys to an external endpoint on every invocation. The skill passed the install-time review — it had good stars, a clean-looking README, and a company name you recognized. What the review missed: the skill's `install` hook contained an obfuscated base64 payload. Your MCP permissions were wide open because the skill needed them for legitimate purposes. By the time the forensic log showed the exfiltration, 47 credentials were in the wild. The OWASP Agentic Skills Top 10 (AST10, v1.0, 2026) exists because the behavioral layer between the model and the tools became the primary attack surface — and nobody was watching it.

## Forces

- **Skills inherit the developer's full privilege scope.** When you install a skill, it gets the same access you have: source code, credentials, production systems. The install prompt is "grant access" — there is no capability model, no least-privilege negotiation.
- **Install-time review cannot catch runtime behavior.** A skill with a legitimate-looking README and clean source can execute credential-exfiltrating payloads via post-install hooks, obfuscated strings, or downstream dependency chains. Static review misses dynamic execution.
- **The skills ecosystem is under active attack as of Q1 2026.** The ClawHavoc campaign alone distributed 1,184 malicious skills across major registries. Snyk's ToxicSkills scan (Feb 2026) found 36.82% of 3,984 skills contained security flaws; 13.4% had critical vulnerabilities. These numbers predate most enterprise adoption waves.
- **Skills sit between MCP and the model — in the gap nobody owns.** MCP secures tool interfaces. LLM security secures the model. The behavioral layer — what a skill does with its access — falls between both frameworks. OWASP AST10 was created to fill exactly this gap.
- **Skill cardinality multiplies the blast radius.** A single compromised skill in a multi-agent workflow can propagate harm across every agent that uses it. Unlike a single malicious API call, a compromised skill persists across sessions.

## The move

**The mental model**: MCP = how the model talks to tools. AST10 = what those tools actually do. Skills encode workflow, permissions, tool orchestration, state, and sometimes executable install paths. They are the behavioral contract between your agent and the world.

### The ten risks (AST10, 2026)

| # | Risk | What it means | Real-world echo |
|---|------|---------------|-----------------|
| AST01 | Malicious Skills | Skills that exfiltrate credentials, modify files, or persist hidden instructions via install hooks or obfuscated code | ClawHavoc campaign (1,184 malicious skills, Antiy CERT, Feb 2026) |
| AST02 | Skill Supply Chain Vulnerabilities | Compromised dependencies, poisoned registries, dependency confusion attacks | GitHub MCP exploit (2025) |
| AST03 | Insecure Skill Installation Mechanisms | Unsafe install hooks, unsigned payloads, unverified download sources | WebSocket hijacking (CVE-2026-28363, Oasis Security) |
| AST04 | Skill Permission Overgrant | Skills requesting or inheriting more permissions than their function requires | Default-allow install flows in Claude Code, OpenClaw |
| AST05 | Unvalidated Skill Artifacts | Executable code, scripts, or binaries bundled in skill packages without sandboxing | Claude Code RCE (CVE-2025-59536/21852, Check Point Research, Feb 2026) |
| AST06 | Skill Memory & State Poisoning | Skills that corrupt agent memory or persist malicious state across sessions | Cross-session behavioral drift from compromised skills |
| AST07 | Insecure Skill-to-Skill Communication | Skills communicating without authentication, enabling lateral movement | Inter-skill credential passing on shared memory stores |
| AST08 | Skill Observability Gaps | Skills that execute without trace, audit, or telemetry — actions invisible to security tooling | No skill-level span in most agent observability stacks |
| AST09 | Insecure Skill Update Mechanisms | Skills that auto-update from unverified sources, swapping benign code for malicious | Silent supply chain pivot on upgrade |
| AST10 | Overtrusted Skill Ecosystem | Registries with no provenance verification, no vulnerability scanning, no incident response | 76 confirmed malicious payloads in production registries (Q1 2026) |

### The lethal trifecta

Three conditions that make a skill compromise catastrophic:

1. **Same-privilege install**: the skill runs with your identity, not a sandboxed one
2. **Multi-step autonomy**: the skill can plan and act across multiple tools without per-step authorization
3. **Persistent memory**: the skill can write to agent memory, persisting its influence across sessions

When all three converge, a single malicious install is indistinguishable from a trusted workflow — until the credentials are gone.

### The defense stack

**Pre-install phase:**

```bash
# 1. Scan before install
npx skill-scan --security <skill-name>
# Checks: dependency graph, install hooks, network calls, credential access patterns

# 2. Verify provenance
sigstore verify --bundle <skill>.bundle <skill-name>
# Ensures the skill was built and signed by the claimed identity

# 3. Dry-run in sandbox
skill run --sandbox --read-only <skill-name>
# Observe actual behavior before granting production access
```

**Install-time controls:**

```yaml
# skill-policy.yaml — enforce least-privilege at install
skills:
  allowed_sources:
    - https://registry.company.com
    - https://github.com/verified-org
  require_signature: true
  sandbox_by_default: true
  max_permission_tier: read   # no write, no exec, no network by default
  audit_installation: true
```

**Runtime controls:**

```python
# Skill permission tiering — don't grant what you don't need
SKILL_TIERS = {
    "test_fixtures": {"network": False, "filesystem": "tmp/", "secrets": []},
    "code_review":   {"network": True,  "filesystem": "ro/", "secrets": ["read:github"]},
    "deployment":   {"network": True,  "filesystem": "prod/", "secrets": ["*"], "require_approval": True},
}
```

**The Universal Skill Format proposal (AST10):**

AST10 proposes a standard skill manifest that declares: required permissions, data access scope, install hooks, update source, and security contact. Registries that enforce this format give security teams a machine-readable contract — not a README — before granting access.

```yaml
# skill.yaml — proposed universal format
apiVersion: ast10/v1
skill:
  name: code-reviewer
  permissions:
    - type: repository
      access: read
    - type: network
      targets: ["github.com"]
  installHooks: []       # empty = no hooks
  updateSource: https://registry.company.com/updates/code-reviewer
  securityContact: security@company.com
  sbom: sha256:abc123...
```

### Detection: the skill observability gap

Most agent observability stacks capture tool calls and LLM tokens — but not skill-level execution. Add skill spans to your trace:

```python
from opentelemetry import trace

tracer = trace.get_tracer("agent.skills")

with tracer.start_as_current_span("skill.execute") as span:
    span.set_attribute("skill.name", skill_name)
    span.set_attribute("skill.source", skill_source)
    span.set_attribute("skill.permissions.granted", permissions)
    # ... skill execution ...
    span.set_attribute("skill.actions.taken", actions)
```

Without skill-level tracing, a compromised skill's actions are invisible to your SIEM.

## Receipt

> Verified 2026-08-01 — OWASP Agentic Skills Top 10 (AST10) v1.0 published at owasp.org/www-project-agentic-skills-top-10 (Jun 2026). Snyk ToxicSkills scan (Feb 2026): 3,984 skills scanned, 36.82% with security flaws, 13.4% critical. ClawHavoc campaign: 1,184 malicious skills (Antiy CERT, Feb 2026). Claude Code RCE: CVE-2025-59536/21852 (Check Point Research, Feb 2026). WebSocket hijacking: CVE-2026-28363 (Oasis Security). Skill cardinality point: MCP secures interfaces, LLM security secures the model — the behavioral layer (skills) falls between both. The three-layer attack model (same-privilege install + multi-step autonomy + persistent memory) confirmed across multiple AST10 entries.

## See also

- [S-641 · Environment-Injected Memory Poisoning](s641-environment-injected-memory-poisoning.md) — AST06 overlaps with persistent memory exploitation; different vector, same defense layer
- [S-365 · MCP Supply Chain](s365-mcp-supply-chain-from-npx-to-production-catalog.md) — SBOM and artifact provenance for tool layers; extend to skills
- [S-1458 · Policy-Kernel Agent Stack](S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — OWASP ASI Top 10 (application layer) enforcement; AST10 is the behavioral/skill layer beneath it
