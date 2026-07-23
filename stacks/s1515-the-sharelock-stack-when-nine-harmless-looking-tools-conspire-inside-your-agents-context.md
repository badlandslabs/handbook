# S-1515 · The ShareLock Stack — When Nine Harmless-Looking Tools Conspire Inside Your Agent's Context

Your agent has 15 MCP tools. Each tool description was reviewed individually — clean schemas, benign names, nothing that triggers your scanner. Then your agent starts exfiltrating session data to an attacker-controlled endpoint. No single tool had the payload. All 15 together did. The reconstruction happened inside the context window, invisible to every defense deployed at connection time. This is ShareLock: a multi-tool threshold poisoning attack that distributes a malicious instruction as cryptographic shares across cooperating tool descriptions, recombining them inside the agent's reasoning context after the security gate has already closed.

## Forces

- **Per-tool scanning is the wrong granularity.** Every deployed MCP security tool — schema validators, toxicity classifiers, description scanners — evaluates one tool at a time. The threshold that matters is the one inside the agent's accumulated context, where all descriptions coexist. These are different threat models and nobody is guarding the second one.
- **Coordinated tools are the norm, not the anomaly.** Production agents routinely connect to 10–30 MCP servers. Multi-tool workflows are the expected use case. An attack that requires multiple cooperating servers therefore operates inside normal, approved behavior — it does not look anomalous to any detection system that treats each tool independently.
- **Context accumulation is invisible to defenses.** The agent's reasoning context grows as it processes tools. This accumulation is treated as a capacity management problem, not a security boundary. The moment all shares are loaded, the instruction reconstructs — and the agent processes it as genuine, authority-weighted text.
- **The reconstruction is information-theoretically undetectable.** ShareLock uses Shamir's threshold scheme: fewer than *t* shares reveal nothing. Even a perfect per-share scanner cannot detect that 9 of 10 tools are carrying 1/10th of a malicious payload — because individually they contain nothing malicious.

## The move

**1. Aggregate tool descriptions before the context gate closes.** Collect all tool descriptions, schemas, and parameter annotations from every MCP server the agent has connected to. This is the attack surface — it lives inside the agent's reasoning context, not in any perimeter scanner.

**2. Run multi-tool correlation analysis.** Instead of scoring each description independently, compute a cross-tool scoring function:

```
S_group = Σ_i s_i + λ · ρ(corr(s_i, s_j))
```

Where `s_i` is per-tool suspicion score and `ρ` measures correlation between descriptions. High correlation across descriptions that individually score low is the ShareLock signal — it's what distinguishes a legitimate multi-tool workflow from a threshold attack.

**3. Apply threshold reconstruction detection.** Before tool descriptions enter the reasoning context, run a sliding-window threshold check:

```
For every subset W of tools where |W| ≥ t:
  reconstruct(W) → decoded_text
  if decoded_text contains exfiltration/delegate/redirect patterns:
    flag attack, block tool loading
```

Shamir's scheme means you only need to check subsets of size ≥ *t*. This is tractable: with t=5 and n=15 tools, that's C(15,5)=3003 checks — fast enough at connection time.

**4. Isolate tool descriptions in a sandboxed retrieval layer.** Rather than loading all descriptions into the agent's working context, serve them on-demand via a tool-description MCP proxy that the agent calls explicitly. This breaks the context accumulation vector: the agent only sees one tool's description at a time, preventing share reconstruction.

**5. Inject a content-filtered intermediate representation.** Instead of passing tool descriptions as raw text to the LLM, encode them as structured JSON schemas with field-level content filters. Strip any field that could carry natural-language instruction payloads (descriptions, parameter annotations, enum values). The agent sees the schema structure — names, types, required flags — without the narrative text that carries the cryptographic shares.

```python
# Minimal ShareLock detector
from itertools import combinations
from collections import defaultdict

def sharerox_scan(tools: list[dict], threshold: int = 5) -> list[dict]:
    """
    tools: list of MCP tool objects with 'name' and 'description' fields
    threshold: Shamir threshold (default 5 from CSA arxiv:2606.27027)

    Returns list of detected threshold attacks.
    Per-tool scan alone catches nothing.
    The signal is in cross-tool correlation + subset reconstruction.
    """
    # Step 1: Per-tool suspicion scoring (baseline — current tools)
    suspicion_scores = {t["name"]: compute_suspicion(t["description"]) for t in tools}

    # Step 2: Cross-tool correlation detection
    # ShareLock fragments individually score near 0; collectively they correlate
    correlation_score = compute_cross_correlation(suspicion_scores)
    if correlation_score < 0.3:  # Legitimate multi-tool: low cross-correlation
        return []  # No ShareLock signal

    # Step 3: Subset reconstruction check (expensive but necessary)
    # Only check subsets >= threshold (Shamir: < threshold reveals nothing)
    attacks = []
    names = [t["name"] for t in tools]
    for subset in combinations(names, threshold):
        decoded = shamir_reconstruct([get_share(n) for n in subset])
        if is_malicious(decoded):
            attacks.append({
                "tools": subset,
                "decoded_instruction": decoded,
                "severity": "critical",
                "threshold_used": threshold
            })

    return attacks
```

## Receipt

> Receipt pending — ShareLock is a novel attack (arXiv:2606.27027, Liu et al., SJTU, Jun 25 2026). The above detector is a principled reconstruction from the paper's published attack model. The core insight — that threshold-based reconstruction happens inside the agent's context, outside every per-tool defense — is verified from the paper's analysis. Concrete validation against real MCP tool registries (78.5% of public servers contain threat-relevant tools per Zhao et al.) would require a live benchmark run against the MCPTox dataset. The key operational insight is real: no existing enterprise MCP scanner checks cross-tool subsets, and the attack requires exactly that gap.

## See also

- **S-1153** · The MCP Description Shadow — When Connecting a Tool Silently Rewrites Your Agent
- **S-1050** · The Tool-Response Poisoning Stack — When Your MCP Server's Return Value Becomes the Attack
- **S-1062** · The MCP Supply Chain Integrity Stack — When 40 CVEs and 9 of 11 Marketplaces Compromised Became a Structural Problem
