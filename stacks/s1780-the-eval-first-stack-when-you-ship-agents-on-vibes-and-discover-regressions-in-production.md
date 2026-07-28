# S-1780 · The Eval-First Stack

Your agent ships. It passed every demo. Three weeks later, a prompt tweak to the ordering flow quietly breaks the customer-support agent — no one notices until tickets spike in week five. You have no regression suite, no baseline scores, and no idea when quality degraded or why. This is the eval debt failure: agent teams that skip evaluation infrastructure pay for it in silent regressions, missed failure modes, and the inability to distinguish improvement from drift.

## Forces

- **Agents fail differently than software** — non-deterministic outputs mean identical inputs produce different results, so traditional exact-match assertions don't work and failure spans multiple LLM calls and tool decisions
- **Benchmarks don't predict production behavior** — GAIA, τ-bench, and AgentBench measure capabilities, not reliability; your agent scoring 70% on a benchmark tells you nothing about whether it will fail gracefully on your specific tool calls
- **The feedback loop is broken by default** — teams ship on vibes, discover regressions only when users complain, and have no data to debug why a tool call sequence diverged three steps in
- **Evaluation tooling has fragmented into three layers** — benchmarks (capability measurement), eval harnesses (test-time scoring), and observability platforms (production monitoring) — and most teams only use one, missing the other two
- **LLM-as-judge is load-bearing but misunderstood** — 57% of production teams use a judge LLM at runtime, but the pattern has six distinct variants with radically different latency, cost, and failure profiles

## The move

Build a three-layer eval stack: **captured traces → scored test cases → CI-gated regression suite**.

### Layer 1 — Trace capture (always-on)

- Instrument every agent run with structured traces: prompt, model, tool calls, tool outputs, final response, latency, and token cost
- Use OpenTelemetry-native tooling (Logfire, Langfuse, Agenta) so traces survive beyond one session and feed into standard observability infrastructure
- Capture the **trajectory**, not just the output — where the agent reasoned correctly, where it called a wrong tool, where it recovered vs. where it spiraled

### Layer 2 — Define what "good" means (once per agent)

- **Code-based scorers** for deterministic checks: did the agent call the right API endpoint? Did the output conform to schema? Did it complete the stated task?
- **LLM-as-judge scorers** for nuanced qualities: correctness, relevance, groundedness (did it hallucinate?), safety, and tone — evaluated per-step and end-to-end
- **Synthetic personas** for CI: generate edge-case test cases automatically; refine with actual user feedback in production
- Choose small distilled judges (Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) for high-throughput inline checking — 97% cost reduction vs. GPT-4o at 0.88–0.95 accuracy; reserve large proprietary judges (Claude 3.7 Sonnet, GPT-4o) for high-stakes verification gates

### Layer 3 — CI-gated regression suite

- Convert passing production traces into permanent regression tests; convert failing traces into test cases that reproduce the bug
- Run evals on every pull request — block merges when quality scores fall below configurable thresholds, same as code coverage or type checking
- Track operating envelopes (cost per task, latency, step/token budgets) alongside quality scores — a "green" eval that costs 10× more is not a win

## Evidence

- **Survey:** A McKinsey survey found 48% of leading genAI organizations cite risk and accountability as impediments to value realization — validating that eval debt is a systemic blocker, not an edge case — https://arxiv.org/html/2507.21504v1
- **Market data:** Gartner predicts 40% of agentic AI projects will be cancelled by 2027 due to reliability concerns, with the AI observability market reaching $1.1B in 2025 — https://www.getmaxim.ai/articles/top-5-tools-to-evaluate-and-observe-ai-agents-in-2025/
- **Production adoption:** Over 57% of surveyed production agent teams now use LLM-as-judge at runtime; small distilled judges deliver 97% cost reduction vs. frontier models at near-equivalent accuracy — https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/
- **Benchmark gap:** τ-bench leaderboard shows GPT-5.5 at 46.4% pass rate on real-world multi-turn tool-calling tasks — even frontier models fail more than half the time, confirming that benchmark scores don't translate directly to production reliability — https://taubench.com/
- **CI pattern:** Braintrust's GitHub Action integration gates pull requests on eval scores, demonstrating eval-as-engineering-gate in practice — teams block merges when quality thresholds are violated — https://www.braintrust.dev/
- **Tooling ecosystem:** MLflow v3.0+ (experiment tracing + LLM judges), TruLens (pluggable feedback functions + OpenTelemetry), LangSmith (trace ingestion + LLM-as-judge calibration), DeepEval (open-source eval harness with CI integration), and Logfire (Pydantic-native AI observability) — representing three distinct layers of the eval stack — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/

## Gotchas

- **Don't evaluate only the final output** — a correct answer from a broken trajectory is a false positive; evaluate each step (tool calls, argument construction, handoffs) independently and as part of the whole
- **LLM-as-judge has six distinct patterns** — offline batch eval, online runtime verifier, self-consistency loops, Reflexion/reflection, constitutional AI/RLAIF, and inference-time reward models — using the wrong one for your use case creates either a bottleneck or a quality blind spot
- **Human review is irreplaceable for calibration** — sample traces for human rubric scoring to catch "metric green, user red" failures where the judge and the user disagree on quality; use it to calibrate the judge, not to replace broad automated coverage
- **Benchmarks measure capability, not reliability** — GAIA and τ-bench tell you what an agent *can* do; they say nothing about whether your specific agent *will* do it reliably in production under your particular tool environment and policy constraints
- **Track cost and latency alongside quality** — a regression suite that scores 95% but doubles your per-task cost or adds 3 seconds of latency is not an improvement; operating envelope violations are eval failures too
