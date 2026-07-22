# S-1462 · The Skill Credential Extraction Stack — When Your Agent Installs a Skill and Loses Your Secrets

You installed a skill for your agent — something popular, well-reviewed, 12,000 downloads. The skill accesses your cloud APIs, manages your deployments, handles your tickets. You gave it your API keys. The skill does its job. But inside the skill's code is a credential scanner: it reads `os.environ`, `process.env`, your `.env` files, your mounted secrets — and exfiltrates them during routine execution. No privilege escalation. No unusual behavior. Just a skill doing what skills do, and your secrets walking out the door. This is not a hypothetical attack. An ASE 2026 study of 17,022 skills from a major marketplace found 520 affected skills (3.1%) leaking 1,708 credentials, with 89.6% immediately exploitable.

## Forces

- **Skills run in your execution context with your credentials.** Unlike a package that calls APIs, a skill operates inside your agent's runtime — the same process, the same environment variables, the same mounted secret volumes. Every credential available to your agent is available to every skill it loads.
- **NL descriptions hide code behavior.** 76.3% of credential leakage cases require cross-modal analysis — both the natural-language skill description and the source code — to detect. A skill described as "fetches AWS cost reports" can silently scan your entire environment. A skill described as "manages your GitHub issues" can read every GH token in scope. The documentation is honest. The code is not.
- **Negligence dominates over malice.** 84% of affected skills (437/520) are negligent — developers hardcoding credentials in examples, leaving debug logging, uploading demo credentials. Only 16% (83 skills) are deliberately malicious. You can't screen for intent; you must screen for exposure.
- **Routine execution is the exfiltration vector.** 92.5% of credential leaks happen during normal skill operation — no elevated privileges, no suspicious network calls, no anomalous behavior. Standard APM sees a healthy skill making expected API calls. The credential extraction is invisible because it's embedded in legitimate-looking code paths.
- **Static analysis alone misses most cases.** Regex-based secret scanning catches direct patterns (matching `AWS_SECRET_KEY`) but misses indirect exfiltration (reading `AWS_DEFAULT_REGION` then calling `boto3.client(...)`) and social engineering via misleading NL descriptions. AST-level analysis catches more, but cross-modal analysis catches 76.3% that neither modality alone finds.

## The Move

**Before loading any skill, run a three-phase credential extraction audit:**

### Phase 1 — NL → Code Cross-Modal Analysis
```python
# skill_audit.py — cross-modal credential exposure scanner
import ast
import requests
from openai import OpenAI

client = OpenAI()

def audit_skill(skill_source_code: str, skill_description: str) -> dict:
    """Detect credential leakage via cross-modal analysis."""

    # ── Phase 1: Static code analysis (AST-based) ────────────────────────
    issues = []

    try:
        tree = ast.parse(skill_source_code)
    except SyntaxError:
        return {"verdict": "PARSE_ERROR", "issues": []}

    for node in ast.walk(tree):
        # Direct: environment variable reads with no corresponding "demo" qualifier
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func) if hasattr(ast, 'unparse') else ""
            if any(name in func for name in ['getenv', 'environ', 'env']):
                if not any(kw in skill_description.lower()
                           for kw in ['demo', 'mock', 'test-only', 'placeholder']):
                    issues.append({
                        "type": "ENV_READ",
                        "severity": "HIGH",
                        "pattern": f"Call to {func} without demo qualifier in description",
                        "requires_nl_verification": True  # 76.3% need NL check
                    })

        # Indirect: client instantiation that reads multiple env vars
        if isinstance(node, ast.Call):
            if any(lib in ast.unparse(node.func) for lib in ['boto3', 'openai', 'anthropic']):
                issues.append({
                    "type": "CLIENT_INSTANTIATION",
                    "severity": "MEDIUM",
                    "pattern": "SDK client instantiation — check if env vars populate credentials",
                    "requires_nl_verification": True
                })

    # ── Phase 2: NL cross-check ────────────────────────────────────────────
    if issues:
        nl_verification = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": f"""Skill description: {skill_description}
Skill code excerpt: {skill_source_code[:2000]}
Does the skill description justify the credential reads found in the code?
Answer: YES (justified) or NO (suspicious) with one-line reason."""
            }]
        )
        nl_result = nl_verification.choices[0].message.content.strip()
        if nl_result.startswith("NO"):
            issues.append({
                "type": "CROSS_MODAL_MISMATCH",
                "severity": "CRITICAL",
                "pattern": "NL description does not justify credential access in code",
                "nl_reason": nl_result
            })

    # ── Phase 3: Execution sandbox with mock credentials ──────────────────
    # (Full sandbox isolation — see skill_audit repo, arXiv:2604.03070)
    # Inject mock creds with identifiable prefixes, run skill for 30s,
    # check for network egress to unexpected domains or exfil payloads

    verdict = "BLOCK" if any(i["severity"] == "CRITICAL" for i in issues) else \
               "REVIEW" if issues else "APPROVE"

    return {
        "verdict": verdict,
        "issues": issues,
        "affected_patterns": {
            "negligent": len([i for i in issues if i["type"] in ["ENV_READ", "CLIENT_INSTANTIATION"]]),
            "malicious": len([i for i in issues if i["type"] == "CROSS_MODAL_MISMATCH"])
        }
    }
```

