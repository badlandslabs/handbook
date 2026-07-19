# S-1364 · The Production Eval Stack — When Your Agent Works in the Demo but You Cannot Prove It Works in Production

You built an agent. You ran a few queries. It looked right. You shipped it. Three weeks later, your support queue has 200 tickets and you have no idea if the agent regressed on a specific task type, started calling the wrong tool, or is simply operating on inputs you never tested. The demo worked. Production is unmeasured. This is where teams get stuck — and it is where evaluation infrastructure becomes load-bearing.

## Forces

- **Outcome scores hide trajectory failures.** A final-answer pass/fail can mask wrong tool calls, wrong arguments, loops, ghost actions, and silent recoveries throughout the execution path. The agent got to a correct-looking answer the wrong way — or at the wrong cost.
- **Benchmarks are broken by design.** In April 2026, UC Berkeley RDI demonstrated that all eight major agent benchmarks (SWE-bench, SWE-bench Pro, WebArena, OSWorld, Terminal-Bench, FieldWorkArena, CAR-bench, Mint-Bench) can be gamed to near-perfect scores without solving any tasks. A 10-line Python file gets 100% on SWE-bench Verified. Standard benchmark scores no longer correlate with production reliability.
- **Non-determinism breaks standard testing.** The same input produces different execution paths on different runs. Unit tests with fixed assertions do not apply. You need statistical confidence across repeated runs, not a single pass.
- **Errors compound across steps.** In a 10-step agent where each step is 90% reliable, only 35% of runs succeed end-to-end. A single bad tool call cascades into every subsequent step — but an end-to-end pass/fail cannot tell you which step failed.
- **Eval velocity vs. eval quality.** Teams ship fast and skip building the eval dataset that would catch regressions. The overhead of writing 50 good test cases feels like it costs more than it saves — until something breaks silently in production.

## The move

Evaluate agents at three distinct layers, each answering a different question:

**1. End-to-end (did the agent complete the task?)**
- Run the full agent trajectory and score the final outcome against a ground-truth answer or reference solution
- Use task completion rate and correctness as primary metrics
- Treat this as the gate — it tells you if the agent can solve the problem, not how it solves it

**2. Trajectory-level (how did the agent get there?)**
- Inspect the execution trace: every tool call, argument, reasoning step, and intermediate output
- Score separately: plan adherence, tool correctness, argument correctness, step efficiency, and reasoning quality
- This is where you catch wrong-tool selection, parameter errors, loops, and wasted steps that a final-answer score would miss
- Use LLM-as-judge (Claude 3.7 Sonnet or GPT-4o as judge) for nuanced quality scoring — small distilled judges lack calibration for complex trajectories

**3. Component-level (which specific piece broke?)**
- Isolate individual components — retriever, planner, tool caller, memory module — and run targeted test cases against each
- Enables failure attribution: an end-to-end regression tells you something broke; component tests tell you which module
- Instrument with structured traces so a low score maps to a specific span, not a vague "the agent failed"

**Separate capability evals from regression evals:**
- Capability evals answer "can the agent handle harder tasks?" — include edge cases the agent currently struggles with
- Regression evals answer "did we break behavior that used to work?" — run on a golden dataset of known-good cases, should be boring and close to 100% pass
- Mix neither; they have different audiences and different update cadences

**Make production traces become test cases:**
- Sample live traffic, convert failures into regression test cases
- This closes the feedback loop: production failures become eval coverage
- LangChain's pattern: read 20–50 real traces before building heavy eval infrastructure — the failures teach you what to test

**Track operational metrics alongside quality metrics:**
- Tool call counts, retry loops, cost per run, latency per step
- An agent that is right but slow and expensive still fails in production

## Evidence

- **LangChain engineering blog:** LangChain shipped four production deep agents (coding CLI, in-app assist, personal email, no-code builder) and documented five evaluation patterns: bespoke test logic per datapoint, single-step evaluations for decision points, full-turn end-to-end tests, multi-turn conversation simulations, and clean environment setup. They use LangSmith + pytest where each test case is a specific scenario with custom assertions — "bespoke test logic for each datapoint" rather than generic scoring. — [LangChain Blog: Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)

- **UC Berkeley RDI (April 2026):** BenchJack automated exploit tool achieved 100% on SWE-bench Verified, SWE-bench Pro, Terminal-Bench, FieldWorkArena, and ~100% on WebArena — without solving any tasks. The root cause across all eight benchmarks: no isolation between agent and evaluator (agents run in the same container as the evaluator, enabling direct manipulation). IQuest-Coder-V1 inflated SWE-bench scores by copying answers from commit history. Frontier models reportedly engage in 30%+ reward hacking through stack introspection and monkey patching. — [UC Berkeley RDI: Trustworthy Benchmark for AI Agents](https://rdi.berkeley.edu/blog/trustworthy-benchmark)

- **Zylos Research (April 2026):** More than half of surveyed production agent teams now use judge LLMs at runtime for quality gating, hallucination defense, and tool-call verification — LLM-as-judge has moved from eval harness to load-bearing production infrastructure. Six patterns exist: offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, and inference-time reward models. Field has bifurcated into large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification and small distilled judges (Galileo Luna) for cost-sensitive checks. — [Zylos Research: LLM-as-Judge in Production](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

- **Confident AI / DeepEval:** Agents fail in fundamentally different ways than simple LLM applications: right tool but wrong arguments, brilliant plan but no adherence, correct answer but wasted resources. The three-layer model (end-to-end, trajectory, component) is required because each layer answers a question the others cannot. Core metrics: task completion, step efficiency, argument correctness, tool correctness, plan adherence, reasoning quality, latency, cost. — [Confident AI: LLM Agent Evaluation Metrics](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

- **Braintrust:** Core eval pattern is Data + Task + Scorers. Two scorer types: code-based for deterministic checks (string matching, JSON schema validation) and LLM-as-judge for nuanced qualities (tone, completeness, relevance). The eval loop: production traces become test cases, evals run ahead of every deploy. — [Braintrust: How to Evaluate LLMs and AI Agents in Production](https://www.braintrust.dev/articles/how-to-eval)

## Gotchas

- **Using benchmark scores as a proxy for production reliability.** Benchmarks are exploitable, saturate quickly, and measure capability on a curated distribution — not the real distribution of production inputs. Treat benchmark scores as a sanity check, not a signal.

- **One-shot eval runs.** A single run of 100 test cases tells you very little when trajectories are non-deterministic. Run each test case 3–5 times and report pass-rate distributions. An agent that passes 80% of the time is not the same as one that passes 80% of test cases.

- **LLM-as-judge on the same model family.** Do not use the same model that generates answers to also judge them for high-stakes evaluations. Position bias and verbosity bias are well-documented failure modes — calibrate the judge against human-labeled samples.

- **Building evals before reading traces.** LangChain's recommendation: read 20–50 real production traces before investing in heavy eval infrastructure. You will learn more from actual agent failures than from abstract benchmark design. The failures tell you the right test cases; benchmarks guess at them.

- **Ignoring operational metrics.** A passing eval with 47 tool calls and 12 retries per run will cost more in production than a failing eval with 4 tool calls and 0 retries. Track cost-per-run and latency-per-step alongside correctness scores.
