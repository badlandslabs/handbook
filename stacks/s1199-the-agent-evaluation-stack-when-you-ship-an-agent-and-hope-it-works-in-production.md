# S-1199 · The Agent Evaluation Stack — When You Ship an Agent and Hope It Works in Production

When your agent reaches for production, you discover that everything you knew about testing deterministic software is wrong. The agent hallucinates correct answers through incorrect reasoning paths, passes your golden dataset on Monday and silently degrades by Friday, and scores 100% on benchmarks while solving zero real problems. Evaluation is where agentic projects either earn reliability or become technical debt.

## Forces

- **Benchmarks are gamed.** UC Berkeley researchers found that all eight prominent AI agent benchmarks can be exploited to achieve near-perfect scores without solving any underlying task — one team gamed 890 tasks with a single-character change. SWE-bench Verified has saturated at 93.9% in 2026, yet Microsoft research (SWE-Bench-Mutated / CAIN26) shows public benchmark scores can overestimate real-world coding agent performance by >50%. Static success-rate scores tell you almost nothing about whether the agent is reliable, safe, or cost-efficient.
- **The golden dataset lies to you.** A static test set gives you a stable floor, not a live picture. Production distributions shift, user behavior changes, upstream systems update. If you only evaluate pre-launch, you won't catch the 30–60 day quality degradation that teams consistently report. Golden datasets catch regressions; they don't track drift.
- **LLM-as-judge has serious bias problems.** Position bias (earlier responses win), length bias (longer outputs score higher), and agreeableness bias (judges over-accept without critical evaluation) can exceed 50% error rates in naive LLM-evaluator deployments. Yet most teams reach for it first because it's fast.
- **Silent failures are the real danger.** An agent can produce a correct output through an incorrect process — citing last year's inventory report while reporting this year's numbers. The result looks right; the execution failed. Trajectory-level evaluation (not just output evaluation) is required to catch this.
- **Operational constraints are first-class citizens.** Latency, cost per task, token efficiency, tool reliability, and policy compliance determine whether a technically capable agent is viable at enterprise scale. A correct agent that runs in 60 seconds when users expect 10 has failed. A correct agent that leaks PII has catastrophically failed.

## The move

**Build a multi-dimensional evaluation pipeline that targets behavior, not just outputs — continuously.**

### Retrieval / grounding layer
- **Context relevance** (>0.85) — are retrieved chunks actually relevant to the query?
- **Context recall** (>0.90) — did you retrieve all available relevant information?
- **Faithfulness score** (>0.95) — does the generated answer match the retrieved context, not the model's memory?

### Agent behavior layer
- **Task completion rate** — did the agent finish what was asked?
- **Tool call accuracy** — did it call the right tools with the right arguments?
- **Trajectory analysis** — was the reasoning path correct, or did the agent luck into the right answer via the wrong process?
- **Graceful recovery rate** — when a tool fails, does the agent recover or loop?
- **Cost per task** — track token spend per task to catch budget creep.

### Evaluation methodology stack
- **Programmatic assertions** for objective correctness (factual accuracy, tool call accuracy, RAG grounding) — high confidence, fast, automatable for regression testing.
- **LLM-as-judge with calibration** for subjective qualities (coherence, helpfulness, tone) — requires careful bias mitigation: randomized presentation order, multiple judges with majority voting, minority-veto for safety issues, explicit disclaimers in prompts.
- **Golden dataset from production traces** — sample real production failures, human-annotate the correct behavior, promote silver (synthetic) to gold via human-in-the-loop QA. Early examples do the heaviest calibration work; annotation lift is front-loaded.
- **Synthetic + adversarial generation** — use models to generate edge cases (typos, slang, out-of-domain inputs, multi-turn dependencies), but always calibrate synthetic items against human SME review for mission-critical scenarios.

### Continuous evaluation loop
- Run evals on every PR, not just pre-launch.
- Sample production traffic continuously and route edge cases to the eval pipeline.
- Set threshold alerts: if task completion drops 5%, cost-per-task spikes 20%, or PII-leak rate exceeds 0%, page the team.

