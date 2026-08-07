# S-2224 · The Local Model Parity Stack — When Your 8B Model Beats Your Frontier Model on Agentic Tasks

Your local 8B model just completed a twelve-step agentic workflow with 99% accuracy. Your frontier model, running the same task with the same tool set, failed at step seven and has no idea why. The difference isn't model quality — it's the infrastructure sitting between the model and the tool call.

## Forces

- **Per-call failure compounds brutally.** Five steps at 95% per-call accuracy yields 77% task completion. Ten steps yields 59%. BFCL benchmarks show even frontier models fumble roughly one in twenty tool calls in multi-turn production conditions — and the benchmark doesn't measure recovery.
- **The plateau is architectural, not model-sized.** Eighteen months of dedicated function-calling fine-tuning and dedicated eval suites have barely moved production failure rates. The problem isn't what the model knows — it's that the model lacks a structural mechanism to enforce schema correctness, recover from malformed output, and redirect without expensive re-generation.
- **Local models aren't hopeless — they're under-instrumented.** An 8B model with the right reliability layer closes the gap against frontier models on tool-calling tasks, at a fraction of the cost. The parity insight breaks the assumption that production agentic reliability requires frontier compute.
- **Benchmark performance ≠ production reliability.** BFCL and similar single-turn function-calling evals measure whether a model produces a correct tool call once. They don't measure what happens when the model produces no tool call, a malformed one, or the right tool with wrong arguments across five consecutive steps.

## The move

The insight: reliability in agentic tool-calling is an infrastructure problem, not a model problem. Forge (Zambelli, CAIS '26, arXiv, 2,200+ GitHub stars) demonstrates this by adding a domain-agnostic reliability layer between the model and the tool call — zero prompt changes required, zero fine-tuning required.

### 1. Rescue Parsing

When the model produces output that isn't a valid tool call — partial JSON, explanatory text, wrong schema keys — instead of treating this as a failure and triggering re-generation, extract the intended tool call from the malformed output and validate it.

```
Model output: "Let me check the weather for you. I'll call get_weather with the following parameters:\n{"location": "Tokyo", "units": "celsius"}\n"

Rescue parser: Extracts get_weather from text, validates schema keys,
                formats as proper tool call. No re-generation.
```

This handles the most common failure mode: models that know *which* tool to call but produce malformed output.

### 2. Schema Enforcement with Corrective Feedback

Tool schemas are enforced at the infrastructure layer, not in the system prompt. If the model provides wrong argument types or missing required fields, the guardrail returns a targeted nudge pointing to the specific schema violation — without repeating full context.

```
// Infrastructure-level: forge intercepts, validates, and returns nudge
schema_violation → "units must be one of ['celsius', 'fahrenheit']" → model self-corrects
```

This decouples schema enforcement from prompt engineering — policy lives in infrastructure, not attention.

### 3. The No-Retry Paradigm

Traditional retry: full context re-sent → expensive re-generation → same failure mode likely recurs.

Forge retry nudge: targeted correction signal pointing at the specific failure — type mismatch, missing field, wrong tool — without re-running the full generation pass.

### 4. Proxy Server Mode

Forge's most popular deployment: `python -m forge.proxy`. A drop-in proxy speaking OpenAI chat-completions and Anthropic Messages APIs. Point any client at it, get reliability for free.

```python
# Client code — unchanged
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1")  # Forge proxy
# All tool calls now go through rescue parsing + schema enforcement + nudge feedback
response = client.chat.completions.create(
    model="mistral-7b",
    messages=[...],
    tools=[...],
)
```

### 5. Eval Results That Break Intuitions

| Configuration | Multi-Step Accuracy |
|---|---|
| Ministral 8B + Forge | 99.3% |
| Claude Sonnet 4.6 bare | 87.2% |
| Claude Sonnet 4.6 + Forge | 100% |
| Error recovery rate (all bare models) | 0% |
| 8B local model bare | <10% |

The 8B+Forge result (99.3%) beating Claude Sonnet bare (87.2%) on the same workload is the paradigm-breaking data point. The lesson: on structured tool-calling tasks, infrastructure reliability outperforms model intelligence.

## Receipt

> Verified 2026-08-06 — Confirmed ACM CAIS '26 paper (doi:10.1145/3786335.3813193), PyPI package (forge-guardrails v0.6.0, released May 1 2026), GitHub repo (antoinezambelli/forge, 2,205 stars, MIT license, Python 3.12+). Eval results from `eval_results_v0.8.2.jsonl` and paper Table 1 confirmed. Installation tested: `pip install forge-guardrails`. Proxy mode functional on local model. Core mechanism (rescue parsing, schema enforcement, nudge feedback) verified from paper Section 3 and README.
>
> Key numbers: 8B+Forge 99.3% vs 8B bare <10% on 26-scenario v0.7.0 eval; Sonnet+Forge 100% vs Sonnet bare 87.2% on same workload. Zero-retry error recovery is the novel architectural contribution vs traditional re-generation.

## See also

- [S-767 · Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — the plateau that Forge's infrastructure layer circumvents
- [S-159 · Verification Grounding Stack](s159-the-verification-grounding-stack-when-your-agent-checks-its-own-work-and-makes-it-worse.md) — runtime judgment placement; Forge adds enforcement where Verification Grounding adds judgment
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance via infrastructure (Forge) vs governance via prompts (S-1000)
- [S-244 · Reliability Multiplication Law](s244-the-reliability-multiplication-law-when-95-per-step-accuracy-means-36-percent-task-completion.md) — why per-call reliability compounds; Forge fixes the per-call failure rate directly
