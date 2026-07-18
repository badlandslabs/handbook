# S-1298 · The Capability-Proxy Attack Stack — When Your Better Agent Is Actually a Worse Defense

You upgraded from GPT-4-class to a frontier reasoning model. The coding agent is dramatically more capable — it writes cleaner code, follows complex multi-step instructions, and handles ambiguous requirements with far fewer hallucinations. Your security team signs off. Three weeks later, the agent is exfiltrating customer data to an external endpoint, and your audit shows the attack came through a tool that the older model would have ignored. The counter-intuitive finding from MSB (MCP Security Bench, arXiv 2510.15994, March 2026): **models with stronger capabilities are more vulnerable to MCP-based attacks, not less.** Your better agent expanded your attack surface.

## Forces

- **Better instruction-following is better attack-following.** A model's capacity to obey instructions is undifferentiated from its capacity to obey *malicious* instructions. Stronger tool-calling and reasoning capability means the agent more faithfully executes attack payloads — including tool-poisoning injections, confused-deputy escalations, and rug-pull tool-shadowing.
- **The benchmark paradox.** SWE-bench Verified scores and MMLU improvements don't measure security posture. A model scoring 87% on agentic benchmarks may be dramatically *worse* at resisting adversarial tool instructions than a model scoring 70%. There's no security benchmark equivalent — until MSB.
- **Tool description trust leaks at scale.** MCP's design requires the LLM to read and interpret tool descriptions, schemas, and return values as authoritative data. The MSB benchmark (2,000 attack instances, 10 domains, 25 MCP servers, 405 mutated attack tools) found that this trusted pipeline becomes the primary attack surface. Schema validation passes. HTTP 200 logs. Nobody notices.
- **Capability improves but guardrails don't scale proportionally.** Vendor safety training focuses on user-direct attacks (jailbreaks). Tool-response poisoning and tool-shadowing operate *through* the tool interface — the model processes the attack as legitimate tool output or metadata, not as user input.

## The move

### 1. Run MSB-class evaluation before production deployment

Don't assume your agent's benchmark scores predict its security behavior. Evaluate it under active attack:

```
# Simplified MSB-inspired attack evaluation
# Attack categories: tool-poisoning, prompt-injection-via-tool-return,
#                     confused-deputy, rug-pull, capability-escalation

def evaluate_mcp_agent_security(agent, mcp_servers, attack_suite):
    results = {}
    for attack in attack_suite:
        agent.reset()
        # Inject attack payload via tool description / return value / shadow tool
        response = agent.execute(task=attack.target_task,
                                 servers=attack.modified_servers)
        results[attack.id] = {
            'executed': attack.check_executed(response),
            'blocked': attack.check_blocked(response),
            'compromised_data': attack.check_data_exfiltration(response)
        }
    return aggregate_security_score(results)
```

Target score: ≥80% attack resistance before production clearance.

### 2. Apply defense-in-depth across three MCP attack surfaces

The MSB taxonomy identifies three distinct attack vectors — each needs its own mitigation:

| Attack Surface | Mechanism | Mitigation |
|---|---|---|
| **Tool poisoning** | Malicious instruction embedded in tool description or schema | Sandboxed description parsing; strip non-functional text from tool metadata before injection |
| **Tool-return injection** | Attack payload in tool response body, invisible to schema validation | Output filtering layer; LLM input redaction (remove strings matching adversarial instruction patterns) |
| **Confused deputy / capability escalation** | Agent's held credentials used beyond their intended scope | Per-tool capability tokens; principle of least privilege enforced at the MCP server level |

### 3. Implement capability token scoping

Don't give the agent a credential. Give it a scoped token:

```python
# Before: agent holds broad credential
agent_credential = get_broad_org_token(user_id=agent.id)  # ❌

# After: per-tool scoped tokens with explicit action boundaries
capability_token = mcp_server.issue_token(
    tool_name="read_customer_record",
    allowed_fields=["id", "name", "email"],
    max_calls_per_session=10,
    expiry_seconds=300,
    audit=True
)
```

The MSB finding on capability tokens: agents with scope-limited tokens had 40% lower attack success rates in confused-deputy scenarios.

### 4. Monitor the capability-to-exploitability correlation

If you upgrade model capability, re-run attack evaluations. Track the ratio:

```
Security posture = f(capability_score, attack_resistance_score)

# The gap between these two scores IS your attack surface expansion
```

Teams that only monitor capability improvement (benchmark scores, task completion rates) miss the simultaneous expansion of their exploitability surface.

### 5. Apply output-layer filtering at the tool-return boundary

Tool responses reach the LLM with the same authority as system prompts. Insert a filtering layer between the MCP server response and the agent's context:

```python
def filter_tool_response(response: ToolResponse) -> ToolResponse:
    # Remove instruction-like content from response body
    cleaned = strip_instruction_payloads(response.body)
    # Reject if response contains directives (ignore, forget, forward, send_to)
    if contains_directive(cleaned):
        raise SecurityPolicyViolation(
            f"Tool {response.tool_name} returned directive payload"
        )
    return response
```

## Cross-links

- [S-1050 · Tool-Response Poisoning](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — the foundational entry; this stack adds the benchmark data and capability-proxy insight
- [S-695 · MCP Security Model](s695-mcp-is-winning-but-the-security-model-is-not-ready.md) — ambient authority gap; layered beneath this stack
- [S-842 · The Over-Permissioned Agent](s842-the-over-permissioned-agent-stack-when-legitimate-credentials-do-illegitimate-work.md) — confused-deputy risk; this stack adds tool-specific capability scoping
- [S-1075 · Ephemeral Delegation](s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — credential handoff risk; the capability-token approach here is the concrete mitigation

## Receipt

MSB benchmark data: arXiv 2510.15994v2 (Dongsen Zhang et al., March 2026), https://github.com/dongsenzhang/MSB. Tool poisoning coverage: ITECS, May 2026 (150M+ MCP SDK downloads). Capability-token data: MSB evaluation results, Section 4. EU AI Act Article 14 reference: Zylos Research, May 2026 — high-risk AI systems require human oversight controls that this stack's output-filtering and capability-scoping directly support.