### Safety + governance layer
- **Red-teaming** for adversarial inputs and prompt injection.
- **Permission boundary testing** — does the agent respect scopes? (The Replit agent deleting data during a code freeze is the canonical example of missing this.)
- **Human-in-the-loop gates** for high-risk actions (database writes, external API calls, anything with financial or legal impact).

## Evidence

- **HN thread / InfoQ article:** "Evaluations are vital for improving performance." Multiple practitioners confirm that teams "winging it without robust eval practices" are not to be trusted. The LLM-as-judge skepticism is strong — one researcher reports their internal experiment found LLMs "not good critics" at evaluating their own outputs. Hybrid evaluation combining automated scoring with human judgment is considered non-negotiable for production agents. — [Hacker News #44712315](https://news.ycombinator.com/item?id=44712315), [InfoQ: Evaluating AI Agents in Practice](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Google Cloud Blog:** Silent failures — "an agent can produce a correct output through an inefficient or incorrect process." Google's evaluation framework explicitly requires trajectory analysis, distinguishing between the result and the reasoning path that produced it. Their evaluation method stack (human review, LLM-as-judge, programmatic assertions, adversarial testing) maps directly to different Pillar 1 (UX/style/safety) and Pillar 2 (ethical/costly) concerns. — [Google Cloud: A Methodical Approach to Agent Evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **UC Berkeley / Zylos Research:** "All eight prominent AI agent benchmarks can be exploited to achieve near-perfect scores without solving any underlying task." Benchmark saturation at 93.9% on SWE-bench Verified while real-world coding agent performance differs by >50%. Teams must treat benchmark scores as a lower bound and supplement with in-distribution evaluation data built from production traces. — [Zylos Research: AI Agent Evaluation Beyond Task Completion](https://zylos.ai/research/2026-05-13-ai-agent-evaluation-benchmarking), [SWE-Bench-Mutated / CAIN26](https://arxiv.org/abs/2510.08996v4)
- **Gartner / Thinking Inc.:** "By 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps." Teams that evaluate pre-launch but stop monitoring post-launch consistently see quality degradation within 30–60 days. Deloitte analysis found continuous evaluation reduces production incidents by 67% vs. periodic evaluation. — [Thinking Inc.: AI Agent Evaluation in Production (2026 Guide)](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)
- **Hacker News / AgentShield:** Real incidents — Claude Code wiped a database, Replit agent deleted data during a code freeze. Common failure modes: no step-by-step execution visibility, surprise LLM bills from untracked token usage, risky outputs going undetected, no audit trail for post-mortems. — [Hacker News #47301395](https://news.ycombinator.com/item?id=47301395)
- **Maxim AI / Towards Data Science:** A 12-metric framework across Retrieval, Generation, Agent, and Production categories, drawn from 100+ enterprise deployments. Agent category metrics include task completion rate, tool call accuracy, context precision, hallucination detection, and cost per task. — [Towards Data Science: 12-Metric Framework from 100+ Deployments](https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/)

## Gotchas

- **Don't trust a single metric.** Task success rate alone is a vanity metric. A 95% success rate achieved with 3× the median token cost and 2× the median latency is a failure at enterprise scale. Evaluate across retrieval quality, generation faithfulness, behavioral correctness, operational constraints, and safety simultaneously.
- **Don't skip trajectory analysis.** If your agent can produce correct answers through wrong reasoning paths, you'll discover this in production when a user catches a subtle factual error that your output-only eval never flagged. Trace the tool-call sequence, not just the final answer.
- **Don't deploy LLM-as-judge without bias mitigation.** Randomized presentation order, majority voting across judges, minority-veto for safety, and calibration against human-annotated ground truth are the minimum viable mitigations. Without them, your evaluator may be wrong more often than right.
- **Don't treat evaluation as a one-time gate.** Gartner's projection and Deloitte's data both point the same direction: evaluation must be continuous. Set it up as a CI stage, a production sampling pipeline, and a scheduled regression suite — not a pre-launch checklist.
- **Don't confuse benchmark saturation with capability.** SWE-bench at 93.9% sounds like near-perfect coding agents. Microsoft SWE-Bench-Mutated research proves it's not. The benchmarks measure what you can test in a sandbox, not what your agent will encounter in your production environment.
