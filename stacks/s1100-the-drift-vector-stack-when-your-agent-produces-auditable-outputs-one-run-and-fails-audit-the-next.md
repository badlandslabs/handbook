# S-1100 · The Drift Vector Stack: When Your Agent Produces Auditable Outputs One Run and Fails Audit the Next

Your agent processes the same 10-K filing on Tuesday that it processed on Monday. Same model. Same temperature=0. Same input. Tuesday's reconciliation fails audit because the output token count, JSON structure, and three field values differ from Monday's. The financial institution's regulator asks: "Can you reproduce the Monday output?" You cannot — and you don't know why. This is not a model quality problem. It is a **drift vector problem**: your agent's outputs are drifting across dimensions that have nothing to do with capability.

## Forces

- **"Deterministic" at T=0 is a legal fiction.** GPU cluster scheduling, floating-point non-determinism in attention kernels, and batch-invariance failures at token sampling boundaries produce different outputs on identical inputs — even with seed parameter set. OpenAI's own documentation admits their seed "mostly" produces identical outputs, not a guarantee.
- **Scale is inversely correlated with deterministic consistency.** IBM's arXiv:2511.07585 (480 runs, n=16 per condition, 5 models × 3 tasks × 2 temperatures) found Granite-3-8B and Qwen2.5-7B at 100% consistency at T=0.0; GPT-OSS-120B at only 12.5% consistency regardless of configuration (p<0.0001, Fisher's exact). Larger models are architecturally less reproducible.
- **Tokenizer drift inflates token counts and enables injection.** arXiv:2511.07585 documents tokenizer drift where text normalization changes inflate token counts by up to 112% — and enables command injection vulnerabilities in code-generation tasks. If your agent generates shell commands, tokenizer drift means a prompt that was safe in June is not safe in August.
- **Cross-provider validation is the only reliable audit guarantee.** If you serve the same input to two providers and get different outputs, you have a compliance problem. The regulatory answer is not "trust the model" — it is "prove the output is reproducible."
- **RAG tasks drift more than structured tasks.** IBM's study shows SQL generation at T=0.2 remains stable across runs; RAG question-answering shows 25–75% drift. The drift profile depends on task type, not just model.

## The Move

Build a three-layer drift management system: **Detection → Attribution → Mitigation**.

### Layer 1 — Drift Detection: Run Outputs Through an Invariant Checker, Not a Judge

Do not use an LLM judge to detect drift. Use **structural invariants** that fail fast:

```python
import hashlib, json

def capture_invariant(output: str, context: dict) -> dict:
    """Capture structural invariants for a production run."""
    return {
        "output_hash": hashlib.sha256(output.encode()).hexdigest(),
        "token_count": len(output.split()),          # approximate; use tokenizer in prod
        "json_valid": _is_valid_json(output),
        "field_count": _count_json_fields(output),
        "schema_match": _matches_schema(output, context.get("expected_schema")),
        "provider": context.get("provider"),
        "model": context.get("model"),
        "seed": context.get("seed"),
        "temperature": context.get("temperature"),
        "run_id": context.get("run_id"),
    }

def detect_drift(invariant_a: dict, invariant_b: dict) -> dict:
    """Compare two runs of the same input. Returns drift flags."""
    drift = {}
    if invariant_a["output_hash"] != invariant_b["output_hash"]:
        drift["content_drift"] = True
        drift["content_drift_pct"] = (
            len(invariant_b["output"]) / max(len(invariant_a["output"]), 1) - 1
        ) * 100
    if invariant_a["json_valid"] != invariant_b["json_valid"]:
        drift["schema_validity_drift"] = True
    if invariant_a.get("field_count") != invariant_b.get("field_count"):
        drift["field_count_drift"] = {
            "run_a": invariant_a.get("field_count"),
            "run_b": invariant_b.get("field_count"),
        }
    return drift
```

Store invariants in an append-only log (S3, GCS, or a time-series DB). This is your audit trail — it proves drift occurred, when, and which dimension drifted.

### Layer 2 — Drift Attribution: Three-Source Diagnostic

When drift is detected, attribute it to one of three sources:

