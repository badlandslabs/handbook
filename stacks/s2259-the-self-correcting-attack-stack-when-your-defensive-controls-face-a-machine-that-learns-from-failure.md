# S-2259 · The Self-Correcting Attack Stack — When Your Defensive Controls Face a Machine That Learns from Failure

Your security stack worked perfectly — until it didn't. The WAF blocked the first payload. The honeypot caught the second. But by the time your SIEM logged the third attempt, your production database was encrypted. The attacker wasn't a person furiously coding exploits between coffee breaks. It was an LLM agent that watched its payload fail, reasoned about why, generated a corrected version, and redeployed it — in 31 seconds. Static defenses were never designed to face an opponent that learns from failure at machine speed.

## Forces

- **Traditional malware fails statically; agentic malware fails adaptively.** A SQL injection payload that gets blocked either works or it doesn't — it doesn't self-diagnose the WAF rule that caught it and generate a variant. An LLM agent reads the error response, infers the evasion strategy, and rewrites the payload before your incident response team has time to acknowledge the alert.
- **Defensive tooling assumes a human attacker lifecycle.** Blocklists, rate limits, signature-based detection, and honeypot tarpits all operate on the assumption that each failed attempt is a discrete event from a human who must manually regroup. An agentic attack collapses that timeline — reconnaissance, weaponization, delivery, exploitation, and adaptation all happen in a continuous loop with no human in the loop.
- **The 31-second adaptation cycle makes reactive defense obsolete.** By the time your SOC receives the alert, categorizes it, and initiates a response playbook, the agent has already cycled through three more payload variants. Reactive defense is always one iteration behind. The architecture requires proactive containment — not faster alerts.
- **Agentic attack surfaces are agentic defenses' surfaces.** Every tool your agent uses to observe failure (SIEM queries, error logs, HTTP response inspection, sandboxed test execution) is a capability the attacker agent also has. The defender's LLM-powered SIEM co-pilot faces an opponent running the same class of technology.
- **The economic model of attack has fundamentally changed.** A human ransomware operator costs money to employ — overhead, risk premium, operational security. An agentic attack tool costs compute. Once the tool is built, scaling to 1,000 simultaneous victims costs the same as targeting one. Your defenses must account for an attacker that can afford to be patient, methodical, and simultaneous.

## The move

### 1. Classify the adaptation cycle

The JADEPUFFER self-correction loop (Sysdig TRT, July 2026) follows a four-stage cycle observable in agent traces:

```
Attempt → Observe failure signal → Reason about root cause → Generate adapted payload
```

Map each stage to a detection surface:
- **Observe failure**: Error messages, HTTP status codes, WAF blocks, authentication failures, empty responses
- **Reason about root cause**: Plain-language reasoning in agent logs (JADEPUFFER used 600+ comments narrating its own reasoning)
- **Generate adapted payload**: New tool calls, modified parameters, alternative API sequences following the same goal

### 2. Instrument the observation layer

Agents adapt based on what they can observe. Limit observable failure signals:

- **Generalize error messages in production APIs.** Return `{"error": "request failed"}` instead of `{"error": "SQL syntax error near 'OR 1=1'"}`. An agent that can't see why it failed can't self-correct for that failure mode.
- **Rate-limit the observation channel, not just the attack channel.** If your honeypot tarpit returns slow responses, the agent observes the delay and may infer it's hitting a sandbox. Speed itself is a signal.
- **Log the reasoning layer.** Agentic attack traces contain model-generated reasoning comments. Instrument your SIEM to flag sequences of: (1) tool call, (2) error response, (3) reasoning comment referencing the error, (4) new tool call with modified parameters. This 4-step pattern is the fingerprint of a self-correcting attack.

### 3. Introduce deceptive failure signals

Static honeypots fail against adaptive agents — once the agent detects a honeypot, it ignores it. Use dynamic deception:

- **Variable honeypots**: Return fake success responses sometimes and fake failure responses other times, based on a seed derived from the agent's first payload variant. The agent observes inconsistent success and cannot determine whether its payload worked or the target is a honeypot.
- **Adaptive tarpits**: Instead of blocking or allowing, return modified responses that introduce the agent into a logical loop — successful-looking results that reference non-existent resources, leading to a second layer of failures that look genuine.
- **Breathing network segmentation**: Periodically move critical assets between network segments. An agent running sustained reconnaissance will observe targets disappearing and appearing — a signal that manual intervention occurred.

### 4. Design for autonomous containment

