# S-859 · The Agent Evaluation Stack — When Your Agent Works in the Demo and Fails in Production

Your agent demo sings. Happy-path questions get perfect answers. You deploy. Within a week someone finds the failure mode the demo never surfaced, your LLM bill triples, and there's no audit trail to explain what happened. You need a real evaluation system before you ship again.

## Forces

- **Deterministic tests can't catch non-deterministic agents.** Unit tests assume X in → X out. Agents plan, call tools, branch, and compound errors across steps. 79% of multi-step agent failures are step repetitions or reasoning-action mismatches — not simple wrong answers. (RockB, "AI Agent Testing Guide 2026," May 2026 — https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)
- **pass@k hides reliability you can't afford to lose.** An agent that succeeds once in three tries scores 97% on pass@3 but only 34% on pass^3 (consistency). For any agent handling real money, health decisions, or customer data, pass^k is the metric. (Digital Applied, "Building an AI Agent Evaluation Pipeline: 2026 Methodology," June 2026 — https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)
- **Only half of teams actually run evals offline.** Per LangChain's 2026 State of AI Agents report, just 52.4% of teams run offline evaluations on test sets, and only 37.3% run online evals in production. 32% of organizations cite quality as the top barrier to agent deployment. (Mastra.ai citing LangChain report, June 2026 — https://mastra.ai/articles/ai-agent-evaluation)
- **You don't know what's failing until users tell you.** 90%+ of YC founders say the only way they know if agents are failing is by hearing customer complaints. Prompt changes get shipped hoping they fix problems without breaking something else. (Voker Launch HN, YC S24, 2025 — https://news.ycombinator.com/item?id=48109962)

## The Move

### 1. Define the eval anatomy first

Every evaluation has four parts: **tasks** (inputs + success criteria), **trials** (multiple runs per task to handle non-determinism), **graders** (scoring logic), and a **harness** (orchestration). Agents need all four. LangChain's report shows teams that skip any layer get false confidence. (Anthropic Engineering, "Demystifying Evals for AI Agents," Jan 2026 — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### 2. Use two grader classes, not one

**Code-based graders** are deterministic — check for valid JSON, exact field matches, function call signatures, code that compiles. Fast, cheap, no calibration needed. **Model-based graders (LLM-as-a-judge)** handle semantic quality: did the answer address intent, follow policy, use the right tone? They need calibration against 100+ human-labeled examples and a minimum Cohen's κ ≥ 0.6 vs. human reviewers before they're trustworthy. (Digital Applied, June 2026; LangChain, "LLM Evals: The Feedback Loop," 2026 — https://www.langchain.com/resources/llm-evals)

### 3. Build your golden dataset from real failures, not curated ones

Start with 20–50 tasks from actual failure cases in production or demo. Don't wait for hundreds of perfectly curated examples. Grow the set from production traces — tools like LangWatch ship agents with golden datasets and pass/fail evaluators for patterns like RAG, tool-use, and multi-agent pipelines. (GitHub: GiuseppeSp/awesome-langwatch-agents, June 2026 — https://github.com/GiuseppeSp/awesome-langwatch-agents) (Digital Applied, June 2026)

### 4. Gate CI on pass^k, not pass@k

Run evals in CI/CD on every PR. The 2026 MVI stack for small teams: **DeepEval** (open-source, pytest-native, code-first) or **Promptfoo** (CLI-first, free) for fast regression checks; **LangSmith** if you're already on LangChain; **Braintrust** for enterprise release gates with dataset + tracing. All support CI gates. At least 60–80% of successful teams' dev time goes to evaluation. (AgentMarketCap, "Building AI Agent Evals in CI/CD 2026," Apr 2026 — https://agentmarketcap.ai/blog/2026/04/10/building-ai-agent-evals-cicd-2026)

### 5. Run online evals in parallel with offline

Offline evals on test sets miss drift and real-world failure modes. Online evaluators capture live user interactions, catch unexpected edge cases, and enable continuous monitoring. One healthcare team deployed an online evaluator to flag potentially harmful advice before it reached users. Run both in parallel; they serve different purposes. (Humanloop, "LLM as a Judge," 2026 — https://humanloop.com/blog/llm-as-a-judge)

### 6. Monitor three production primitives: Intents, Corrections, Resolutions

Voker (YC S24) frames production agent analytics around three primitives: **Intent** (what the user wanted), **Correction** (where the user had to rephrase or redirect the agent mid-task), and **Resolution** (whether the intent was ultimately met). This gives teams conversational intelligence without digging through raw logs. Correlate these with token cost and latency per session. (Voker Launch HN, 2025 — https://news.ycombinator.com/item?id=48109962)

## Evidence

- **Engineering Blog:** Anthropic's "Demystifying Evals for AI Agents" defines the core vocabulary (task, trial, grader, harness) and breaks down grader types for coding, conversational, research, and computer-use agents. Authoritative framework for understanding what eval infrastructure should contain. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **Practitioner Methodology:** Digital Applied's 2026 pipeline guide surfaces the pass^k vs. pass@k gap concretely (97% vs. 34% for a 70%-per-trial agent), judge calibration requirements (100+ labeled examples, κ ≥ 0.6), and CI gating as the mechanism that makes evals actually ship. — https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology
- **Tooling Landscape:** AgentMarketCap's 2026 CI/CD guide maps the four dominant tooling approaches (DeepEval, LangSmith, Braintrust, Promptfoo) with tradeoffs for team size and monitoring needs. Cites Gartner prediction that 40% of agentic AI projects will be cancelled by 2027 due to inadequate risk controls. — https://agentmarketcap.ai/blog/2026/04/10/building-ai-agent-evals-cicd-2026
- **Real Incident Driver:** The HN thread on agent monitoring (triggered by DataTalks DB wipe by Claude Code and Replit agent deleting data during code freeze) shows the operational risk gap: no step-by-step visibility, untracked token usage, undetected risky outputs, no audit trail. AgentShield (mentioned in thread) and Voker both launched from these pain points. — https://news.ycombinator.com/item?id=47301395

## Gotchas

- **Scoring only the final output misses the trajectory.** Multi-agent regressions hide in sub-agents. Use span-level evaluation — check intermediate tool calls, reasoning steps, and context management alongside the final answer. (RockB, May 2026; LangChain)
- **An uncalibrated judge is worse than no judge.** A weak LLM-as-a-judge gives false confidence. Calibrate against a human gold set before trusting scores for high-stakes decisions. Without calibration, "it passed the eval" means nothing. (Digital Applied, June 2026)
- **Offline eval misses drift.** Your test set was representative in January. By June, real user behavior may have shifted. You need online monitoring to catch the gap. (Humanloop; Langfuse, "LLM Evaluation 101," Mar 2025 — https://langfuse.com/blog/2025-03-04-llm-evaluation-101-best-practices-and-challenges)
- **Eval data contamination is invisible.** If your eval set appears in your training corpus, your numbers are inflated and you don't know it. Decontaminate before claiming improvements. (FutureAGI, "Best LLM Evaluation Frameworks 2026" — https://futureagi.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **Pass^k requires multiple trials per task.** Single-trial evaluation is pass@1, which hides consistency. Budget for 3–5 trials per task to get a meaningful pass^k. Cost scales accordingly.