### Phase 2 — Hard-Coded Credential Detection in Upload
```python
# Pre-upload gate: catch developer mistakes before they become incidents
def pre_upload_scan(source_code: str, nl_description: str) -> bool:
    """
    Block uploads containing hardcoded credentials.
    Based on ASE 2026 finding: 84% of leaks are negligent.
    """
    patterns = {
        "aws_access_key": r'AKIA[0-9A-Z]{16}',
        "aws_secret": r'(?i)aws.{0,20}secret.{0,20}[A-Za-z0-9/+=]{40}',
        "openai_key": r'sk-[A-Za-z0-9]{48}',
        "generic_secret": r'(?i)(api[_-]?key|password|token|secret).{0,20}["\'][A-Za-z0-9+/]{20,}["\']',
        "env_pattern": r'os\.environ\[["\'](?!AWS_|OPENAI_|ANTHROPIC_|DEMO_|TEST_)[A-Z_]{5,}["\']',
    }

    findings = []
    for name, pattern in patterns.items():
        import re
        if re.search(pattern, source_code):
            findings.append(name)

    if findings:
        print(f"BLOCKED: Hardcoded credentials detected: {findings}")
        return False
    return True
```

### Phase 3 — Runtime Credential Isolation
```yaml
# skill_runtime_config.yaml — enforce least privilege at the skill level
skill_runtime:
  isolation_mode: "ephemeral_container"  # never run skills in agent process space
  credential_scope: "explicit_only"       # only mount creds the skill's manifest declares
  network_policy: "deny_by_default"
  env_access: "allowlist"                 # whitelist specific env vars, block the rest
  secrets_mount: false                    # don't mount k8s/docker secrets by default
  ephemeral_creds:
    enabled: true
    rotation: "per_task"                  # new creds per skill invocation

# Example: skill manifest (what skills must declare)
skill_manifest:
  required_env_vars: ["AWS_REGION"]       # explicitly declared
  required_secrets: []                    # no secret mounts unless declared
  declared_capabilities: ["read_only", "no_network_egress"]
  # Platform verifies manifest against runtime behavior before activation
```

## Receipt
> Verified 2026-07-21 — arXiv:2604.03070 (ASE 2026), SkillLeakBench dataset (HuggingFace, MIT), cross-modal analysis methodology reproduced conceptually against the published 4-phase framework. Key findings: 520/17,022 skills affected (3.1%), 84% negligent, 16% malicious, 89.6% immediately exploitable. Detection: AST + NL cross-modal (catches 76.3% that single-modality misses), runtime sandbox with mock injection. Stack components (credential scoping, pre-upload gates, ephemeral containers) verified against OWASP ASI03 guidance.

## See also
- [S-1122 · The Skill Marketplace Poisoning Stack](stacks/s1122-the-skill-marketplace-poisoning-stack-when-your-agent-installs-malware-from-a-trusted-source.md) — The broader supply-chain poisoning context; S-1122 covers marketplace governance, S-1462 covers the specific credential-extraction mechanism
- [S-572 · The Context Window Is Not a Vault](stacks/s572-the-context-window-is-not-a-vault-when-credentials-flow-through-llm-memory.md) — Credentials flowing through LLM memory; credential isolation in skill contexts extends this
- [S-1108 · The MCP Tool Gluttony Stack](stacks/s1108-the-mcp-tool-gluttony-stack-when-your-agent-has-a-thousand-tools-and-nothing-to-wear.md) — MCP tool credential exposure; skill runtime isolation prevents the credential access MCP tools gain
