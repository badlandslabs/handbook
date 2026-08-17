# [S-2742] · The Agentic Audit Specification Gap — When Your Security Audit Says "Secure" but the Agent Doesn't Know Why

When you deploy an LLM agent to audit your codebase for vulnerabilities, it finds real bugs — bugs that human reviewers missed for years. Then it pronounces other code "secure" and you trust it. The problem: the agent never knew why. It made tacit assumptions about a function's inputs, its trust boundaries, and its callers that happen to be wrong. The security verdict is opaque, the assumptions are buried in reasoning chains nobody reads, and the missed vulnerabilities are invisible.

## Forces

- **Agents find real vulnerabilities** — Mythos-class agents uncover 34–370% more bugs than prior state-of-the-art, discovering vulnerabilities masked for years.
- **Agents don't know what they don't know** — When an agent calls a function `secure`, it made silent assumptions about input ranges, caller identity, and environmental context that were never articulated.
- **Auditing the auditor requires what the auditor produced** — You can't validate hidden reasoning without an explicit artifact. In-source assertions that the agent commits when it judges code safe are the load-bearing artifact for post-audit validation.
- **Analytical agents miss corner cases; fuzzing agents lack semantic understanding** — Neither approach alone closes the gap. Analytical agents' reasoning is intuitive and untested. Fuzzing agents reach deep program states but lack context to know which states matter.
- **The audit artifact outlives the session** — A vulnerability report without the reasoning behind it is a black box. The next auditor (human or agent) gets no signal from the previous verdict.

## The move

The move is **specification-inference-as-commitment**: when an agent auditing code judges a function or code path secure, it must articulate the assumption as an explicit, machine-checkable in-source assertion — then a guided fuzzer attempts to falsify it. Either the assertion holds (the code is provably safe under the stated assumptions) or the assertion fails (the assumption was wrong, and the agent found a real vulnerability). This converts opaque reasoning into a durable, falsifiable artifact.

### Phase 1 — Specification Extraction (The Commitment)

As the agent analyzes a codebase component for vulnerabilities:

1. When the agent deems a function secure, it generates a **local invariant assertion** (an in-source comment or assert statement) that captures its implicit assumptions about the function's inputs and trust boundaries — e.g., `// Assert: input_len < MAX_PATH && caller == AUTHENTICATED_USER`.
2. This forces the agent to externalize what would otherwise be latent: "I assumed the caller would be authenticated" becomes a named assertion that can be examined, challenged, or verified.
3. The assertion is committed alongside the security verdict — the audit artifact now contains the reasoning, not just the result.

### Phase 2 — Runtime Falsification (The Validation)

1. A **guided fuzzer** reads the in-source assertions and attempts to construct inputs that violate them — not random fuzzing, but targeted falsification attempts against the specific stated assumptions.
2. If the fuzzer finds a violation → real vulnerability discovered (the assumption was wrong). The agent's "secure" verdict was based on a flawed premise.
3. If the fuzzer cannot falsify the assertion after N attempts → the assumption is corroborated, not proven correct, but the audit is now grounded in evidence rather than intuition.
4. Violated assertions feed back into the agent's specification set — the agent refines its assumptions and generates a new, harder-to-falsify assertion.

### Key Results (Code-Augur, NUS, arXiv:2606.18619, June 2026)

- Finds **34–370% more bugs** than state-of-the-art baselines (ATLANTIS, Claude Code)
- Discovered **22 new vulnerabilities** in real-world projects; 16 confirmed and fixed
- Works effectively with small models (7B) when combined with the specification-falsification loop
- The specification inference step is what enables small models to punch above their weight — they don't need to know everything, they need to know what they don't know

### The Falsification Threshold

Not all assertions are equally falsifiable. Set a coverage threshold: if the fuzzer cannot exercise the assertion's control-flow path within N iterations, treat the assertion as **unfalsifiable** (not proven true), flag it for human review, and document it in the audit report as a "credible-but-unverified assumption."

```python
# Example: agent commits this assertion during audit
def process_user_input(data: bytes) -> str:
    # SPEC: assume data is utf-8 encoded, len < 10_000 bytes
    # FUZZ: attempt to violate (non-utf8, oversized)
    assert isinstance(data, bytes), "SPEC violation: non-bytes input"
    assert len(data) <= 10_000, "SPEC violation: oversized input"
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # Already handled — but what about surrogate escapes?
        return data.decode("utf-8", errors="replace")
    # The assertion passed; the error=replace fallback was judged acceptable
    # Re-examine: is silent replacement a security-relevant behavior?
```

### The Audit Artifact Structure

A complete agentic security audit should produce:

| Component | Purpose |
|-----------|---------|
| `assertions.json` | List of all committed specifications (assumptions → in-source locations) |
| `fuzz_results.json` | Per-assertion falsification outcome (passed / violated / unfalsifiable) |
| `refined_specs.json` | Assertions that survived falsification with augmented assumptions |
| `missed_cases.json` | Assumptions that were violated → real vulnerabilities found |
| `coverage_report.json` | Which code paths were exercised by the fuzzer vs. purely analytical reasoning |

Without this structure, you have a vulnerability report but no audit trail — and you cannot distinguish a genuine finding from a missed vulnerability dressed in the same "secure" language.

## Receipt

> Verified 2026-08-16 — arXiv:2606.18619v1 (Code-Augur, Luo et al., NUS, June 2026): 34–370% bug improvement vs ATLANTIS/Claude Code baselines, 22 new vulnerabilities found, 16 confirmed+fixed. Specification-as-commitment paradigm extracted from paper methodology section. Falsification feedback loop verified against paper's 3-phase architecture diagram (specification extraction → falsification → specification refinement). Unfalsifiable assertion coverage threshold confirmed as paper's "guided fuzzing" component. No handbook entry covers this angle.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — behavioral eval as falsification complement to analytical reasoning
- [S-2688 · The Agent Blast-Radius Stack](s2688-the-agent-blast-radius-stack-when-the-agent-gets-in-and-everything-is-on-fire.md) — what happens after the agent finds (or misses) a vulnerability in production infrastructure
- [S-2359 · The Inter-Agent Trust Propagation Stack](s2359-the-inter-agent-trust-propagation-stack-when-your-security-boundary-is-the-agent-you-trust.md) — trust-mediated collaboration risk in multi-agent audit pipelines where one agent's "secure" verdict propagates as authorization
