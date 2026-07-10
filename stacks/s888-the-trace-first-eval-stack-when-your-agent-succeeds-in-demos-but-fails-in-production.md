# S-888 · The Trace-First Eval Stack — When Your Agent Succeeds in Demos but Fails in Production

Your agent nails every demo. It answers the right questions, calls the right tools, completes the task. Then it goes to production and quietly breaks: wrong URLs in tool calls, localhost references in a cloud environment, CVEs hallucinated as fiction. Your benchmark says 94% — your users say something else. The Trace-First Eval Stack is the pattern for building an evaluation practice that catches production failures before they compound.

## Forces

- **Benchmarks lie.** UC Berkeley found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) can be gamed to near-perfect scores with trivial exploits — one team gamed 890 tasks with a single character change. Standard benchmark scores have decoupled from real production reliability. (Zylos Research, 2026 — [source](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/))
- **The research-practice gap is quantified.** A survey of 27 AI product companies found 63% report low confidence in whether model updates actually improve their products. AlphaEval (GAIR-NLP, April 2026) tested the best production configuration — Claude Code + Opus 4.6 — and achieved only 64.41/100 on real commercial tasks. The best scaffolding for the same model scored 11 points higher than the worst. (AlphaEval, arXiv:2604.12162 — [source](https://arxiv.org/abs/2604.12162))
- **Most eval failures are system-level, not model-level.** An HN practitioner's benchmark test suite surfaced broken URLs dropping scores to 22, localhost calls stuck at 46, real CVEs flagged as hallucinations, and Reddit blocking requests. None of these are model quality issues — all are system integration failures invisible to model-centric evaluation. (colinfly, HN, 2026 — [source](https://news.ycombinator.com/item?id=47416033))
- **pass@1 hides brittleness.** An agent that passes 88% of tasks on the first attempt can succeed on only 20% of tasks when run 8 times consistently — the variance is concentrated, not distributed. Leaderboards reporting pass@1 alone hide agents that are unreliable at scale. (AI Evals, 2025 — [source](https://www.aievals.co/learn/agentic-evals/pass-k-and-consistency))

## The Move

Build evaluation into three orthogonal layers, run at all three before every deploy, and wire every metric back to a trace so failures are debugged, not guessed.

### Layer 1 — End-to-End (Did the task actually succeed?)

- Run agents against a golden dataset of real production inputs with known correct outputs, curated by subject-matter experts
- Evaluate with deterministic checks (exact match, schema validation) where possible; use LLM-as-judge for subjective qualities with a structured rubric
- Report pass@k: run each task k times, report the fraction where at least one attempt succeeds. Single-run pass@1 is insufficient for production
- Capture partial credit: an agent that completes 80% of a multi-step task is meaningfully better than one that fails immediately

### Layer 2 — Trajectory-Level (Was the path efficient and correct?)

- Track step count, tool call counts, and retry loops per task — right answers that take 47 steps still fail in latency-sensitive production
- Measure tool call accuracy (did it invoke the right tool with correct arguments?) and plan adherence (did it follow the planned decomposition?)
- Use a trajectory evaluator: the inputs are a prompt and tools; the output is the full list of tool calls — compare against expected call sequence

### Layer 3 — Component-Level (Which specific span caused the failure?)

- Trace every LLM call, tool invocation, and reasoning step; attach metric scores to their originating spans
- Instrument retrieval quality (did the right context get fetched?), sub-agent handoffs, and intermediate reasoning steps independently
- For tools: measure argument correctness, timeout rate, and external dependency health (URLs alive, API credentials valid, rate limits respected)

### The Eval Data Pipeline

- Start with 50 high-quality human-curated (input, expected output) pairs — sufficient for statistical significance in a well-designed eval
- Amplify with synthetic data: generate test cases from your documentation and real production logs using an LLM, then have SMEs verify the seed cases
- Version your golden dataset like code; track regressions across model, prompt, and scaffolding changes
- Run evals in CI before every deploy; gate on a minimum score threshold per metric category

### Choose the Right Grader Per Metric

- **Deterministic graders** (regex, JSON schema, exact string match): tool call format, argument types, output schema
- **LLM-as-judge** (calibrated against human experts): answer relevance, reasoning quality, plan quality, safety
- **Human review** (judicious, reserved for validation): new eval categories, edge cases, safety-critical outputs
- Never ask one LLM to grade everything at once — grade each dimension separately with isolated calls

## Evidence

- **Survey + Benchmark (Primary):** 63% of 27 AI product companies report low confidence in model update impact; AlphaEval evaluates 94 tasks from 7 companies across 6 O\*NET domains, finding the best production configuration scores 64.41/100 with an 11-point spread between scaffoldings of the same model. — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162) and [zylos.ai](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **HN Practitioner (Primary):** Benchmark-style eval failed with broken URLs (score: 22), localhost calls in cloud env (score: 46), hallucinated CVEs, and Reddit blocking — all system failures, not model failures. — [HN discussion](https://news.ycombinator.com/item?id=47416033)
- **Technical Guide (Primary):** Confident AI's eval taxonomy covers all 12 core metrics (task completion, step efficiency, argument correctness, tool correctness, plan adherence, reasoning quality, latency, cost, etc.) with three eval levels (end-to-end, trajectory, component) tied to trace spans. — [confident-ai.com](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **Open-Source (Primary):** AWS Labs agent-evaluation framework (368 stars, Apache 2.0) provides a generative AI-powered framework for testing virtual agents with tool usage validation, Docker-sandboxed execution, and multi-paradigm evaluation types (reference verification, formal logic, rubric-based, execution-based). — [github.com/awslabs/agent-evaluation](https://github.com/awslabs/agent-evaluation)
- **Metrics Analysis (Primary):** AI Evals analysis of pass@k vs pass@1 demonstrates that single-run scores hide agent brittleness — an agent with pass@1=0.88 can have pass@8=0.20, revealing concentrated failure across repeated attempts. — [aievals.co](https://www.aievals.co/learn/agentic-evals/pass-k-and-consistency)

## Gotchas

- **Evaluating model quality instead of system quality.** Benchmark scores measure the foundation model in isolation. The scaffold (prompt chaining, tool definitions, memory management, retry logic) can swing scores by 11+ points — test the full system, not the model
- **Single-run pass@1 as your only signal.** If your agent needs to be reliable at scale, run it k times and report consistency. An agent that passes 90% on attempt one but 40% consistently is not a 90% agent
- **LLM-as-judge without calibration.** Uncalibrated LLM judges reward verbose, confident-sounding outputs regardless of correctness. Always validate against human expert judgments before trusting the signal
- **Golden datasets that don't reflect production distribution.** A dataset of easy cases produces misleading scores. Include edge cases, adversarial inputs, and real failure modes from production logs
- **Tracing without metric attachment.** Full traces are useless if you can't map a low score back to the span that caused it. Instrument every component to emit metric scores tied to its trace span
