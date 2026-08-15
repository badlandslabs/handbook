# S-2671 · The Evaluation Gap Stack — When Your Agent Aces the Benchmark and Flops in Production

A team scores 92% on GAIA. They ship. Customer satisfaction week one: 64%. The agent handled the "what" correctly — it just couldn't handle the "how": ambiguous phrasing, mid-conversation corrections, the user who said "actually, never mind." This is the evaluation gap: benchmarks measure capability; production requires reliability.

## Forces

- **Benchmarks measure capability, not reliability.** SWE-bench, GAIA, WebArena — all score task completion under controlled conditions. Production introduces compounding failures: ambiguous inputs, mid-task corrections, token drift, API schema changes, and users who say things in the wrong order.
- **Agents fail non-deterministically.** The same input can produce different trajectories on different runs. A score by itself is useless unless it reflects the distribution of real inputs and measures what actually changes when you ship.
- **LLM-as-judge is unreliable at temperature=0.** Northwestern researchers (arXiv:2412.12509) found that even deterministic LLM judges exhibit low internal consistency (measured via McDonald's omega) across repeated evaluations. One sample from the model's distribution is insufficient — you need multiple samples and psychometric framing.
- **Offline evals alone are insufficient.** They catch regressions before deployment but cannot detect the drift that happens after: data distribution shift, tool API changes, user behavior shifts. Online evals catch these — but only if the pipeline is instrumented to score production traffic.
- **Regression gates are inconsistently applied.** Unlike traditional CI where a failed test blocks a deploy, prompt changes in agentic systems still often go straight to production. Without a harness that blocks deployment on eval regressions, evals are theater.

## The move

Build an **eval harness** that closes the loop from development to production. The harness does three things: defines what gets evaluated, executes the scoring, and acts on the results.

- **Layer your evaluation by what matters:** score reasoning (did the agent plan correctly?), actions (did it call the right tools in the right order?), and outputs (did it produce the right answer?). Braintrust's framework recommends organizing metrics by architectural layer rather than using a single composite score.
- **Run offline evals against curated datasets before every deploy.** These act as unit tests — they catch regressions before they reach production. LangChain's Agent Development Lifecycle frames offline evals as the gate between build and deploy.
- **Run online evals on production traffic continuously.** Tools like AgentOps (5,770 GitHub stars, MIT license) instrument agents with two lines of code and capture step-by-step traces, cost data, and session replays on live traffic. Braintrust similarly scores production traces automatically and alerts on regressions.
- **Calibrate LLM-as-judge with human oversight.** Northwestern's research shows LLM judges need multiple samples and psychometric consistency checks. LangSmith recommends routing samples to human reviewers who flag disagreements, then using that feedback to iteratively calibrate the automated evaluation.
- **Set hard regression gates in CI/CD.** Arize's Laurie Voss describes the pattern: (1) production trace, (2) evaluator, (3) monitor, (4) alert, (5) annotation queue, (6) regression dataset, (7) CI gate. The last step is what makes evals real — blocking a deploy when eval scores drop below threshold.
- **Pick your eval framework by deployment model:** DeepEval (open-source, self-hosted, free but engineering-time-intensive) for teams wanting full control; LangSmith (tight LangChain integration, hosted) for LangChain shops; Braintrust (observability + evals, no framework lock-in) for framework-agnostic teams; Arize Phoenix (open-source instrumentation, enterprise monitoring) for large-scale deployments.

## Evidence

- **Benchmark gap case study:** A team scored 92% on GAIA (multi-step reasoning + tools benchmark, human baseline 92%) but achieved only 64% customer satisfaction in production after one week. Root cause: the benchmark tested correct outputs, not the conversational recovery and ambiguity-handling required by real users. — Chanl Blog, "Your Agent Aced the Benchmark. Production Disagreed." — [https://www.chanl.ai/blog/ai-agent-evaluation-benchmarks-predict-production](https://www.chanl.ai/blog/ai-agent-evaluation-benchmarks-predict-production)
- **LLM-as-judge reliability research:** Northwestern University researchers found LLM judgments at temperature=0 still exhibit low internal consistency reliability across repeated evaluations. They recommend McDonald's omega as a measurement framework and multiple samples per judgment. — arXiv:2412.12509 (v2, February 2025) — [https://arxiv.org/abs/2412.12509](https://arxiv.org/abs/2412.12509)
- **Production eval harness pattern:** AgentOps (MIT-licensed, 5,770 stars, integrates with CrewAI, Agno, OpenAI Agents SDK, LangChain, AutoGen, AG2, CamelAI) provides two-line instrumentation for step-by-step session replay, cost tracking, and benchmarking. Online eval pipelines (agent-eval-harness by mattrobin) ingest OpenTelemetry traces and flag statistically significant regressions within minutes of a deploy. — GitHub: agentops-ai/agentops, mattrobin/agent-eval-harness

## Gotchas

- **A single eval score is a lie.** Run multiple trials per task (AgentOps, LangSmith both support this). An agent that scores 85% on one run and 72% on the next is not an 85% agent — it is a variable agent, and variability is the real production risk.
- **Benchmarks don't test your tools.** SWE-bench tests code repair in open-source repos. WebArena tests web browsing. Neither tests whether your internal CRM API returns the schema your agent expects. Build task-specific evals against your actual tool chain.
- **Calibration drift is silent.** An LLM-as-judge prompt that was 80% aligned with human judgment six months ago may be 55% aligned today as the base model's behavior shifts. Re-calibrate against human ground truth at least quarterly — don't trust the score without the human-in-the-loop check.
- **Cost per eval matters at scale.** Running full LLM-as-judge evaluations on every production trace is expensive. Arize recommends sampling production traffic strategically (e.g., 5% of traces, with biased sampling toward high-risk interactions) rather than scoring everything.
