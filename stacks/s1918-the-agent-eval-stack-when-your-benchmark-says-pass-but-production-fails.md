# S-1918 · The Agent Eval Stack — When Your Benchmark Says Pass but Production Fails

Your agent scores 78% on SWE-bench Verified. Your CI pipeline is green. You ship. Then in production, you discover the agent achieves 23% success across eight runs, corrupts data silently, and loops on edge cases your benchmark never contained. The benchmark didn't lie — it just measured the wrong thing.

## Forces

- **Benchmarks optimize for capability, not reliability** — SWE-bench, GAIA, and WebArena measure what an agent *can* do, not how often it *will* do it under real conditions. Benchmark scores correlate weakly with production adoption (ρ=0.05 across 50 agents across 10 workload categories).
- **Trajectory quality is invisible to output-only evaluation** — A correct answer can mask a dangerous execution path: unnecessary API calls, policy violations, or fragile tool-use sequences that will break under distribution shift.
- **The observability-eval gap is massive** — 89% of organizations have implemented observability, but only 52% run offline evals on test sets and just 37% run online evals in production. Teams can see what agents do but cannot judge whether it's right.
- **LLM outputs resist deterministic testing** — The same input can produce multiple valid responses. Exact-match assertions fail. Unit-testing culture from traditional software breaks down.

## The Move

Build a **three-level eval architecture** that evaluates the reasoning path, not just the outcome.

### 1. Separate trajectory evaluation from outcome evaluation

- **Outcome metrics** (task completion, accuracy, error rate) are cheap to compute and sufficient for initial validation and continuous monitoring. Run these on every commit.
- **Trajectory metrics** (tool-call sequence, intermediate reasoning quality, recovery behavior) require more compute but provide superior interpretability for debugging failures and validating high-stakes decisions. Run selectively on test suites and regression scenarios.

> "If you only score the final output, your agentic systems may look healthier than they are." — LangChain Agent Evals documentation (June 2026)

### 2. Layer the eval stack from unit to end-to-end

| Layer | What it tests | When to run |
|---|---|---|
| **Unit tests** | Deterministic components: tool implementations, parsing logic, routing functions, prompt templates | Every commit (fast) |
| **Trajectory evaluation** | Full agent run: tool-call sequence, intermediate reasoning, failure recovery | Test suite + regression |
| **LLM-as-judge** | End-to-end output quality: tone, trust, contextual appropriateness | Offline eval + production sampling |
| **Production monitoring** | Real-traffic scoring, behavioral drift detection, regression alerts | Continuous |

### 3. Calibrate LLM-as-judge rigorously

- Target **≥0.80 Spearman correlation** with human judgment before deploying the judge.
- Use **reference grounding prompts** with known-good and known-bad examples.
- Acknowledge judge biases: **verbosity bias** (prefers longer outputs), **position bias** (prefers first option in comparisons), **self-preference bias** (prefers outputs similar to the judge's own style).
- Build **rubrics with 3 tiers**: 7 dimensions → 25 sub-dimensions → 130 specific items, as reported by Galileo AI's evaluation framework.

### 4. Select benchmarks by domain match

| Benchmark | Focus | Best for |
|---|---|---|
| **SWE-bench Verified** | Python bug-fixing from real GitHub issues | Code agents |
| **GAIA** | Multi-step reasoning + tool use | General-purpose agents |
| **WebArena** | Web automation on live sites | Browser agents |
| **TAU-bench** | Policy-compliant tool use | Customer service / compliance agents |
| **AgentBench** | Multi-environment interaction | Cross-domain agents |

Expect a **20–40 percentage point drop** from public benchmark scores to your own task distribution. This gap comes from task distribution shift, environment differences, and prompt sensitivity.

### 5. Integrate evals into CI/CD with sampling

- Run full eval suites on commit for regression detection.
- Use **commit triggers** for modified agent code, **scheduled triggers** weekly, and **event-driven triggers** on production anomalies.
- Sample production traffic for online evals — 5–10% of runs with automatic scoring — rather than evaluating everything (cost prohibitive) or nothing (you go blind).

### 6. Build private eval datasets from production failures

The highest-signal test cases come from production failures, not synthetic generation. When an agent fails in production, write a deterministic test case from that failure before fixing the agent. This creates a regression suite that over time matches your actual distribution.

## Evidence

- **Survey:** LangChain's State of Agent Engineering (June 2026, n=1,340 practitioners) found 89% of organizations have implemented observability but only 52% run offline evals and 37% run online evals. 32% cite quality as the top production barrier, while cost concerns dropped. 57% now have agents in production (up from 51% the prior year). — [langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)

- **Benchmark analysis:** AgentPulse (arXiv:2604.24038, analyzing 50 agents across 10 workload categories using 18 real-time signals) found that benchmark performance has near-zero correlation with production adoption (Spearman ρ=0.05). Public benchmarks measure capability, not reliability or developer preference. — [arxiv.org/abs/2604.24038](https://arxiv.org/abs/2604.24038)

- **Benchmark-to-production gap:** OpenLegion's analysis of benchmark methodology reports a consistent 20–40 percentage point drop from public benchmark scores to real-world task distributions, driven by task distribution shift (15–25 pp), environment differences (5–10 pp), and prompt sensitivity (5 pp). Public benchmarks serve for coarse model shortlisting and regression detection only. — [openlegion.ai/en/learn/ai-agent-benchmarks](https://www.openlegion.ai/en/learn/ai-agent-benchmarks)

- **LLM-as-judge methodology:** Zylos Research (2026-05-26) documents calibration protocols for LLM-as-judge deployment, noting the industry has moved from "ask GPT-4 if this response is good" to disciplined evaluation with reference grounding, bias taxonomies (verbosity, position, self-preference), and rubric engineering standards. — [zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/)

- **Eval framework:** Galileo AI's agent evaluation framework (July 2026) prescribes the 3-tier rubric structure (7→25→130 dimensions) and recommends CI/CD integration with commit, scheduled, and event-driven triggers. — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Production eval patterns:** InfoQ (March 2026) documents hybrid evaluation as "non-negotiable" — automated scoring for repeatability, human judgment for tone and contextual appropriateness — and emphasizes that operational constraints (latency, cost per task, token efficiency, policy compliance) are first-class evaluation targets. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **Output-only evaluation is a false signal** — A correct final answer can hide a trajectory full of unnecessary tool calls, policy violations, or fragile assumptions that will fail on next quarter's data.
- **Public benchmark scores ≠ production performance** — Benchmark-to-production drops of 20–40 pp are routine. Use benchmarks for regression detection and coarse shortlisting, not for shipping confidence.
- **LLM-as-judge has systematic biases** — Verbosity bias, position bias, and self-preference bias are well-documented. Without calibration against human judgment, the judge can mislead you into preferring worse outputs.
- **Synthetic test cases drift from production distribution** — Over time, the eval suite becomes a proxy for the benchmark it was built from rather than the actual user distribution. Refresh test cases from production failures to keep signal current.
- **The eval frequency problem** — Running full trajectory evaluation on every commit is computationally expensive. Budget for eval infrastructure as a first-class concern — LangChain's O' Reilly report notes "five is impossible without trace-level evals on every handoff" when building multi-agent systems.
