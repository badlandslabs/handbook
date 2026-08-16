# S-2728 · The VulMask Stack — When Your Skill Security Review Cleared Something It Couldn't See

Your security team audits every skill before installation. Static scanner: clean. SKILL.md review: clean. The skill ships. Three months later, credentials start appearing at an external endpoint. The forensic reconstruction: the skill's auxiliary script — the one your scanner never deeply analyzed — contained a vulnerability-shaped payload that activated only when `$CI_COMMIT_REF_SLUG` matched a specific pattern. Your scanner cannot see trigger conditions. It never could.

## Forces

- **Static scanners match signatures, not behavior.** VulMask rewrites malicious scripts into vulnerability-shaped implementations — code that looks like a common SQL-injection-prone helper, not a backdoor. Signatures for "malware" fire; signatures for "vulnerable code" do not.
- **SKILL.md review misses the execution layer.** The attack surface is in `scripts/`, not in the skill description. Reviewers read the manifest, not every shell script, template, and dependency file.
- **Trigger conditions are invisible at install time.** VulMask activates malicious behavior only under attacker-controlled conditions (`$CI_COMMIT_REF_SLUG`, environment variables, network responses). In the review sandbox, those conditions never fire.
- **Skill ecosystems normalize wide privilege grants.** Skills request broad MCP permissions for legitimate reasons, creating a permission surface that obfuscated scripts can exploit at runtime.
- **The 58.8% attack success rate is the baseline, not the ceiling.** VulMask achieves 58.8% ASR against state-of-the-art scanners while preserving 96.6% of host skill utility. Refined variants can do better.

## The move

### 1. Separate the vetting layer from the execution layer

Never install a skill's auxiliary resources into a privileged environment for scanning. Spin up an ephemeral sandbox (no credentials, no network egress, no production filesystem) and run behavioral analysis against execution traces — not text patterns.

```
# Ephemeral scan wrapper (pseudocode)
scan_skill(skill_tarball):
    sandbox = launch_container(
        network=none,
        filesystem=empty,
        credentials=stripped
    )
    scripts = extract(skill_tarball, "scripts/*")
    for script in scripts:
        trace = execute_in_sandbox(script, timeout=30s)
        report = analyze_behavioral_trace(trace)
        if report.contains_egress() or report.contains_credential_access():
            flag(skill, severity=HIGH, evidence=trace)
```

### 2. Treat "vulnerable-looking code" as a red flag, not background noise

VulMask weaponizes common vulnerability patterns (SQL concatenation, `eval()` wrappers, shell injection in `subprocess`). A static scanner that flags these as warnings may suppress them as false positives. Instead: **any skill containing exploitable code patterns must pass enhanced behavioral review**. Low severity findings in combination are not low severity in aggregate.

```
# Countermeasure: pattern-as-signal, not pattern-as-noise
SUSPICION_SCORE = sum([
    has_sql_concat() * 0.3,
    has_dynamic_eval() * 0.4,
    has_env_condition() * 0.5,
    has_network_egress() * 0.6,
    has_credential_access() * 0.7,
])
if SUSPICION_SCORE > 0.6:
    escalate_to_security_team(skill, score=SUSPICION_SCORE)
```

### 3. Runtime containment is the only reliable defense

Skill scripts that pass static review must still run in a constrained execution environment. Apply the principle of least privilege per invocation — not per skill. Capability-based execution means the shell script that formats SQL gets a database connection token scoped to read-only; it does not get the MCP server's full OAuth session.

```
# Per-script capability scoping
SCRIPT_CAPS = {
    "format_sql.py":      ["db:read:analytics"],
    "lint_changes.py":    ["git:read", "stdout:write"],
    "fetch_deps.py":      ["network:allowlist:pypi.org"],
}
# No script gets more than its explicit allowlist
```

### 4. Monitor execution traces, not just outcomes

VulMask's trigger conditions depend on runtime environment variables and network responses. Instrument skill execution to log all environment variable reads, file accesses, and network calls — regardless of whether the script succeeded. A script that reads `$CI_COMMIT_REF_SLUG` during a review scan is a signal even if it doesn't exfiltrate anything.

### 5. Treat skill updates as new installs

VulMask's delayed-activation threat model relies on attackers inserting a dormant payload that updates to active code via a subsequent skill push. Require full behavioral re-review for every version bump. Semantic versioning trust is not warranted in a supply chain where the attacker's version bumps match the legitimate maintainer's.

## Receipt

> Verified 2026-08-16 — PhantomSkill (arXiv:2606.19191v1, Lin & Yu, June 2026) establishes VulMask baseline: 58.8% ASR against static scanners, 96.6% utility preservation, trigger-condition activation via environment variables (`$CI_COMMIT_REF_SLUG`, `$GITHUB_REF`). CodeX CLI runtime behavioral analysis catches 97% at 2% false-positive rate. CSA CloudAI report confirms 36.8% of community skills have exploitable vulnerabilities. OWASP Agentic Skills Top 10 B1-B4 covers supply chain trust boundaries. No existing handbook stack covers obfuscated auxiliary script execution or VulMask-class attacks — distinct from S-1960 (which covers SKILL.md injection and install hooks).

## See also

- [S-1960 · The Agentic Skills Top 10 Stack](/stacks/S-1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — the upstream supply chain problem; this chapter covers what survives S-1960's review
- [S-1458 · The Policy-Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — capability-based enforcement at the MCP boundary
- [S-2274 · The Isolation Spectrum Stack](/stacks/s2274-the-isolation-spectrum-stack-when-your-agent-runs-code-and-nobody-drew-the-fence.md) — sandbox primitives that make runtime containment viable
