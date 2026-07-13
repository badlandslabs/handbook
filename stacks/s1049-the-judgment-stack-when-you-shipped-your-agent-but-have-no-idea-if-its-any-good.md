# S-1049 · The Judgment Stack — When You Shipped Your Agent But Have No Idea If It's Any Good

Your agent is in production. It is returning responses. You have no systematic way to know if those responses are correct, safe, or getting better or worse. You are not alone: LangChain's 2026 State of Agent Engineering survey found that only **52.4%** of teams run offline evaluations, and just **37.3%** run online ones — meaning nearly half of all deployed agents operate with no evaluation infrastructure at all. The teams that do evaluate well share a common pattern: they do not try to test everything. They build a judgment stack.

## Forces

- **An agent's quality is not a number.** Unlike a deterministic function, an agent produces variable outputs. Scoring it requires a reference point, a rubric, and a scorer — and all three introduce their own drift.
- **Evaluating every response is economically impossible.** LLM-as-judge on 100% of production traffic can cost more than the agent itself. Sampling is necessary, but sampling creates statistical uncertainty about when failures began.
- **The benchmark ≠ the production distribution.** SWE-bench Verified and GAIA tell you how your coding agent performs on canonical tasks. They tell you nothing about whether your customer-support agent handles your specific edge cases, and those edge cases are where you lose users.
- **Evaluation has a shelf life.** A grader prompt that correlated 0.90 with human judgment six months ago may correlate 0.65 today — the model behind the grader may have changed, the production distribution may have shifted, or the task itself evolved. Without re-calibration, your eval infrastructure slowly lies to you.

## The Move

Build a three-layer judgment stack: **reasoning eval** (is the plan right?), **action eval** (did the tool calls fire correctly?), and **outcome eval** (did it accomplish the goal?). Use LLM-as-judge for reasoning and outcome, structured logging for actions. Gate CI/CD on offline eval results, and run continuous sampling in production to catch drift. Calibrate your judge against human annotation quarterly.

### The three evaluation layers

1. **Reasoning layer — plan quality.** Does the agent's plan logically decompose the task? Is it complete before acting? A plan with a hallucinated step produces a confident failure. Evaluate this before any action fires.
2. **Action layer — tool correctness.** Did the agent call the right tool, with the right arguments, in the right order? Log every tool call with its input, output, and latency. This is the most automatable layer — use structured assertions, not LLM judges.
3. **Outcome layer — goal completion.** Did the agent satisfy the user's intent? This is the slowest to evaluate and the most expensive. Use LLM-as-judge here, but with an explicit rubric that requires the judge to cite evidence before scoring.

### The four production metrics that actually predict failures

Teams on r/LangChain who have run agents in production converge on four metrics that catch most regressions before users notice:

- **Latency p99** — not average latency. p99 catches when specific prompts trigger pathological token generation. Alert threshold: 2× baseline.
- **Quality sampling** — run evaluators on a sampled percentage of traffic (5–20%), not every request. Automated judges check hallucination, instruction adherence, and factual accuracy. This catches drift without burning budget.
- **Cost per request by feature** — token costs vary by feature. A sudden spike in cost-per-request on the "search" feature usually means the agent is looping on search calls. Monitor at feature granularity.
- **Task completion rate** — binary: did the agent complete the stated task or not? This is the coarse alarm. When it drops, something is seriously wrong.

### Grader design principles

- **Require structured output.** Judge prompts must return JSON with fields for score, reasoning, and evidence. A numeric score without cited evidence is noise.
- **Calibrate against human annotation.** Target 0.80+ Spearman correlation with expert human judgment. Measure Cronbach's alpha across multiple independent runs to assess grader consistency.
- **Use a purpose-built small model for cost efficiency.** Running GPT-4o as an evaluator on every sample is expensive. Luna-2 and similar small models trained for hallucination detection can match large-model evaluator accuracy at a fraction of the cost.
- **Guard against judge drift.** Re-run the grader against a golden dataset quarterly. If the score diverges from the golden baseline by more than 5%, re-annotate and retune.

### CI/CD integration patterns

Braintrust's GitHub Action (`braintrustdata/eval-action`) is the most cited pattern in practitioner discussions. It runs evaluations on every pull request and posts results as PR comments showing improvements (🟢) and regressions (🔴) per scorer. Notion's documented case study: after moving from JSONL files to hundreds of criterion-specific datasets in Braintrust, they went from 3 issues triaged per day to 30 — a 10× improvement in failure visibility.

### The benchmark selection problem

Standard benchmarks have a relevance gap: they test canonical tasks, not your production distribution. Practical approach from practitioner consensus:

- Use **SWE-bench Verified** for coding agents (78% ceiling as of May 2026; Claude Sonnet 4.5 scores 0.772, leading the agentic coding leaderboard).
- Use **WebArena** for web-automation agents.
- Use **GAIA** for general-purpose assistants.
- Build a **custom test suite** covering your critical paths, edge cases, and adversarial inputs. This is the part no benchmark replaces. Start with 50–100 cases that have cost you users.

## Evidence

- **Survey report:** 52.4% of teams run offline evals; quality is the #1 production barrier per LangChain's State of Agent Engineering 2026 (survey of 1,340 practitioners, Nov–Dec 2025) — [https://www.langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)
- **Community writeup:** Layered evaluation framework (reasoning/action/execution) with four production metrics (p99 latency, quality sampling, cost-per-request, task completion) from a practitioner on r/LangChain — [https://www.reddit.com/r/LangChain/comments/1q5rbs9](https://www.reddit.com/r/LangChain/comments/1q5rbs9) and [https://www.reddit.com/r/LangChain/comments/1qv0mmr](https://www.reddit.com/r/LangChain/comments/1qv0mmr)
- **Industry analysis:** Braintrust CI/CD integration, judge calibration targeting 0.80+ Spearman correlation, Luna-2 SLM for cost-efficient hallucination detection, Notion 10× issue visibility improvement — [https://www.augmentcode.com/tools/best-ai-agent-evaluation-tools](https://www.augmentcode.com/tools/best-ai-agent-evaluation-tools)
- **Benchmark data:** SWE-bench Verified reached 78% pass rate by May 2026 (up from 13% in early 2024); Claude Sonnet 4.5 leads at 0.772 — [https://presenc.ai/research/coding-agent-benchmarks-2026](https://presenc.ai/research/coding-agent-benchmarks-2026)
- **Analyst projection:** Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation and monitoring — [https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)

## Gotchas

- **Evaluating only the final answer is evaluating the wrong thing.** An agent that scores 92% on final-answer accuracy may have failed on step 3 of a 5-step task and recovered by coincidence. The failure mode was real; the score missed it. You need trajectory metrics for debugging and outcome metrics for validation.
- **A golden dataset without maintenance is a decaying asset.** Production distributions shift. A test set that reflected real inputs six months ago may now contain 30% out-of-distribution cases. Schedule quarterly re-annotation of at least your top-failure cases.
- **Correlation ≠ causation in judge feedback.** An LLM-as-judge that consistently rates your agent highly on politeness when your agent is actually failing on correctness is not a trustworthy signal — it is a reflection of the judge's own biases and training distribution. Always validate grader scores against human expert annotation before trusting them.
- **Pass@1 is not your reliability number.** 75% per-trial reliability = 42% reliability across 3 sequential steps. If your agent needs 5 steps and each has 90% reliability, your end-to-end success rate is ~59%. Plan for compounding failure.
