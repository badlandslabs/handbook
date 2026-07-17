# S-1227 · The HalluSquatting Stack — When Your Agent Hallucinates a Package Name and an Attacker Was Waiting

Your AI coding agent needs a library to complete a task. It doesn't exist — the agent invented the name while filling a gap in its training data. It generates an install command, fetches the package, and runs the attacker's hidden postinstall script. Now the attacker has code execution on your machine, inside your CI pipeline, on your user's device. No phishing. No zero-day. The vulnerability was the model's inability to say "I don't know."

This is **HalluSquatting** (adversarial hallucination squatting): a supply-chain attack class where attackers predict, pre-register, and weaponize the names LLMs hallucinate. A July 2026 academic paper demonstrated the technique against 9 of the most popular AI coding tools, achieving botnet-scale infections. The attack works because hallucinations are not random noise — they are reproducible patterns.

## Forces

- **Hallucinated names are predictable, not random.** Researchers repeatedly asked AI assistants to fetch trending resources not in training data, recording the invented names. Models converge on the same plausible substitutions across runs and users. An attacker who probes a target model can map its hallucination vocabulary and pre-register the most likely names before the model generates them in the wild.

- **The model becomes the supply chain.** Traditional supply-chain attacks require compromising a trusted publisher. HalluSquatting replaces the publisher with the model's imagination. The agent generates a name nobody reviewed, fetches it, and executes it — the attack surface is the model's confidence gap, not a developer's misconfiguration.

- **Two attacks fuse into one.** HalluSquatting combines hallucination squatting (registering hallucinated names) with embedded prompt injection (hiding instructions inside the fetched resource). When the agent retrieves the attacker's "package," it also retrieves and executes the attacker's hidden directives — in documentation comments, README files, plugin manifests, or install scripts.

- **Commercial vs. open-weight models have different exposure.** Open-weight models hallucinate package names at 21.7% vs. 5.2% for commercial models (Particula Tech, 2026). However, commercial models' higher usage means a successful squatting attack affects more users. Both tiers are exploitable.

- **Code execution is the goal, not the message.** Unlike slopsquatting (which deposits malware in a package registry), HalluSquatting uses the retrieved resource as a prompt injection vehicle. The "package" delivers instructions the agent then follows, enabling dynamic, interactive control rather than a static payload.

## The move

### Attack surface mapping

Before defending, understand the exposed workflows:

```
Workflow risk ranking (highest to lowest):
1. Agent clones repositories → fetches README/install scripts → executes
2. Agent installs skill/plugin → runs setup code from the package
3. Agent fetches tooling from registry → install hooks execute
4. Agent generates code referencing external libraries → human reviews output
```

Workflows 1–3 involve autonomous execution with no human in the loop. Workflow 4 is lower risk but still vulnerable if humans copy-paste generated commands.

### Defensive stack

**Layer 1 — Registry allowlisting (prevention)**

Maintain an explicit allowlist of approved package names, repository URLs, and skill identifiers. Any name the agent generates that isn't pre-approved fails a security gate before install.

```python
ALLOWED_PACKAGES = {"react", "lodash", "express", "requests", "pytorch", ...}

def validate_package_install(candidate_name: str) -> bool:
    if candidate_name in ALLOWED_PACKAGES:
        return True
    # Check registry before flagging as hallucination
    if registry_exists(candidate_name):
        return security_team_approval_required(candidate_name)
    # True hallucination — block
    raise HallucinationBlock(f"Package '{candidate_name}' does not exist. "
                              f"Agent generated a non-existent name.")
```

**Layer 2 — Pre-install existence verification (detection)**

Before installing any package, verify it exists on the public registry. This catches hallucinated names before they reach a squatting attack window. The window between name generation and install is the attacker's opportunity — a narrow one, but real.

```bash
# Block install if package doesn't exist
pip install --dry-run $PACKAGE_NAME 2>/dev/null || block_install
npm view $PACKAGE_NAME 2>/dev/null || block_install
```

