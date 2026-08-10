# S-2438 · The Agent Eval Stack — When Your Passing Suite Hides a 58% Reliability Collapse

Your eval suite says 74% pass-rate. Your users say the agent is broken. Both are right. Traditional LLM evaluation — single-turn accuracy on curated datasets — measures the wrong thing. Agents are systems: they plan, call tools, recover, and accumulate cost at every step. Eval that ignores the trajectory will let you ship agents that reach correct answers via hallucinated tool calls, 40-step retry loops, and silent context corruption. This is the eval stack that actually catches what matters.

## Forces

- **Agents fail non-deterministically.** The same task may work today and fail tomorrow via a different trajectory — a property no static test suite captures unless you run multiple trials.
- **Output-only scoring misses terrible paths.** An agent that hallucinates a tool call and happens to get useful data still passes if the final answer looks right. Trajectory quality is invisible to answer-only grading.
- **Eval suites converge on what works.** The natural tendency is to add passing cases until the pass-rate looks acceptable, then ship. The untested cases are exactly where production exposes you.
- **Production inputs break lab assumptions.** Real users submit ambiguous requests, trigger API errors, and hit edge cases your curated dataset never covered — the 37% lab-to-production gap.

## The move

Separate **what** you evaluate (scope) from **how** you evaluate it (methodology), and run at least one layer of trajectory-level checks alongside output checks.

**Three evaluation scopes — all three needed for agents:**

- **End-to-end (black-box):** Input → final output only. Fast. Catches whether the agent got the right answer. Misses whether it got there correctly.
- **Action-layer (tool-call):** Inspects tool call sequence, arguments, and ordering. Catches tool misuse, fabrication-before-lookup, and redundant calls. Requires trace instrumentation.
- **Reasoning-layer:** Evaluates the agent's planning, sub-goal decomposition, and error recovery. Most expensive. Catches strategic failures that only appear in complex tasks.

**Run multi-trial — single runs are misleading:**

Agents that achieve 60% success on a single run drop to ~25% across eight consecutive runs. Run each task 5–8 times and track pass-rate variance, not just pass/fail. Flag if any trial reaches the correct answer through a hallucinated tool call.

**Build a failure taxonomy mapped to evaluators:**

Rather than scoring "good" or "bad," classify failures into categories and assign targeted evaluators to each:

| Failure Class | What It Looks Like | Evaluator |
|---|---|---|
| Hallucination | Fabricates facts or citations not in retrieved context | groundedness check |
| Fabrication-before-lookup | Answers before calling required knowledge tool | tool-call validator |
| Tool misuse | Wrong tool, wrong arguments, wrong sequence | tool-call validator |
| Silent context corruption | Downstream tool returns malformed data; agent continues with garbage | inline schema check |
| Safety miscalibration | Responds confidently when it should abstain | rubric scorer with abstention criteria |
| Behavioral regression | Previously-passing case fails after prompt or model change | regression tracker on golden dataset |

**Golden dataset: real, not synthetic. 100–500 cases:**

Synthesized test cases encode your assumptions about what the agent should do — which means they can't catch failures from incorrect assumptions. Pull 100–500 real (anonymized) examples from production traffic with known correct outcomes. Mix in edge cases and adversarial inputs your current agent fails on. Reject cases that only test what already works.

**Production eval pipeline — three layers:**

1. **Inline verification (critical path, <50ms):** Structural checks on each step — tool call schema validation, required tool enforcement, output format validation. Catches failures before they compound.
2. **Trace analysis (offline, per-release):** Full transcript review. Score trajectory quality: number of steps, tool-call accuracy, error recovery attempts. Compare against golden dataset baseline.
3. **Async production evaluation (continuous):** Sample live traffic, score with LLM-as-judge, track drift over time. Catches failure modes that only appear under real conditions.

## Evidence

- **Engineering blog:** Anthropic's guide to building effective agents explicitly separates workflow (pre-defined paths) from agent (dynamic tool use and self-directed reasoning) — and notes that eval must match the system's complexity. Agents that reach correct answers through incorrect reasoning require trajectory-level evaluation. — [Anthropic: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **arXiv survey:** "AlphaEval" framework in the 2025 survey reverses the typical benchmark-first approach — starts from authentic production requirements and transforms them into executable automated evals. Argues that curated benchmarks "cannot capture the under-specification, implicit constraints, and domain expertise that characterize production work." — [arXiv:2507.21504, Evaluation and Benchmarking of LLM Agents: A Survey](https://arxiv.org/abs/2507.21504)
- **Industry guide (2026):** Reports that agents achieving 60% success on a single test run drop to 25% across 8 consecutive runs — a 58% reliability collapse invisible to single-run eval. Also documents the trajectory problem: agents reaching correct answers via hallucinated tool calls, 12-step retry loops, or redundant API calls all score "pass" on output-only grading. — [Jobs by Culture: AI Agent Evaluation Guide 2026](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)
- **HN discussion (July 2025, 128 pts):** Practitioner thread on production AI agents confirms evals as the primary differentiator between teams that iterate confidently and teams that ship blind. LLM-as-judge scored against human-annotated rubrics emerges as the most practical production approach for trajectory quality. — [Hacker News: Principles for Production AI Agents](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Output-only scoring is a false signal.** It tells you the agent sometimes gets lucky. It tells you nothing about whether it gets there correctly. Every team that skips trajectory scoring eventually ships an agent that reaches correct answers via hallucination.
- **Single-trial eval is a false signal.** Run each task 5–8 times before trusting the pass-rate. If variance is high across trials, the agent is not reliable — no matter what one good run showed.
- **Synthetic golden datasets encode your blindspots.** If your test cases reflect what you think the agent should do, they can't catch failures from incorrect assumptions. Real production cases surface the gaps synthetic data misses.
- **Model updates break evals silently.** A provider update can shift agent behavior without changing your eval suite's output format. Re-run the full golden dataset after any model or prompt change — not just the failing cases.
- **LLM-as-judge has a calibration problem.** Judges trained on different rubric styles disagree on the same outputs. Calibrate your judge against human annotations using Spearman correlation before trusting it to gate deployments.
