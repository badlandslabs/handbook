# S-1891 · The Multi-Run Reliability Stack — When Pass@K Replaces Pass@1

Your agent works. It worked in the demo. It worked in the staging suite. It worked three times in a row on your laptop. Then it deployed and started failing on inputs that looked identical to the ones that passed. Your single-run evaluation told you the agent worked. The real world told you it didn't. This is where single-run eval stops being honest and multi-run reliability measurement takes over.

## Forces

- **Non-determinism compounds.** The same prompt can produce different tool-call sequences across runs. A model scoring 95% pass@1 may score only 72% pass@5 — the difference between "reliable enough" and "deployable"
- **Benchmarks can be gamed.** UC Berkeley researchers examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA) and found all could be exploited — contamination, shortcut-taking, and environment-gaming are rampant
- **Episodic eval misses evolution.** Standard benchmarks treat each task as independent. Real agents learn, adapt, and fail across tasks — a quality existing benchmarks don't measure
- **Trajectory beats outcome.** A task that completed but took 47 wrong turns is not the same as one that took 3 correct ones. Eval must score the path, not just the destination
- **Human verification is still required.** Every production team using LLM-as-judge also uses human review — judges correlate well with humans (~0.80+ Spearman) but don't replace them for high-stakes outputs

## The Move

Measure agent quality as a reliability distribution, not a binary pass/fail. Run evaluations multiple times, track pass@K curves, and gate deployment on consistency thresholds, not single-run accuracy.

**Key techniques:**

- **Run evaluations 5–10 times per scenario.** Track pass@1, pass@3, pass@5, pass@10 curves. A model with 85% pass@1 but 98% pass@10 behaves very differently in production than one with 95% pass@1 and 96% pass@10
- **Gate on consistency thresholds.** Require pass@5 ≥ 90% for production deployment, not pass@1. This catches stochastic failures before users do
- **Distinguish trajectory quality from outcome quality.** Score both final outcome (did it complete correctly?) and reasoning path (how many wasted steps, hallucinated tool calls, or recovery events occurred?)
- **Use domain-matched benchmarks.** WebArena for browser agents, SWE-bench Verified for code agents, tau-bench for CRM workflows, GAIA for general assistants. Generic benchmarks don't predict domain performance
- **Implement LLM-as-judge with human calibration.** Target ≥0.80 Spearman correlation with human judgment. Calibrate on 20–30 samples before trusting the judge at scale
- **Build a 50–100 scenario suite per agent, stratified by difficulty.** Easy/medium/hard at roughly 30/50/20 distribution. Each scenario includes input, expected output characteristics, and weighted evaluation criteria
- **Integrate eval into CI/CD.** Trigger on every commit, nightly, and on-demand. Block deployment on regression — a green single-run test suite is insufficient; require consistency passes

## Evidence

- **HN Ask: "How are you testing AI agents before shipping to production?"** — Practitioners report 68% of agents execute at most 10 steps before requiring human intervention, 74% depend primarily on human evaluation. Top failure modes: hallucination under unexpected inputs, edge case collapse (null values, Unicode names like O'Brien or José), prompt injection, and context limit surprises. A real incident: prompt injection in a customer support agent processed a $47,000 fraudulent refund — [HN #47325105](https://news.ycombinator.com/item?id=47325105)

- **InfoQ: "Evaluating AI Agents in Practice"** — Frameworks like AutoGen Bench enable performance benchmarking. Key insight: agents often work perfectly in sandbox but fail silently in production (e.g., skipping a refund when API returns an error). Single-turn accuracy metrics and NLP benchmarks (BLEU, ROUGE) don't capture multi-step failure modes. Recommended approach: hybrid evaluation combining automated scoring with human spot-checks, running in CI/CD with deployment gates — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

- **ChangeGamer AI Benchmark Reference** — Comprehensive benchmark table: AgentBench (8 diverse environments), SWE-bench Verified (real GitHub issues), WebArena (browser tasks), OSWorld (OS interactions), GAIA (general assistance), BFCL (function calling), tau-bench (CRM workflows), MLE-bench (ML engineering). Key insight on evaluation: agents calling external tools produce stochastic outputs; eval must sandbox or mock calls consistently. Multi-run reliability metrics (pass@K) are essential because the same prompt produces different tool sequences across runs — [ChangeGamer](https://changegamer.ai/resources/evaluating-ai-agents)

- **GitHub Blog: Top 10 Open Source AI Projects** — MCP (Model Context Protocol) emerging as the USB-C of AI tooling. Top projects include MCP servers from Anthropic, Google, and Puppeteer, enabling any LLM to call standardized tools. This standardization enables more consistent eval — when tool interfaces are stable, eval harnesses can be too — [GitHub Blog](https://github.blog/open-source/maintainers/from-mcp-to-multi-agents-the-top-10-open-source-ai-projects-on-github-right-now-and-why-they-matter/)

- **SEA-Eval (arXiv, 2026)** — UC Berkeley researchers found all eight major agent benchmarks can be exploited (contamination, gaming). Proposes closed-loop evaluation where agents are measured across cross-task evolutionary quality, not just episodic task completion. Demonstrates that treating each task as independent misses how real agents accumulate competence or failure over time — [arXiv #2604.08988](https://arxiv.org/html/2604.08988v1)

- **Zylos Research: "AI Agent Evaluation and Benchmarking: Beyond Task Completion"** — Documents the benchmark crisis: static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. Shift to trajectory-level evaluation — scoring the full sequence of reasoning and action steps — is the emerging standard. Cost-per-successful-task and time-to-completion are now production-relevant metrics alongside accuracy — [Zylos Research](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)

## Gotchas

- **Running once and passing is not evaluation.** A single successful run tells you the happy path works. It tells you nothing about consistency. Always report pass@K curves, not pass@1
- **Benchmarks predict generic capability, not domain performance.** An agent scoring 60% on SWE-bench can still be the best code agent for your internal DSL if your eval suite says so — build custom benchmarks from your actual task data
- **LLM-as-judge correlation degrades on edge cases.** Judges perform well on typical outputs but diverge from human judgment on unusual, adversarial, or high-stakes outputs. Always spot-check the judge's disagreeing cases
- **Cost of eval scales with pass@K.** Running 10 runs × 100 scenarios × 5 agents = 5,000 agent invocations. Budget $5–20 in API calls per agent's full benchmark run. Many teams skip this and pay in production incidents instead
- **Context window limits in eval are different from production.** What works in a clean eval environment with mocked tool responses may fail when tools return large payloads, network latency, or partial data. Include real tool integration tests, not just mocked ones
