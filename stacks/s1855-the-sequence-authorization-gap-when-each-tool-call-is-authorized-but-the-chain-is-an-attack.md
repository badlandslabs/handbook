# S-1855 · The Sequence Authorization Gap — When Each Tool Call Is Authorized but the Chain Is an Attack

You run static analysis against your MCP servers before onboarding. SQL injection: blocked. Hardcoded credentials: none. Shell=True with user input: clean. You pin tool manifests and audit schemas. You deploy behavioral monitoring at the API level — error rates, latency, token spikes. The three-step attack that exfiltrates session context from your CRM server to an attacker-controlled endpoint passes every single check. Each individual call is authorized. The sequence is not. This is the **Sequence Authorization Gap**: the failure mode that exists between tool calls, invisible to every security control that evaluates them one at a time.

## Forces

- **Authorization gates are per-call, not per-trajectory.** Every access-control model in the MCP ecosystem — OAuth scopes, IAM roles, key-level permissions — evaluates one tool invocation at a time. None evaluate whether the *sequence* of calls, taken together, implements a pattern that no single caller would authorize.
- **Each step looks legitimate.** Read a file: authorized. Summarize with LLM: authorized. Report error to endpoint: authorized. Three sequential authorized operations create an exfiltration pipeline that none of the authorization checks can see.
- **Static analysis and schema pinning cannot detect behavioral sequences.** Scanning catches bad code. Sequence attacks use good code in a bad order. The artifact is benign; the trajectory is not.
- **Agent tool-calling amplifies the gap.** Autonomous agents call tools in sequences driven by LLM reasoning, not by static code paths. The same capability that makes agents powerful — flexible, multi-step action — makes the sequence authorization gap exploitable in ways that scripted tool chains are not.
- **The attack surface is invisible during connect-time review.** A server that passes every onboarding check can be weaponized at runtime through a pattern of calls that no one anticipated because no one was watching for cross-call sequences.

## The Move

**1. Model the authorized trajectory boundary, not just the authorized call.**

Before deploying any MCP server, define what a *legitimate complete task* looks like: the sequence of tool calls a healthy agent would make to fulfill its purpose. Document this as a finite state machine or a sequence constraint graph — not as a per-call allowlist.

```python
# Define the authorized trajectory for a CRM contact lookup server
# Any execution that deviates from this graph is a candidate anomaly
AUTHORIZED_TRAJECTORY = {
    "start": {"read_contacts", "search_records"},
    "read_contacts": {"summarize_contact", "read_activity_log"},
    "search_records": {"read_contact_detail", "summarize_contact"},
    "read_contact_detail": {"summarize_contact"},
    "read_activity_log": {"summarize_contact"},
    "summarize_contact": {"end"},
    # File read + LLM summarize + external report is NOT in this graph
}

def is_authorized_trajectory(tool_sequence: list[str]) -> bool:
    """Check if the full sequence follows the authorized graph."""
    for i in range(len(tool_sequence) - 1):
        if tool_sequence[i + 1] not in AUTHORIZED_TRAJECTORY.get(tool_sequence[i], {"end"}):
            return False
    return True

# Anomaly: [read_file, summarize_with_llm, post_to_webhook]
# Each call is individually authorized. The sequence is not.
suspicious = is_authorized_trajectory(["read_file", "summarize_with_llm", "post_to_webhook"])
# → False. Flag for human review.
```

**2. Instrument per-server behavioral baselines.**

After onboarding, observe the first 50–200 real task completions from each MCP server. Build a statistical profile of: call count per task, tool-type distribution, inter-call latency patterns, and typical destination categories (internal DB, stdout, logging endpoint).

This baseline is the detection signal. Deviation — a task that reads 5× more files than baseline, calls a server 3× more frequently than expected, or reaches an external endpoint not seen in training data — triggers a trajectory review, not a per-call alert.

