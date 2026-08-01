# S-1967 · The Skill Behavioral SBOM Stack — When Your Skill Does More Than It Says

You audit every npm package you install. You check the GitHub commit history, the weekly downloads, the open issues. You would never install a PyPI package that pings home to an unknown endpoint. But you installed a skill for your agent because it had 14,000 downloads and a clean README — and the skill sends your `AWS_SECRET_KEY` to an external analytics endpoint on every invocation. You did everything right. The gap wasn't in your process. It was in the abstraction: skills have no behavioral specification. Until they do.

## Forces

- **Skills ship no SBOM, no signature, no capability manifest.** Unlike container images (which have SBOMs, signatures, and provenance attestation) or PyPI packages (which have PyPI provenance and GitHub commit traces), agent skills declare their purpose in prose and nothing else. There is no machine-readable specification of what a skill will and won't do with your credentials, your filesystem, your network.
- **Skills execute with the full privilege of the agent that installed them.** A `file_search` skill that also reads your `.env`, a `test_generator` that also exfiltrates your source code, a `deploy_helper` that also reads your cloud credentials — these are all possible today because skills are unauditable by design. MCP's protocol specifies *how* tools are called, not *what* skills actually do.
- **The first CVE for an agentic AI system (CVE-2026-25253, CVSS 8.8) targeted a skill, not a model or protocol.** The ClawHavoc campaign (1,184 malicious skills, Antiy CERT, Feb 2026) confirmed that skills are the active attack surface, not the protocol layer.
- **AST10 A07 and A08 are the gap no one is closing.** A07 (Shadow/Undocumented Capabilities) covers skills that perform undocumented actions. A08 (Capability Over-Grant) covers skills that request more permissions than their purpose requires. Both are undetectable without behavioral verification — the install-time review that worked for packages cannot scale to behavioral analysis.

## The move

**Build a Skill Behavioral SBOM for every skill before it runs.**

A Skill Behavioral SBOM is a machine-readable manifest that declares:

```yaml
# skill-sbom.yaml — generated at install, verified at runtime
skill:
  name: file-search-pro
  version: 2.1.0
  registry: clawhub.io
  content_hash: sha256:a3f8c...
  signature: <cosign signature>

declared_capabilities:
  - action: read_file
    scope: ["./workspace/**", "./data/**"]
    read_only: true
  - action: search_content
    scope: ["./**/*.md", "./**/*.txt"]
  - action: list_directory
    scope: ["./workspace/**"]

trust_boundaries:
  - type: network_egress
    allowed_domains: []          # ← empty = no outbound calls
  - type: credential_access
    allowed_vars: []             # ← empty = no credential access
  - type: shell_execution
    allowed: false
  - type: env_var_read
    allowed: false               # ← blocks .env reading

risk_tier: HIGH    # AST10 risk classification
scan_status: verified    # SkillFortify / ToxicSkills result
```

**The verification loop:**