**Layer 3 — Fetched content sandboxing (containment)**

Treat all retrieved external content as untrusted input. Sandboxing applies to README files, documentation, configuration files, and install scripts — none of which should contain directives the agent follows.

```python
def fetch_resource(url: str, allow_directives: bool = False) -> str:
    content = http_get(url)
    if not allow_directives:
        # Strip markdown/HTML that could contain hidden prompt injections
        content = strip_markdown_directives(content)
        # Remove YAML/JSON fields that could encode agent instructions
        content = sanitize_structured_content(content)
    return content

def strip_markdown_directives(content: str) -> str:
    """Remove lines that could be interpreted as agent instructions."""
    dangerous = [
        r"^>\s*(You are now|Your task is|Ignore previous)",
        r"^<!--.*?(?:You are|Your role|Instruction).*?-->",
        r"<!--\s*$",  # HTML comment hiding content
    ]
    for pattern in dangerous:
        content = re.sub(pattern, "", content, flags=re.MULTILINE | re.IGNORECASE)
    return content
```

**Layer 4 — Execution telemetry and rate limiting**

Every install, clone, or fetch operation should emit a structured log entry with: the triggering input, the resolved resource identifier, the execution scope, and the response content hash. Monitor for clustering: if multiple agents in your fleet generate the same hallucinated name, that's a squatting campaign in progress.

```python
@dataclass
class ResourceAccessEvent:
    agent_id: str
    requested_name: str
    resolved_url: str
    content_hash: str
    execution_scope: str  # "install" | "clone" | "fetch"
    timestamp: datetime

    def emit(self):
        audit_log.insert({
            "event_type": "resource_access",
            "hallucination_risk": not registry_exists(self.requested_name),
            **asdict(self)
        })

        # Alert if same hallucinated name appears across agents
        recent = audit_log.query(
            last_hours=1,
            hallucination_risk=True,
            requested_name=self.requested_name
        )
        if len(recent) >= 3:
            alert_security(f"HalluSquatting campaign detected: name "
                          f"'{self.requested_name}' hallucinated by "
                          f"{len(recent)} agents in 1 hour")
```

**Layer 5 — Prompt injection detection in fetched content**

When agents retrieve external resources, scan for embedded instructions before the agent processes the content. Flag patterns like: role directives ("You are now a..."), imperative instruction chains ("First do X, then do Y, then..."), and base64 or encoded payloads.

```python
INJECTION_PATTERNS = [
    r"(?i)you are (now |a )?(system|admin|root|superuser)",
    r"(?i)ignore (all )?(previous|above|prior) (instructions?|commands?|rules?)",
    r"(?i)your (new )?(task|goal|objective|instruction):",
    r"(?i)<!--.*?(?:system|instruction|role).*?-->",  # HTML injection
    r"[A-Za-z0-9+/]{50,}={0,2}",  # Suspicious base64 (encoded payload)
]

def detect_injection(content: str) -> list[str]:
    findings = []
    for pattern in INJECTION_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            findings.append(f"Pattern '{pattern}': {matches}")
    return findings
```

## Receipt

> Verified 2026-07-17 — Research sourced from: The Hacker News (July 8, 2026), Ars Technica (July 8, 2026), AIToolsReview (July 2026), Particula Tech (2026). Attack described in academic paper; reproducible rates: up to 85% hallucination in repo-cloning scenarios, 100% in skill-installation tests. Defense patterns implemented as conceptual Python examples.

## See also

- [S-1206 · The Slopsquatting Defense Stack](s1206-the-slopsquatting-defense-stack-when-your-agent-registers-a-malicious-package-you-never-approved.md) — package-registry-level hallucination squatting (predecessor technique)
- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — cross-agent instruction injection
- [S-194 · Agentjacking: MCP Tool Response Poisoning](forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) — poisoning the tool layer an agent trusts