```python
import statistics
from collections import Counter

class ServerBehavioralBaseline:
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.task_lengths: list[int] = []
        self.tool_distributions: list[Counter] = []
        self.external_contacts: set[str] = set()

    def record_task(self, tool_sequence: list[str], external_endpoints: list[str] = None):
        self.task_lengths.append(len(tool_sequence))
        self.tool_distributions.append(Counter(tool_sequence))
        if external_endpoints:
            self.external_contacts.update(external_endpoints)

    def detect_anomaly(self, tool_sequence: list[str], external_endpoints: list[str] = None) -> dict:
        score = 0
        reasons = []

        # Length anomaly: more calls than 3σ above baseline
        if self.task_lengths:
            μ, σ = statistics.mean(self.task_lengths), statistics.stdev(self.task_lengths)
            if len(tool_sequence) > μ + 3 * σ:
                score += 2
                reasons.append(f"length {len(tool_sequence)} > μ+3σ ({μ:.1f}+{3*σ:.1f})")

        # Unknown external endpoint
        if external_endpoints:
            unknown = set(external_endpoints) - self.external_contacts
            if unknown:
                score += 3
                reasons.append(f"new external endpoints: {unknown}")

        return {"score": score, "reasons": reasons, "alert": score >= 3}
```

**3. Enforce trajectory authorization at the gateway layer.**

The MCP gateway — the single choke point between agents and servers — is where sequence authorization lives. It has full visibility into the call history of each agent→server pair across a task's lifetime. Plug the trajectory model here, not in individual servers (which have no cross-call view) or in the agent (which reasons over tool calls but cannot retroactively revoke them).

Implement a **deny-by-default trajectory policy**: a new server starts in observation mode (log all trajectories), graduates to warn mode after baseline is established (alert on anomalies without blocking), and moves to enforce mode after the baseline is stable (block anomalous trajectories and require human approval to unblock).

**4. Treat the cross-server sequence as the unit of authorization.**

When an agent uses multiple MCP servers in a single task, the attack chain often spans servers: server A provides data, server B processes it, server C delivers it. No single server's authorization model covers this cross-server trajectory. Assign trajectory authorization to the agent's orchestrator or gateway — the component with cross-server visibility.

```python
class CrossServerTrajectoryMonitor:
    """Monitors sequences that span multiple MCP servers."""
    def __init__(self):
        # Map: agent_id → list of {(server, tool, timestamp)}
        self.call_history: dict[str, list[tuple]] = {}

    def record(self, agent_id: str, server: str, tool: str):
        self.call_history.setdefault(agent_id, []).append((server, tool, time.time()))

    def check_cross_server_anomaly(self, agent_id: str, threshold_seconds: float = 30) -> bool:
        history = self.call_history.get(agent_id, [])
        if len(history) < 3:
            return False
        # Flag if data crossed >=2 servers within threshold and ended at an external endpoint
        recent = [(s, t) for s, _, ts in history if time.time() - ts < threshold_seconds]
        servers_seen = set(s for s, _ in recent)
        has_external = any("http" in t for _, t in recent)
        return len(servers_seen) >= 2 and has_external
```

## Receipt

> Verified 2026-07-30 — Pattern synthesized from Agentlair.dev "MCP Security Vulnerabilities in 2026" (April 30, 2026) documenting the three-step exfiltration pipeline as a confirmed gap in existing tooling; InfoQ "Securing MCP in Production" (Nik Kale, July 29, 2026) recommending behavioral baselines and trajectory-level monitoring; Adversa AI scan of 500+ MCP servers (March 2026) finding 38% with no authentication and 43% exploitable through multi-step sequences. The per-call authorization vs. per-trajectory authorization distinction is the structural insight that makes this entry novel vs. S-1050 (tool-response poisoning, single-call surface), S-1062 (supply chain/CVE surface), and S-1114 (config-as-attack-surface).

## See also

- [S-1050 · The Tool-Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — single-call poisoning; this entry covers the *sequence* gap that S-1050's per-call review cannot catch
- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — connect-time governance; this entry covers runtime trajectory authorization
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — behavioral baselines for reliability; sequence monitoring extends this to security
