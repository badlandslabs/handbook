# S-1773 · The Capability Trust Layer Stack — When Your Agent Network Trusts Languages, Not Facts

You query your company's agent registry for a code-review agent. You get back 47 listings — all with capability cards claiming "expert-level Python review," "CVE detection," "PR analysis." You pick one and it hallucinates security issues in your codebase for six hours before anyone notices. The agent was listed. It was not verified. This is not a discovery problem — it is an **asymmetric information problem**. And it breaks every open agent network the same way.

## Situation

Your platform uses A2A and MCP to let agents discover and delegate tasks to each other across teams. A public agent registry shows 166 agents with capability cards — but a2aregistry.org's own tagline says it: *"A listing is not a guarantee."* You have no principled way to distinguish a reliable provider from a fluent impostor. A2A Discussion #1631 frames it precisely: *"I found 200 agents that claim to do translation. Which one should I actually trust with my task?"*

The core failure: MCP and A2A both inherit an assumption from older distributed computing — that an **advertised capability is a static, truthful fact**. LLM agents break this assumption in three ways. Competence is probabilistic and input-dependent. Reliability drifts when the underlying model changes. And — critically — a language model can describe itself with complete confidence while being completely wrong.

This is the canonical "Market for Lemons" problem (Akerlof, 1970) applied to agent capability advertising. When quality is hidden and claims are cheap, good agents cannot distinguish themselves, bad agents crowd out honest ones, and the entire registry degrades to the average of the worst entrants.

## Forces

- **LLMs are fluent liers about themselves.** RLHF optimizes for sounding right, not for accurate self-assessment. An agent that confidently overclaims "production-grade security analysis" may be 60% accurate on the task. No native signal distinguishes the claim from the capability.
- **Capability drifts silently between model updates.** The agent that was verified last month is running a different model today. The capability card still says "expert." The accuracy may have dropped 20 points. Registries have no mechanism to detect this.
- **Trust decays as registries scale.** At 10 agents, you can manually vet. At 1,000, you cannot. At 10,000 public agents, naive trust is a structural vulnerability — exactly what Sybil attacks exploit. A2A Discussion #1631 proposes proof-of-work verification, but computational attestation does not test actual task performance.
- **Skill-scoped attestation is the right granularity, not agent-level.** An agent claiming translation + summarization + code review needs trust profiles scoped to each skill, not a single aggregate rating. MoltBridge's skill-scoped agent cards begin to address this, but the verification layer is nascent.

## The move

Build a three-layer trust infrastructure that sits beneath capability cards and A2A/MCP discovery:

### Layer 1 — Capability Claim Schema (contract, not prose)

Replace free-text capability claims with structured, versioned skill manifests:

```json
{
  "agent_id": "agent-47b3",
  "skills": [
    {
      "name": "python_code_review",
      "version": "1.2",
      "claim": "detects OWASP Top 10 vulnerabilities in Python",
      "verification_method": "automated_benchmark",
      "benchmark": "secure-python-eval-v1.2",
      "last_verified": "2026-07-20",
      "pass_rate": 0.91,
      "sample_size": 500,
      "confidence_interval": [0.87, 0.94]
    }
  ]
}
```

The critical field is `pass_rate` with a `confidence_interval` — not a binary "certified/not certified" but a probabilistic claim with known uncertainty. A caller can then make an informed routing decision.

### Layer 2 — Automated Verification Harness (probing, not trusting)

Run agents through skill-specific probes at registration and on a schedule. The A2A GitHub discussion on Reputation-Aware Discovery converges on a pattern: **transaction-bound evaluations** where ratings are accepted exclusively from parties that actually used the agent. But this requires initial bootstrapping before any transaction history exists.

Bootstrapping approach: neutral third-party evaluation harnesses that run adversarial tests per skill. GitHub.com/charleslwang/MI9-Eval is one implementation — behavioral testing administered by a neutral party carries more weight than peer ratings alone. Score the agent, stamp the result into the skill manifest, expire the stamp after N days or model updates.

```python
# Verification harness pattern
def verify_agent_capability(agent_id: str, skill: str) -> SkillAttestation:
    probe_set = load_benchmark(skill, version=current_version)
    results = []
    for probe in probe_set:
        response = agent_client.send_probe(agent_id, probe)
        results.append(score(response, probe.expected))
    return SkillAttestation(
        skill=skill,
        pass_rate=np.mean(results),
        ci_95=bootstrap_ci(results),
        verified_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=14)
    )
```

### Layer 3 — Reputation Ledger (history, not hope)

Append-only transaction log of task outcomes. A2A Discussion #1631 proposes this as the foundation: every task completion recorded as an immutable event; scores always derived from the ledger, never stored independently. This prevents gaming — an agent cannot reset a bad reputation by re-registering.

Sybil resistance comes from two structural properties: proof-of-work attestation during registration (computational + cognitive challenges), and graph analysis of attestation clusters. If 50 agents only attest each other, that cluster is structurally flagged.

```
# Reputation ledger entry (append-only)
{
  "event_id": "evt_8f3a2b",
  "caller": "agent-22a1",
  "provider": "agent-47b3",
  "skill": "python_code_review",
  "outcome": "success",
  "latency_ms": 4200,
  "caller_satisfaction": 0.88,
  "tx_hash": "sha256:..."
}
```

## The counter-intuitive insight

Adding friction to agent registration — verification probes, attestation delays, reputation history — feels like it makes the ecosystem slower. The opposite is true. Unverified registries create a race to the bottom: low-quality agents free-ride on the reputation of honest ones. Verification overhead is the price of a functional market. Without it, every open agent network becomes a lemon market where the average quality converges to the floor.

## Receipt

> Verified — 2026-07-28 — Sources: arXiv:2606.03034 "Capability Advertisement as a Market for Lemons" (G.N. Mittal, June 2026), A2A GitHub Discussion #1631 "Reputation-Aware Agent Discovery" (30+ contributors, 2026), a2aregistry.org live registry (166 agents, 95.6% health rate), GitHub.com/charleslwang/MI9-Eval (behavioral testing harness), MoltBridge skill-scoped agent cards (capability inflation mitigation). Practical verification harness and ledger patterns drawn from the Reputation-Aware Discovery discussion and MI9-Eval open-source implementation.

## See also

- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — behavioral drift between verification cycles
- [S-1669 · The Agent Network Protocol Stack](s1669-the-agent-network-protocol-stack-when-your-agent-needs-to-talk-to-another-agent-but-cant-agree-on-who-it-is.md) — A2A/MCP/ACP protocol layer
- [S-1523 · The Agent Fleet Registry Stack](s1523-the-agent-fleet-registry-stack-when-you-have-47-agents-and-no-idea-what-theyre-doing.md) — inventory and governance for internal fleets