**Source A — Model-level nondeterminism.** The dominant source for large frontier models. Evidence: identical seed + temperature + prompt produces different outputs. Mitigation: switch to smaller, deterministic models (7-8B range) for structured tasks; or accept probabilistic behavior and build tolerance.

**Source B — Provider-level configuration drift.** Your provider changed model weights, batching strategy, or hardware mid-deployment. Evidence: drift coincides with provider changelog. Mitigation: pin to a specific model version/commit where available; use `system_fingerprint` (OpenAI) or equivalent to detect provider-side changes.

**Source C — Tokenizer drift.** Evidence: the same input text produces different token counts across runs or providers. Mitigation: normalize tokenization by running inputs through the target model's tokenizer before injection; never hardcode token counts as constants.

```python
from transformers import AutoTokenizer

def normalize_tokenization(text: str, target_model: str) -> list[int]:
    """Normalize input across tokenizers to detect tokenizer drift."""
    tokenizer_a = AutoTokenizer.from_pretrained("your-model-a")
    tokenizer_b = AutoTokenizer.from_pretrained("your-model-b")
    tokens_a = tokenizer_a.encode(text, add_special_tokens=False)
    tokens_b = tokenizer_b.encode(text, add_special_tokens=False)
    if len(tokens_a) != len(tokens_b):
        logger.warning(
            f"Tokenizer drift detected: {len(tokens_a)} vs {len(tokens_b)} tokens "
            f"for identical input. Model: {target_model}"
        )
    return tokens_a  # use as reference
```

### Layer 3 — Cross-Provider Validation Gate

For regulated outputs, run the same input through two independent providers and gate on **invariant agreement** before committing the output:

```python
async def validated_completion(prompt: str, ctx: dict) -> str:
    """Dual-provider validation with invariant gate."""
    provider_a = ctx["provider_a"]  # e.g., OpenAI
    provider_b = ctx["provider_b"]  # e.g., Anthropic or local 7B

    output_a = await provider_a.complete(prompt, seed=42, temperature=0.0)
    output_b = await provider_b.complete(prompt, seed=42, temperature=0.0)

    inv_a = capture_invariant(output_a, {**ctx, "provider": "a"})
    inv_b = capture_invariant(output_b, {**ctx, "provider": "b"})
    drift = detect_drift(inv_a, inv_b)

    if drift.get("content_drift"):
        # Log to append-only audit store, then handle per policy:
        await audit_log.append({"drift": drift, "inv_a": inv_a, "inv_b": inv_b})
        if len(drift.get("content_drift_pct", 0)) > 5.0:  # 5% materiality threshold
            raise DriftMaterialityError(f"Output drifted {drift['content_drift_pct']:.1f}%")

    # For low materiality: pick A (primary provider), log B as shadow
    return output_a
```

The 5% materiality threshold mirrors financial audit practice from arXiv:2511.07585. Tune it per domain.

## Receipt
> Verified 2026-07-14 — Source: arXiv:2511.07585 (Khatchadourian & Franco, IBM, AI4F @ ACM ICAIF '25). 480 runs (n=16 per condition). Key numbers: Granite-3-8B/Qwen2.5-7B = 100% consistency at T=0; GPT-OSS-120B = 12.5% consistency. Tokenizer drift token inflation up to 112%. SQL generation stable at T=0.2; RAG QA 25–75% drift. Practical mitigations: structural invariants, cross-provider validation, tokenizer normalization. Code examples drawn from the IBM harness at github.com/ibm-client-engineering/output-drift-financial-llms and principles from arXiv:2511.07585.

## See also
- [S-1015 · The Stability Gradient](/opt/data/handbook/stacks/s1015-the-stability-gradient-when-your-agent-works-once-and-fails-twice.md) — single-trial evaluation lies and pass@1 vs consistency gap (this entry extends S-1015 with attribution and mitigation layers)
- [S-885 · The Behavioral Drift Detector](/opt/data/handbook/stacks/s885-the-behavioral-drift-detector-continuous-agent-competence-monitoring.md) — rolling baseline and z-score drift detection for agent competence
- [S-998 · The Capability Ceiling](/opt/data/handbook/stacks/s998-the-capability-ceiling-when-deploying-to-the-wrong-complexity-tier-silently-undermines-your-agent.md) — complexity profiling before deployment
