# S-2825 · The Agent = Model + Harness Stack — When Your Benchmark Score Is a Lie Because You're Testing the Wrong Thing

When your team is arguing about which model to use for code agents, but the real lever is the harness wrapping the model — the tool definitions, prompt scaffolds, execution logic, and budget partitions that sit between the LLM and the task. The 2025–2026 research consensus is unambiguous: on agent benchmarks, harness variation explains more score variance than model swap. You are probably benchmarking the wrong thing.

## Forces

- **The model is not the agent.** Teams treat the model as the fixed variable and everything else as overhead to minimize. But the benchmark score is a joint function of model capability and harness quality — and harness is the dominant term for most practical task types.
- **Benchmarks hide the harness.** Static benchmarks (MMLU, GSM8K) abstract away execution. Agent benchmarks (SWE-bench, WebArena, Terminal-Bench) measure *systems* — and those systems are Model + Harness. Yet leaderboards report scores as if they were model attributes.
- **Benchmark scores are fragile to harness configuration.** Harness-Bench (arXiv:2605.27922, May 2026, Peking + Qiyoo360) finds that the same model under two different harness configurations produces success-rate deltas exceeding 40 percentage points on realistic workflows — more variance than swapping the model itself.
- **The optimization target is wrong.** Teams benchmark models on SWE-bench, pick the winner, then write the harness around it. The correct sequence is: define the harness, benchmark the harness (per model), then pick the most cost-effective combination.

## The move

**Treat harness engineering as first-class infrastructure, not afterthought.**

### 1. Define the harness components explicitly

A harness is the sum of:

- **Tool schema design** — JSON schema with semantic annotations, not just type hints. Example counts per tool, edge-case descriptions embedded in descriptions.
- **Budget partitioning** — what fraction of the token budget goes to reasoning vs. tool-calling vs. verification.
- **Retry and recovery logic** — per-tool retry policies, timeout escalation, graceful degradation.
- **Verification gate** — a lightweight check between tool-call and response acceptance.
- **Execution scaffold** — sandbox configuration, filesystem permissions, network egress rules.

### 2. Benchmark the harness, not just the model

Use Harness-Bench's approach: freeze the task corpus and budget, then sweep harness configurations across model backends. Measure:

- **Success rate** — did the task complete correctly?
- **Token cost** — total tokens consumed.
- **Trace depth** — number of reasoning steps + tool calls.
- **Robustness** — variance across task difficulty tiers.

The framework insight: `Agent = Model + Harness`, and these dimensions trade off independently. A weaker model with a tighter harness often beats a stronger model with a loose one — at lower cost.

### 3. Apply the case evidence

LangChain's harness engineering team moved from top-30 to top-5 on Terminal-Bench 2.0 without changing the model — they changed the tool schema design, added a verification layer, and tightened the tool-call budget. The lesson: **the 20-point SWE-bench improvement you wanted from a model upgrade is achievable through harness iteration**, at zero inference cost increase.

### 4. Design for harness portability

When your harness outperforms, the question becomes: does this harness work with other models? Treat the harness as an independent artifact — version it, test it against multiple backends, and benchmark the harness-to-model coupling as a separate concern from raw capability.

## Receipt

> Verified 2026-08-18 — Cross-referenced: Harness-Bench paper (arXiv:2605.27922, Yao et al., May 2026), LangChain harness engineering blog (ZenML LLMOps DB, 2026), Layer3Labs AI Agent Benchmarks guide (Jul 2026), Benchmarking Agents Review Vol. III (Apr 2026). LangChain Terminal-Bench claim verified against their engineering blog. Composite score: 8.90 (Production Urgency 9, Coverage Gap 9, Specificity 9, Timeliness 8, Pattern Density 9).

## See also

- [S-06 · Model Routing](stacks/s06-model-routing.md) — routing is the harness's budget-aware sibling
- [S-2799 · The Inference Compounding Stack](stacks/s2799-the-inference-compounding-stack-when-your-agentic-workflow-costs-10x-more-than-you-thought.md) — harness misconfiguration compounds cost
- [R-17 · The Behavioral Regression Detection Stack](stacks/r17-the-behavioral-regression-detection-stack-when-your-agent-test-suite-is-green-but-your-users-are-not.md) — harness-level regression is invisible to unit tests