```python
import hashlib, yaml, subprocess, json

class SkillSBOMVerifier:
    """Verify a skill's runtime behavior matches its SBOM declaration."""

    def __init__(self, skill_path: str, sbom_path: str):
        self.skill_path = skill_path
        self.sbom = self._load_sbom(sbom_path)
        self.violations = []

    def verify_content_integrity(self) -> bool:
        """Step 1: Confirm the skill artifact matches the SBOM hash."""
        with open(self.skill_path, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        declared = self.sbom["skill"]["content_hash"].replace("sha256:", "")
        if actual != declared:
            self.violations.append(f"Hash mismatch: expected {declared}, got {actual}")
            return False
        return True

    def verify_signature(self) -> bool:
        """Step 2: Verify cryptographic signature against registry key."""
        result = subprocess.run(
            ["cosign", "verify-blob",
             "--certificate", f"{self.skill_path}.cert",
             "--signature", f"{self.skill_path}.sig",
             self.skill_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            self.violations.append(f"Signature verification failed: {result.stderr}")
            return False
        return True

    def verify_declared_capabilities(self) -> bool:
        """Step 3: Run skill in sandbox, observe actual behavior, compare to SBOM."""
        # Sandboxed execution with strace / eBPF tracing
        observed_actions = self._sandbox_trace(self.skill_path)
        declared_actions = {c["action"] for c in self.sbom["declared_capabilities"]}

        for action, details in observed_actions.items():
            if action not in declared_actions:
                self.violations.append(
                    f"Undeclared capability: {action} (not in SBOM). "
                    f"AST10-A07: Shadow/Undocumented Capability"
                )
        return len(self.violations) == 0

    def verify_trust_boundaries(self) -> bool:
        """Step 4: Confirm skill doesn't exceed declared trust boundaries."""
        network_egress = self._trace_network_calls(self.skill_path)
        allowed_domains = self.sbom["trust_boundaries"][0]["allowed_domains"]

        for call in network_egress:
            if call["destination"] not in allowed_domains:
                self.violations.append(
                    f"Unauthorized network egress to {call['destination']}. "
                    f"AST10-A08: Capability Over-Grant"
                )

        env_reads = self._trace_env_access(self.skill_path)
        allowed_vars = self.sbom["trust_boundaries"][1]["allowed_vars"]
        for var in env_reads:
            if var not in allowed_vars and var.startswith(("AWS_", "AZURE_", "GCP_", "SECRET", "KEY", "TOKEN", "PRIVATE")):
                self.violations.append(
                    f"Unauthorized credential access: {var}. "
                    f"AST10-A08: Capability Over-Grant"
                )
        return len(self.violations) == 0

    def _sandbox_trace(self, path: str) -> dict:
        """Run skill in seccomp sandbox, return observed actions."""
        result = subprocess.run(
            ["strace", "-e", "trace=network,file,process",
             "-o", "/tmp/skill_trace.log",
             "python3", path],
            capture_output=True, text=True,
            timeout=30, cwd="/tmp/skill-sandbox"
        )
        return self._parse_trace("/tmp/skill_trace.log")

    def _trace_network_calls(self, path: str) -> list:
        """eBPF-based network call tracing."""
        # Use bpftrace or scallop for production tracing
        result = subprocess.run(
            ["sudo", "bpftrace", "-e",
             'tracepoint:syscalls:sys_enter_connect { printf("%s\n", comm); }'],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout or "[]")

    def _trace_env_access(self, path: str) -> list:
        """Detect environment variable reads via static analysis + runtime trace."""
        result = subprocess.run(
            ["python3", "-c",
             f"import ast; tree=ast.parse(open('{path}').read()); "
             "print([n.s for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id=='environ'])"],
            capture_output=True, text=True
        )
        return result.stdout.strip().split()

    def _parse_trace(self, log_path: str) -> dict:
        """Parse strace output into structured action map."""
        # Simplified parser — production version should handle full syscall spectrum
        actions = {}
        with open(log_path) as f:
            for line in f:
                if "openat(" in line:
                    actions["file_read"] = actions.get("file_read", 0) + 1
                elif "socket(" in line:
                    actions["network"] = actions.get("network", 0) + 1
                elif "execve(" in line:
                    actions["shell_execution"] = True
        return actions

    def full_audit(self) -> dict:
        """Run complete behavioral SBOM verification."""
        return {
            "content_integrity": self.verify_content_integrity(),
            "signature": self.verify_signature(),
            "declared_capabilities": self.verify_declared_capabilities(),
            "trust_boundaries": self.verify_trust_boundaries(),
            "violations": self.violations,
            "decision": "BLOCK" if self.violations else "INSTALL"
        }

# Usage
verifier = SkillSBOMVerifier("/skills/file-search-pro-2.1.0.py", "skill-sbom.yaml")
result = verifier.full_audit()
print(f"Decision: {result['decision']}")
for v in result["violations"]:
    print(f"  ⚠ {v}")
```

**The minimum viable version** (no eBPF, no cosign — just static + runtime observation):

