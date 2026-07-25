# S-1642 · The Component Debugging Gap Stack

When your agent's end-to-end eval score drops 13 points and you have six possible culprits — routing, retrieval, tool selection, reasoning, formatting, context assembly — and no way to know which one.

## Forces

- **E2E evals tell you the car is broken, not which wheel has a flat** — a composite score masks which component degraded, so a failing retrieval pipeline gets the same red result as a broken tool schema.
- **Component-level evals require instrumentation you didn't build** — the agent must emit trace spans per component before you can score them independently, and retrofitting that after the fact is painful.
- **The eval frameworks (DeepEval, RAGAS, etc.) default to E2E** — getting granular component scores requires custom metrics and explicit test construction per component, not the happy-path `assert agent(input) == expected_output`.
- **Cross-component failures are invisible to both levels** — a subtle routing error that causes wrong tool selection produces a plausible final answer that passes E2E, but for the wrong reason, creating silent correctness drift.
- **Component boundaries are design choices, not given** — what counts as "a component" varies by architecture: for a LangGraph agent it might be a node; for a React agent it might be a tool wrapper. The eval granularity follows the architecture, not the other way around.

## The move

Separate the measurement problem from the system design problem by running two eval layers in parallel.

**Layer 1 — End-to-end as the smoke test.**
Run a golden dataset against the full agent pipeline, black-box style. Input in, output out. Score with LLM-as-judge or exact-match where applicable. This catches regressions that manifest in final output. Gate every PR on this.

**Layer 2 — Component spans as the debugging layer.**
Instrument the agent to emit trace spans for each decision point: routing, retrieval, tool call, response generation. Score each span independently. At minimum, separate:
- **Retrieval quality** — context relevance, recall, precision (RAGAS metrics or custom)
- **Tool selection accuracy** — did the agent call the right tool for the task type?
- **Output faithfulness** — does the final answer match the retrieved context, not hallucinate?
- **Latency per component** — p95 per span catches silent slowness before it compounds

**Layer 3 — Golden set versioning as the coverage anchor.**
A golden dataset without versioning is a liability. Production traffic reveals failure cases you didn't anticipate. The pattern: production failure → trace capture → test case extraction → golden dataset → CI gate. Each release bumps the version (MAJOR/MINOR/PATCH by change type). 100 curated goldens + 1,000 production-derived cases is a common ratio from teams running this at scale.

**The key insight** — don't try to make one eval layer do both jobs. E2E gives you confidence the system works; component spans give you confidence you know why it doesn't.

## Evidence

- **Engineering blog:** The "100 Golden + 1,000 Production" architecture from Balachander Keelapudi (substack, 2025) describes a two-layer eval design where expert-curated goldens optimize for validity (measuring what matters) and production-trap-derived cases optimize for recall (covering the real failure distribution). Neither layer alone is sufficient — the convergence property only emerges when both run together and the golden set coverage increases monotonically from production failure captures.
  — https://balachanderkeelapudi.substack.com/p/the-100-golden-1000-production-architecture

- **Framework documentation:** DeepEval's component-level eval approach explicitly distinguishes between end-to-end tests (black-box: input → output) and component-level tests (score individual spans like retrieval, tool selection, reasoning). Their recommended pattern: run both, use component scores to isolate failures when E2E goes red, use E2E as the release gate.
  — https://deepeval.com/docs/getting-started-agents

- **Production failure analysis:** Arthur's regression testing guide describes the trace-to-test-case loop: production failure captures a real input distribution and edge case that no synthetic dataset would include. Teams that treat every production failure as a permanent addition to the golden dataset (not just a one-time fix) build coverage that compounds over time. The key engineering requirement is trace instrumentation that captures enough state at failure time to reconstruct the test case.
  — https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures

## Gotchas

- **Instrumentation is the prerequisite, not the eval** — if your agent doesn't emit trace spans per component, you can't score them. Build instrumentation on day one; retrofitting it after 6 months of production traffic requires re-running historical traces you never captured.
- **LLM-as-judge has bias propagation at scale** — when your judge model has the same capability ceiling as your agent model, it systematically over-rates borderline outputs. Calibrate the judge against human annotations using Spearman correlation before relying on it as the sole scorer for component spans.
- **Synthetic goldens are a starting point, not an endpoint** — LLM-generated test cases cover the model's own blind spots poorly. Use them to bootstrap coverage, but expect production failure captures to regularly contradict synthetic test expectations and update the golden set accordingly.
- **Component boundaries must match your observability stack** — if you're using LangSmith, trace spans are automatic; if you're using custom instrumentation, you must define and name spans explicitly. The eval framework reads what you emit, not what you intended to emit.
