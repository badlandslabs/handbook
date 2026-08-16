# S-2747 · The Agent Trajectory Eval Stack — When Your Agent Succeeds But You Can't Prove It

You have an agent in production. You have traces. You have a dashboard. But when someone asks "is it actually working?" you have no defensible answer. Output-only evaluation misses the most common failure modes.

## Forces

- **Traces ≠ evals.** Most teams instrument their agents but never convert those traces into test cases — the LangChain State of Agent Engineering survey (late 2025, n=1,340) found 89% had some observability, but only 52.4% ran offline evals and 37.3% ran online evals.
- **Output scores lie.** The most damaging agent failures — broken URLs in tool calls, environment mismatches, loops, wrong tool selection — don't appear in the final answer. One practitioner's small test suite scored 22% due to broken URLs and localhost calls in a cloud environment, not model quality.
- **The adoption gap costs.** Teams that can inspect a bad run after the fact still ship the same failure twice because no test captures it.
- **Judgment is fragile.** LLM-as-a-judge works at scale but drifts without human calibration — overconfident scores are worse than no scores.
- **Eval tooling is fragmented.** promptfoo, DeepEval, LangSmith, Arize, and custom harnesses all do different slices of the problem; no single tool covers the full loop.

## The Move

Build a **three-layer eval system** with a **trace-to-test flywheel** that closes the loop between production failures and new test cases.

### 1. Layer your evals by what they catch

| Layer | What it catches | Tooling examples |
|---|---|---|
| **Golden datasets + deterministic checks** | Tool call order, argument validity, loop detection, invariants, dead URLs | promptfoo YAML, DeepEval `@assert` tests, custom rule engines |
| **LLM-as-a-judge on traces** | Task completion, answer quality, trajectory reasonableness | Schema-Guided Reasoning (SGR) judges, Claude judge, LangSmith evaluators |
| **Production monitoring + sampling** | Live distribution, edge cases, regression | Langfuse, Arize Phoenix, OpenTelemetry spans, Lucidic graph traces |

Deterministic checks run fast and reliably in CI; LLM judges catch semantic failures that rules can't encode; production monitoring finds what neither offline layer anticipated.

### 2. Instrument the trace-to-test flywheel

```
Production trace → label failures → cluster by pattern → dedupe → 
versioned golden dataset → CI regression gate → monitoring →
new production trace (loop)
```

Capture failing production traces, define a golden dataset record (input + expected behavior + scoring method), score it with the eval harness, gate CI. The flywheel ensures that every real failure produces a regression test before the next deploy.

### 3. Track operating envelope alongside quality

In the same traces you use for quality metrics, record: cost per run, latency per step, total steps, token count, tool call count. A trajectory that scores well but consumes 10x the expected tokens or loops 40 times is a real failure — it just won't show up in answer-quality metrics alone.

### 4. Calibrate judges before trusting them

Run LLM-as-judge outputs against a small human-labeled sample (20–50 cases). Measure agreement. Adjust the judge rubric or switch to deterministic checks for the cases where the judge is wrong. An uncalibrated judge produces confident wrong scores that are harder to debug than no scores.

### 5. Version and gate

Keep the golden dataset in the repo with your agent code. Every prompt change, model swap, or tool modification runs the full eval suite. Block the PR if task success drops below threshold or operating cost/latency regresses. This is the mechanism that converts "we know it failed" into "we won't ship that again."

## Evidence

- **HN practitioner post:** Ran a benchmark-style eval on an agent; score dropped to 22% not because of model quality issues but because of broken URLs in tool calls and the agent calling `localhost` in a cloud environment. System-level failures dominated — https://news.ycombinator.com/item?id=47416033
- **LangChain State of Agent Engineering survey (2025, n=1,340):** 89% of agent teams have some observability; 57.3% have agents in production; only 52.4% run offline evals and 37.3% run online evals. When asked what blocks production, 32% named quality and 20% named latency — https://www.langchain.com/state-of-agent-engineering
- **Langfuse eval guide:** Evaluates agents on four dimensions — trajectory (step count, loops, correct ordering), tool use (correct tool selected, argument validity), task completion (goal achieved), and multi-turn quality (consistency across conversation turns). Each dimension is independent; a per-dimension score tells you where the agent failed; an aggregate score only tells you it got worse — https://langfuse.com/resources/engineering/ai-agent-evaluation
- **NVIDIA Technical Blog (2026):** Distinguishes agent evaluation from model evaluation: model eval uses static benchmarks (MMLU, GSM8K) and asks "is the engine powerful enough?"; agent eval uses trajectory-based assessment (GAIA, SWE-bench, WebArena) and asks "can this system execute multi-step workflows?" — https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation
- **Microsoft Multi-agent Reference Architecture:** Multi-agent systems introduce path optimization (agents may reach correct solutions inefficiently), error propagation (upstream failures cascade), emergent behavior from collective interactions, and non-deterministic outputs. Each requires dedicated eval strategy — https://github.com/microsoft/multi-agent-reference-architecture
- **Open-source harness (praveenpke/agent-eval-harness):** Golden datasets → trajectory capture → rule + LLM-as-judge scoring → CI gate → interactive dashboard. Deterministic heuristic judge for CI without API keys — https://github.com/praveenpke/agent-eval-harness
- **TribeAI/claude-evals:** Production eval framework for Claude Agent SDK with 50-case golden dataset, native SDK hooks, and one-command model comparison — https://github.com/TribeAI/claude-evals
- **Confident AI eval guide:** Hybrid eval stack: automated evals (goldens, CI, LLM-as-judge on traces) for fast regression signal, production monitoring for live distribution, human review for rubric calibration, user feedback to convert complaints into new test cases — https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide

## Gotchas

- **Output-only eval misses the majority of agent failures.** Broken tool arguments, environment mismatches, loops, and wrong tool selection are invisible to answer-quality scoring.
- **Golden datasets go stale.** If they don't reflect real usage distribution, evals pass on synthetic traffic while production fails on real inputs. Feed production failures back into the dataset continuously.
- **LLM-as-judge without calibration produces overconfident wrong scores.** Run human-labeled samples through first; adjust rubric before scaling.
- **A versioned dataset in CI is useless if nobody acts on it.** Define the threshold and the process: who reviews, what exceptions are allowed, what the rollback looks like.
- **Step count and cost are first-class signals, not secondary metrics.** A task-success-passing agent that loops 40 times or costs 10x budget is a production failure — instrument and alert on it.