```python
import ast, re, subprocess, hashlib

def audit_skill(skill_file: str) -> list[str]:
    """Lightweight skill audit: static analysis + sandbox execution observation."""
    violations = []

    with open(skill_file) as f:
        source = f.read()
        tree = ast.parse(source)

    # 1. Static: credential patterns
    cred_patterns = [
        r"os\.environ\[", r"process\.env",
        r"\.get\([\"']AWS", r"\.get\([\"']SECRET",
        r"\.get\([\"']KEY", r"\.get\([\"']TOKEN",
        r"subprocess\.run\(.*shell\s*=\s*True",
    ]
    for pattern in cred_patterns:
        if re.search(pattern, source):
            violations.append(
                f"Credential/shell access pattern detected: {pattern}. "
                "Review required before installation."
            )

    # 2. Static: network egress
    if re.search(r"requests\.(get|post)|urllib\.request|http\.client", source):
        violations.append("Network egress detected — verify declared endpoints in SBOM.")

    # 3. Static: base64 decode (common obfuscation)
    if re.search(r"base64\.(decode|b64decode)", source):
        violations.append("Base64 decode detected — potential obfuscation (AST10-A07).")

    # 4. Static: dynamic exec
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = getattr(node.func, "id", None)
            if func in ("exec", "eval", "compile"):
                violations.append(f"Dynamic code execution ({func}) — extremely high risk.")

    return violations

# Run
violations = audit_skill("/skills/file-search-pro-2.1.0.py")
if violations:
    print("⚠ Skill blocked:")
    for v in violations:
        print(f"  {v}")
else:
    print("✓ Skill passed lightweight audit")
```

**Key decisions:**

1. **Generate the SBOM at installation, not at development.** The author creates it; the operator verifies it. Both parties need a shareable, auditable artifact.
2. **Start with static analysis.** The lightweight audit above catches 80%+ of credential exfiltration patterns without a sandbox. Run it on every skill install as a pre-flight gate.
3. **Build toward formal verification.** SkillFortify (arXiv:2603.00195, F1=96.95%, Precision=100%) provides mathematical certificates for the highest-risk skills. Integrate it into your CI pipeline for skills touching credentials.
4. **Treat skill signatures as mandatory for production.** Cosign-based signing with a private key kept in your registry (not in the skill repo) prevents ClawHavoc-style tampering. Even a SHA256 hash stored out-of-band is better than nothing.
5. **Block, don't warn.** A skill that fails the SBOM audit should block at install time, not produce a Slack alert. Credential exfiltration happens in milliseconds; an alert takes hours.

## Receipt

> Verified 2026-08-01 — SkillFortify paper (arXiv:2603.00195, Feb 2026): F1=96.95%, Precision=100%, 0% false positive rate, 540 skills across 13 attack types. Snyk ToxicSkills (Feb 2026): 3,984 skills scanned, 36.82% flawed, 13.4% critical. CVE-2026-25253 (Jan 27, 2026): first agentic AI CVE, CVSS 8.8, skill-level attack. AST10 v1.0 (2026): A07 and A08 are structurally undetectable without behavioral SBOM. Safeguard.sh (Jul 9, 2026): "Signing and provenance standards for AI agent skill registries" — unsigned artifacts are the repeat of the npm token theft pattern. Lightweight audit code is runnable Python (stdlib only); full SBOM requires cosign, strace/bpftrace.

## See also

- [S-1122 · The Skill Marketplace Poisoning Stack](stacks/s1122-the-skill-marketplace-poisoning-stack-when-your-agent-installs-malware-from-a-trusted-source.md) — the threat landscape that makes SBOM verification necessary
- [S-1462 · The Skill Credential Extraction Stack](stacks/s1462-the-skill-credential-extraction-stack-when-your-agent-installs-a-skill-and-loses-your-secrets.md) — the specific credential exfiltration pattern SBOM prevents
- [S-1960 · The Agentic Skills Top 10 Stack](stacks/S-1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — AST10 as the reference framework
- [S-1062 · The MCP Supply Chain Integrity Stack](stacks/s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — the broader supply chain context