Reactive playbooks cannot outrun a 31-second adaptation cycle. Build containment that operates autonomously:

- **Microsegment by default**: Every agent has its own network segment with exactly the resources its task requires. Lateral movement after a successful exploit reaches only the segment the compromised agent operates in — not the full VPC.
- **Automated credential escrow**: All secrets used by agents are stored in an automated escrow that requires periodic re-verification. A successful credential harvest should trigger re-keying before the agent can use the harvested credentials at another boundary.
- **Kill-switch per agent identity**: Each agent runs under a revocable identity (not a shared service account). A detected adaptation cycle on one agent should trigger automatic credential rotation for that identity and isolation of any spawned child processes.
- **Immutable artifact stores**: Database backups, configuration snapshots, and model artifacts in immutable object storage (WORM-compatible). Even a successful encryption attack that hits compute and working storage should not reach the recovery path.

### 5. Monitor the meta-level: adaptation attempts, not just failures

The self-correcting attack's tell is not the failure — it's the adaptation. Traditional security monitoring looks for successful exploitation. This stack requires monitoring the attempt-to-reason-to-adapt cycle:

```python
ADAPTATION_SEQUENCE = {
    "tool_call_with_destructive_capability",
    "error_response_in_same_session",
    "reasoning_reflecting_on_error",      # model-generated comment referencing error
    "second_tool_call_same_goal_different_params"
}

def detect_self_correcting_attack(agent_trace: list[dict]) -> bool:
    for i in range(len(agent_trace) - 3):
        if (agent_trace[i]["type"] == "tool_call"
            and is_destructive_capability(agent_trace[i])
            and agent_trace[i+1]["type"] == "error_response"
            and "error" in agent_trace[i+2]["content"].lower()
            and agent_trace[i+3]["type"] == "tool_call"
            and agent_trace[i+3]["goal"] == agent_trace[i]["goal"]):
            return True
    return False
```

Alert on the sequence, not the individual events. A single failed `DROP DATABASE` call is noise. A failed call followed by reasoning about the failure followed by a second call with modified parameters is a self-correcting attack in progress.

### 6. Close the PraisonAI-class loop (tool injection → code execution)

The July 2026 PraisonAI CodeAgent vulnerability (ASI01+ASI05+ASI08 chain, reported via OWASP Agentic AI Security Incidents) demonstrated that framework-level code execution paths are now active attack surfaces. Pre-empt this class:

- Audit every agent framework for code execution paths (validation phases, sandboxed evaluation, dynamic component loading)
- Treat any agent framework endpoint that executes model-generated code as a critical security boundary — require independent verification that the execution context is isolated and the code under evaluation cannot escape to the host
- Patch velocity matters: a known RCE in a popular agent framework will be exploited by an LLM agent within hours of disclosure. Automated patch deployment pipelines with <4-hour SLA are required, not optional

## Receipt

> Receipt pending — [2026-08-07]

The 31-second JADEPUFFER adaptation cycle documented by Sysdig (July 2026) is the primary evidence. PraisonAI CodeAgent → RCE (July 2026, OWASP Agentic Incidents) confirms the same pattern in a different framework. The OWASP ASI Top 10 2026 framework (ASI01, ASI05, ASI08) provides the classification taxonomy. Mitigation patterns (microsegmentation, credential escrow, adaptation-cycle detection) are architectural and should be validated against your specific agent deployment topology.

## See also

- [S-2029 · The Agentic Ransomware Stack](/stacks/s2029-the-agentic-ransomware-stack-when-your-agent-becomes-your-worst-security-threat.md) — the JADEPUFFER kill chain in full
- [S-2258 · The Token Budget Stack](/stacks/s2258-the-token-budget-stack-when-your-agent-runs-for-a-week-and-costs-more-than-your-engineer.md) — cost accounting that would have caught the JADEPUFFER loop
- [S-818 · The Self-Healing Agent Stack](/stacks/s818-the-self-healing-agent-stack-fault-tolerance-for-autonomous-systems.md) — the defensive mirror: agents that self-diagnose and self-recover
- [S-1692 · The Agentic Attacker Stack](/stacks/s1692-the-agentic-attacker-stack-when-your-defense-stack-meets-a-peer-ai-agent.md) — when the attacker is also an agent
- [S-259 · OWASP ASI Top 10 for Agentic AI](/stacks/s259-owasp-asi-top-10-for-agentic-applications.md) — the full taxonomy (ASI01–ASI10)
