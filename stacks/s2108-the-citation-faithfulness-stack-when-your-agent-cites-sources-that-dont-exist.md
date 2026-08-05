# S-2108 · The Citation Faithfulness Stack

When your research agent finishes writing and you audit its bibliography, you find three papers that don't exist, two that exist but have the wrong authors, and one real paper cited for the exact opposite claim. The citations look perfect — formatted correctly, plausible venue names, reasonable year. No error surfaced during execution. This is citation hallucination, and it is now a venue-scale problem: ICLR 2026 desk-rejected over 600 submissions for fabricated references.

## Forces

- **Confidence decouples from accuracy.** A model generates a citation that reads perfectly and scores high on formatting checks. The hallucination lives in the metadata, not the prose. Your syntax validator never sees it.
- **Binary detection is useless for triage.** Existing tools (Citely, CiteCheck, RefCheck-AI) return Real/Fake — no signal about *which field* broke. An auditor with a "fake" label still has no idea whether to fix the title, authors, or venue.
- **PDF parsing compounds the problem.** When the agent ingests papers as PDFs, its citation parser drops entries, mis-segments fields, and occasionally invents fields of its own. The verifier inherits a corrupted input before auditing begins.
- **Propagation is silent.** Search engines surface fabricated citations, downstream researchers cite the hallucinated claim, and the fake paper accrues citation count — creating a feedback loop of fake authority.
- **The citation is the trust surface.** In legal, medical, and academic outputs, a single fabricated citation destroys credibility for the entire document.

## The move

**Citation faithfulness** means every factual claim in agent output must be traceable to a verifiable source — not just "the model said so." The stack has three layers:

### Layer 1 — Field-Level Verification (not binary)

Decompose each citation into six fields: title, authors, venue, year, DOI/URL, and peripheral (volume, pages, publisher). Verify each independently. A paper can be real but cited for the wrong claim (P-type) — that's as dangerous as a hallucinated one.

The 12-code taxonomy (Li et al., UMass/Ohio State, arXiv:2605.08583) separates citations into:

| Class | Code | Meaning |
|-------|------|---------|
| Real | R1–R3 | Correct, minor variant, or corrected metadata |
| Potential | P1–P3 | Needs manual verification; plausible but unverified |
| Hallucinated | H1–H6 | Title/author mismatch → year error → wrong venue → entirely fabricated |

```python
# Minimal citation verification pipeline
import httpx

async def verify_citation(title: str, authors: list[str], venue: str, year: int):
    """Verify a single citation across three sources. Returns a faithfulness score."""
    score = 0.0
    sources_checked = []

    # Stage 1: CrossRef API (authoritative for DOI/metadata)
    try:
        resp = await httpx.AsyncClient(timeout=10).get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 3}
        )
        if resp.status_code == 200:
            results = resp.json().get("message", {}).get("items", [])
            if results:
                best = results[0]
                score += 0.4  # CrossRef match is strong signal
                sources_checked.append("crossref")
                # Check year alignment
                if best.get("published-print", {}).get("date-parts", [[]])[0]:
                    actual_year = best["published-print"]["date-parts"][0][0]
                    if abs(actual_year - year) <= 1:
                        score += 0.2
    except Exception:
        pass

    # Stage 2: Semantic Scholar
    try:
        resp = await httpx.AsyncClient(timeout=10).get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "fields": "title,authors,year,venue", "limit": 3}
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                score += 0.25
                sources_checked.append("semanticscholar")
    except Exception:
        pass

    # Stage 3: Google Scholar (fallback, rate-limited)
    # In production: use SerpAPI or a dedicated scraper with proper rate limiting
    # Score contribution: 0.15 if found

    return {
        "score": min(score, 1.0),
        "sources": sources_checked,
        "verdict": "REAL" if score > 0.8 else "POTENTIAL" if score > 0.4 else "HALLUCINATED"
    }
```

### Layer 2 — Citation-Grounded Generation

Instruct the agent to anchor every factual claim to a verified citation. This means the citation exists *before* the text is written, not after.

```python
SYSTEM_PROMPT = """You are a research writing assistant. For every factual claim you make, you MUST:
1. First verify the claim against a known source
2. Cite using [SourceID:score] notation, e.g., [crossref:10.1234/5678:0.95]
3. Never assert a claim without a citation with faithfulness score >= 0.7
4. Flag uncertain claims with [CLAIM: needs_verification]

If you cannot verify a claim, say "This claim requires verification" instead of guessing.
Do not fabricate citations. A missing citation is better than a hallucinated one."""
```

### Layer 3 — Faithfulness Scoring at Output Gate

Before user-facing delivery, run a judge agent on the full output. The judge is specifically calibrated for faithfulness (use a different model family from the generator — same-family judges are too lenient).

```python
FAITHFULNESS_JUDGE_PROMPT = """Given the following text and its citations, score each citation for faithfulness.
For each [SourceID] in the text:
1. Does the cited paper actually support the claim made?
2. Is the metadata (title, authors, year) correct?
3. Score 0.0 (fabricated) to 1.0 (fully verified).

Return a per-citation breakdown with verdicts: VERIFIED / MISALIGNED / FABRICATED.
Output: JSON list of {{"cite": "...", "score": float, "verdict": str}}"""

# Run on every agent output before delivery
async def gate_output(agent_text: str, citations: list[str]) -> dict:
    score = await call_judge(FAITHFULNESS_JUDGE_PROMPT, agent_text, citations)
    if score["avg_faithfulness"] < 0.85:
        return {"pass": False, "unverified": score["low_confidence_cites"]}
    return {"pass": True, "score": score}
```

## Receipt

> Verified 2026-08-04 — CITETRACER (Li et al., arXiv:2605.08583) achieves 97.1% catch rate on real ICLR 2026 + ACM CCS desk-rejected submissions (957 papers) using the 12-code taxonomy with a 4-stage cascading multi-agent pipeline. Class-level F1 on synthetic benchmark (2,450 citations): Real=97.0, Potential=95.8, Hallucinated=98.5. Field-level decomposition of citation metadata is the key insight that binary detectors miss — P-type (plausible but unverifiable) citations are as dangerous as H-type (fabricated) for downstream propagation. Citation pending on the minimal verification pipeline above (not run in this session).

## See also

- [S-1007 · The Tool-Call Hallucination Plateau](/stacks/s1007-tool-call-hallucination-plateau.md) — the broader hallucination family; tool-call hallucination and citation hallucination share the same architectural response (verification gate before action)
- [S-997 · The Agent Observability Stack](/stacks/s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — trace-level instrumentation for catching faithfulness failures before user-facing output
- [S-1239 · The Runtime Verification Loop](/stacks/s1239-the-runtime-verification-loop-when-inline-agent-step-verification-becomes-your-quality-gate.md) — inline verification at tool-call and memory-fetch boundaries; citation verification is the output-side mirror of this gate
