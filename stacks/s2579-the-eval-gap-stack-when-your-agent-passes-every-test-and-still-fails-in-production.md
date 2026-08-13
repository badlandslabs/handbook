# S-2579 · The Eval Gap Stack — When Your Agent Passes Every Test and Still Fails in Production

Your agent crushes your test suite. All 200 evals green. You ship it. Two weeks later, users are getting subtly wrong answers, the agent is looping on edge cases, and you have no idea which prompt change broke it. You didn't test the wrong things — you tested in the wrong dimension. You measured whether the agent got the right answer, not whether it got it for the right reasons.

## Forces

- **Correct output masks unstable execution.** An agent that reaches the right answer via a broken or inefficient path will pass output-only scoring but fail silently in production when the input distribution shifts.
- **Agent errors compound across steps.** A bad tool call in step two corrupts step three, which corrupts step four. Single-prompt benchmarks miss this entirely.
- **Observability outpaced judgment.** According to LangChain's State of Agent Engineering survey (June 2026): 89% of organizations have implemented observability, but only 52% run offline evals and just 37% run online evals. Teams can see what agents do; they can't yet reliably judge whether it's good.
- **The benchmark problem.** Standard LLM benchmarks (BLEU, ROUGE) measure single-turn text similarity. Agents are non-deterministic, multi-step systems that make tool calls, maintain state, and recover from errors. No existing public benchmark covers all of this.
- **"Vibes-based eval" is epidemic.** Commenters on an HN Ask thread on AI evals (~5 months ago) noted that "the vast majority of AI companies evaluate models mostly based on vibes" — a real risk when deploying autonomous systems.

## The Move

Evaluate agents on **trajectory quality, not just outcome quality.** Combine at least two of the following layers, and make evaluation a continuous operational practice, not a pre-launch gate.

### Layer 1 — Run-Level (per-step)
Score each individual tool call and reasoning step:
- Did the agent call the right tool?
- Were the arguments correctly formatted?
- Did it recover from a bad intermediate result?
Frameworks: LangSmith trace analysis, Phoenix (arize), DeepEval unit-test-style per-call assertions.

### Layer 2 — Trajectory-Level (full workflow)
Score the entire execution path, not just the final output:
- Was the sequence of tool calls logical and efficient?
- Did the agent avoid unnecessary steps or loops?
- Did it reach the goal through a stable path, or was it lucky?
G-Eval (Microsoft) and other LLM-as-judge chains score trajectories with multi-criteria rubrics. Trajectory scoring catches the "right answer, wrong path" failure mode that kills production agents.

### Layer 3 — Thread-Level (multi-session, production)
Score behavior across sessions and over time:
- Does the agent handle nulls, Unicode names (O'Brien, José, 北京), empty fields, and concurrent requests?
- Do cost-per-task and latency stay within budget as input distribution shifts?
- Does quality degrade over the 30–60 day window that Deloitte found is the typical failure window for unmonitored production agents?
Tools: Langfuse production monitoring, Braintrust production evals, Promptfoo regression suites on CI.

### The Evaluation Stack in Practice
- **Golden dataset curation:** Build a representative test set from real production inputs. MIT MCP Intelligence's open eval harness uses 25 Q&A pairs with drift detection against LangSmith + local backends. Golden datasets are high-effort but give the most reliable offline signal.
- **LLM-as-judge with calibration:** Use a stronger model to score outputs. Calibrate against human annotations using Spearman correlation — uncalibrated judges suffer from position bias (preferring first or last options) and self-preference (favoring outputs similar to their own training distribution). MLflow, Braintrust, and DeepEval all support this with built-in calibration helpers.
- **Continuous over one-shot:** Teams that evaluate only at launch consistently see quality degrade within 30–60 days. Set up automated eval triggers on every significant prompt or scaffold change. Promptfoo, LangSmith, and GitHub Actions-based eval pipelines make this tractable.
- **Standardized benchmarks as a floor, not a ceiling:** SWE-bench Verified (coding agents, ~49–55% resolution rate for top agents as of 2025) and GAIA (general-purpose agents) give you a public baseline, but neither tests cost efficiency, multi-session memory coherence, or domain-specific edge cases. Use them to catch regressions; build custom evals for your actual use case.

## Evidence

- **HN Ask Thread:** "Ask HN: How are you testing AI agents before shipping to production?" — Practitioners report that most teams test hallucination and prompt injection but almost no one systematically tests edge case collapse (Unicode, nulls, concurrent requests) or long-horizon degradation before launch. Gartner predicted 40%+ of AI agent projects will fail by 2027. — https://news.ycombinator.com/item?id=47325105

- **LangChain State of Agent Engineering Survey (June 2026):** Found 89% of organizations have observability in place, but only 52% run offline evals on test sets and just 37% run online/production evals. Quote: "The tooling to see what agents are doing has outpaced the tooling to judge whether they're doing it well." — https://www.langchain.com/resources/agent-evals

- **InfoQ — Evaluating AI Agents in Practice (March 2026):** Article on hybrid evaluation pipelines covering trajectory analysis, LLM-as-judge scoring, tau-bench for customer service agents (retail + airline domains), and load testing. Key point: "Agents are systems, not models — evaluate them accordingly. Single-turn accuracy metrics don't capture how agents fail in multi-step scenarios." — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned

- **Braintrust AI Agent Evaluation Framework (Feb 2026):** Documents the trajectory-level vs. outcome-level eval distinction. Golden datasets + trajectory capture + rule + LLM-as-judge scoring + CI gates. Shows that "correct answers can mask unstable, inefficient, or risky execution paths." — https://www.braintrust.dev/articles/ai-agent-evaluation-framework

- **Sierra Research τ²-Bench (tau-bench successor, ~1,800 stars):** Benchmark for tool-agent-user interaction in real-world domains. Airline domain top scores: Claude 3.5 Sonnet (Oct 2024) at 46% on airline tasks, GPT-4o at 42% — demonstrating that even frontier models have significant room to improve on real-world tool-use scenarios. — https://github.com/sierra-research/tau2-bench

## Gotchas

- **LLM-as-judge is not self-certifying.** Judges exhibit position bias, self-preference, and verbosity bias. Always calibrate against a sample of human-annotated examples before trusting judge scores at scale.
- **Golden datasets go stale.** Production input distributions shift. A golden dataset built on last quarter's user queries will miss new failure modes. Budget for quarterly refresh cycles.
- **Offline evals don't catch online failures.** An agent can behave correctly on a static test set and still fail under real concurrency, rate limits, tool timeout cascades, or adversarial user inputs. Online/production evals catch what offline cannot.
- **Trajectory length and cost are first-class metrics.** An agent that gets the right answer in 47 tool calls instead of 3 has failed, even if the output is correct. Track tokens-per-task and cost-per-completion alongside accuracy.
- **Security and safety evals are often missing.** Prompt injection, PII leakage, and permission boundary violations are rarely caught by functional evals. Add red-teaming and policy-compliance checks as explicit eval criteria, not afterthoughts.
