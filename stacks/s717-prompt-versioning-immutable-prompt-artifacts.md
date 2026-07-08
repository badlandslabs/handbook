# S-717 · Prompt Versioning and Immutable Prompt Artifacts

[Prompts are code. They change behavior, break downstream parsers, and cause silent regressions — yet most teams edit them like configuration strings, with no history, no rollback, and no testing. The discipline of treating prompts as immutable, versioned software artifacts is the gap between a demo that works and a production system you can actually maintain.]

## Forces

- **A prompt is a behavioral specification, not a string.** Changing three words can spike structured-output error rates or shift agent behavior in ways that only surface in production under specific inputs.
- **Prompts decay.** Model updates, provider changes, and upstream data shifts silently alter the execution context a prompt was tested against.
- **The execution context is a unit.** Prompt text + model + temperature + sampling params + retrieval config form a single coherent artifact. Versioning only the text while the model floats is incomplete.
- **Hot-reload is necessary in production.** Unlike software binaries, prompts change more frequently. You cannot rebuild and redeploy every time a prompt is tuned.
- **Multi-step agents cascade.** A prompt change in stage 2 may actually be caused by a silent change upstream in stage 1's output format.

## The move

### 1. The Immutability Principle

Once a prompt version is published to production, **it must never be modified in place.** Any change — even a typo fix — creates a new version. This is the same discipline as database migrations: you write forward, never mutate.

```
# Wrong: editing in place
prompts["customer-service"] = "You are now more conversational..."

# Right: creating a new immutable artifact
prompts.create("customer-service", version="2.1.0", content=...)
prompts.publish("customer-service", version="2.1.0")
```

Each artifact is content-addressable by default: identical content produces the same ID. This makes it trivially detectable when anything changed.

### 2. Semantic Versioning for Prompts

Use `major.minor.patch`:

- **Major** (`x.0.0`): Changes the output schema or breaks downstream consumers
- **Minor** (`x.y.0`): Changes behavior without breaking schema compatibility
- **Patch** (`x.y.z`): Typos, formatting, no behavioral change

```python
@dataclass
class PromptArtifact:
    name: str
    version: str          # SemVer string
    content: str
    model: str            # e.g., "claude-opus-4-5"
    temperature: float
    max_tokens: int | None
    retrieval_config: dict | None = None  # RAG pipeline ID, top_k, etc.
    author: str
    rationale: str        # Why this change was made
    created_at: datetime

    @property
    def artifact_id(self) -> str:
        """Content-addressable ID: identical content → same ID."""
        payload = f"{self.content}|{self.model}|{self.temperature}|{self.max_tokens}"
        return hashlib.sha256(payload.encode()).hexdigest()[:12]
```

Bundling the model and sampling params is critical. Switching from `claude-opus-4-5` to `claude-opus-4-6` can silently shift behavior even if the prompt text is identical. These must travel together.

### 3. Two Registry Patterns

**Git-based (versioned flat files):** Prompts live in a repository alongside tests and evaluation datasets. Changes go through pull requests. This is the right default for teams with existing CI/CD.

```
prompts/
├── customer-service/
│   ├── v1.0.0.yaml    # initial
│   ├── v1.1.0.yaml    # minor: sharper tone
│   └── v2.0.0.yaml    # major: new output schema
└── triage/
    └── v1.0.0.yaml
```

**Proxy-based (runtime registry):** Prompts are stored in a dedicated service (PromptLayer, Helicone, or a homegrown registry) and resolved at call time. The app code references `prompt_id` instead of embedding text. This enables hot-reload without redeployment and provides built-in observability per prompt version.

```python
# Proxy-based: prompts resolved at runtime
response = llm.complete(
    prompt_ref="customer-service@v2.0.0",  # not the text itself
    model="claude-opus-4-5",
    temperature=0.3,
)
```

The proxy resolves the artifact, logs which version was used, and can be updated independently of the app.

### 4. Prompt Testing in CI

Every new version must pass tests before promotion. Tests run against the same eval harness used for the old version:

```python
def test_customer_service_v2_compliance(prompt_artifact):
    """v2 output schema must match v1 for backward-compatible fields."""
    result = run_agent(prompt_artifact, TEST_CASES)
    
    # Schema contract: summary + tags must exist and be correct types
    for item in result.outputs:
        assert isinstance(item.summary, str)
        assert isinstance(item.tags, list)
        assert item.tags  # not empty
    
    # Behavioral regression: quality should not degrade
    quality_scores = [score(o) for o in result.outputs]
    prev_avg = get_baseline("customer-service", previous_major())
    assert mean(quality_scores) >= prev_avg * 0.95  # 5% tolerance
```

### 5. Cascade Tracing for Multi-Step Agents

In a pipeline where each stage uses a versioned prompt, a quality regression in stage N+1 may originate from a change in stage N's output format. Tag each call with its artifact ID:

```python
# Each stage carries its artifact ID through the pipeline
context = {
    "stage": "document_classifier",
    "prompt_artifact_id": "a3f9b2",
    "prompt_version": "1.4.0",
    "model": "claude-sonnet-4-6",
}
```

When an eval failure surfaces at stage N+1, trace backward through artifact IDs to identify whether the regression is in the current stage or upstream.

## Receipt

> Verified 2026-07-06 — Concepts validated against: Tian Pan (prompt versioning blog, March 2026), MyEngineeringPath prompt management guide, linesNcircles 2026 versioning guide. Implementation patterns drawn from industry practice documented across these sources. Real execution pending: the test harness and proxy registry examples above are structural illustrations; a production implementation would require the team's specific eval harness and registry choice.

## See also

- [S-64 · Agent Output Schema Versioning](s64-agent-output-schema-versioning.md) — output schemas version on the same immutability principle
- [S-222 · Agent Trajectory Replay](s222-agent-trajectory-replay.md) — tagged traces enable pinpointing which prompt version caused a regression
- [S-251 · Golden Dataset Curation As Code](s251-golden-dataset-curation-as-code.md) — golden datasets are the test surface for prompt version promotion
- [S-36 · System Prompt Architecture](s36-system-prompt-architecture.md) — system prompt is the artifact being versioned
