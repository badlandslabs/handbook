# S-1332 · The Compounding Accuracy Stack — When Your 95% Agent Succeeds 60% of the Time

Your agent passes every demo. Your test suite returns green. You ship it. Three weeks in, the on-call team is drowning: the agent completes a task 60% of the time, not 95%. Nobody can explain the gap, because nobody measured what actually matters. This is the compounding accuracy problem: single-turn benchmark scores don't survive multi-step execution, and most teams are measuring the wrong thing entirely.

## Forces

- Benchmark scores reflect single-task accuracy, not end-to-end reliability across a workflow — a 95% accurate step becomes 60% after 20 sequential steps
- Trajectory (how the agent reasons) and outcome (did it succeed) are treated as the same metric when they diverge constantly
- "Vibe checking" — manually chatting with the agent — is the primary evaluation method at most teams, which is subjective, non-repeatable, and blind to cost
- LLM-as-judge evaluators introduce their own failures: position bias (first answer wins), length bias (longer = better), and agreeableness bias (accepts without criticism), with error rates exceeding 50% unmitigated
- Enterprise teams face a 37% gap between lab benchmarks and production reliability, driven by ambiguous inputs, flaky APIs, and adversarial conditions benchmarks never simulate
- Token cost compounds with steps: two agents with identical success rates can have 50x cost-per-task difference due to retry loops, redundant calls, and poor efficiency

## The move

Distinguish trajectory from outcome. Evaluate both. Build regression.

- **Measure end-to-end success rate** — run the full workflow 100+ times and count completions, not just step-level accuracy. A task requiring 20 steps at 95% per-step accuracy yields ~36% end-to-end success (0.95^20).
- **Separate trajectory scoring from outcome scoring.** Did the agent reason correctly down a wrong path? Did it succeed for the wrong reason? These require different fixes. Jobs Culture recommends 5 evaluation layers: task completion, safety, stability, cost efficiency, and skill coverage (web search, memory, cart operations, reflection).
- **Use LLM-as-judge with calibration.** Deploy multiple judge instances with randomized response order, majority voting, and explicit disclaimers in the prompt ("do not favor longer responses"). Target 0.80+ Spearman correlation against human judgment. Without calibration, LLM judges can exceed 50% error rate.
- **Build a regression pipeline.** Run evals against every code change. The KDD 2025 tutorial on LLM agent evaluation recommends treating evaluation as a dynamic, continuous process — not a one-time benchmark. SAP's tutorial materials include specific test suites for agent behavior, capability, reliability, and safety.
- **Track cost-per-task, not just success rate.** An agent that achieves 80% success but costs 50x the budget baseline is not an 80% agent. Track token consumption per task type, watch for retry loops, and set hard cost ceilings per execution.
- **Stress-test with adversarial inputs.** Null values, Unicode names (O'Brien, José, 北京), empty fields, concurrent requests, and prompt injection attempts. What works on clean demos fails under production noise. Harper Labs documented a $47,000 fraudulent refund processed by a customer support agent from a prompt injection.

## Evidence

- **Enterprise research report:** MMC Ventures surveyed 30+ AI agent startup founders and 40+ enterprise practitioners. Found that reliability issues are the #1 barrier to enterprise adoption — practitioners are constraining themselves to fewer-step workflows and internal-facing agents with human review rather than deploying fully autonomous agents. — [State of Agentic AI: Founder's Edition](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)
- **AI monitoring thread:** HN discussion on production AI monitoring surfaced AgentShield (2-line integration for LangChain, CrewAI, OpenAI Agents SDK with execution tracing, risk detection, cost tracking) and Lava (gateway proxy with spend keys that enforce hard budget limits per agent). Both address the observability gap — without them, teams have no step-level audit trail or token accounting. — [Ask HN: How are you monitoring AI agents in production?](https://news.ycombinator.com/item?id=47301395)
- **Reliability math:** Rippletide quantified compounding failure: 95% per-step accuracy yields ~86% after 3 steps, ~60% after 10 steps, ~36% after 20 steps. Multiply by a fleet of agents running continuously, and incorrect production actions become the operating reality, not the edge case. — [AI Agent Reliability in Production](https://www.rippletide.com/enterprise/ai-agent-reliability)
- **Evaluation framework guide:** Jobs Culture's 2026 evaluation guide recommends 5-layer scoring (task completion, safety, stability, cost, skills) with trajectory/outcome separation and 100+ run regression suites. Notes that "vibe checking" is a primary evaluation method at most teams — a recipe for production failure at scale. — [AI Agent Evaluation Guide 2026](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)
- **Academic framework:** KDD 2025 tutorial on LLM agent evaluation introduced a two-dimensional taxonomy (evaluation objectives: behavior, capability, reliability, safety × evaluation process: interaction modes, datasets, metrics, tooling). Includes enterprise-specific challenges around role-based data access and compliance. — [KDD 2025: Evaluation & Benchmarking of LLM Agents](https://sap-samples.github.io/llm-agents-eval-tutorial)
- **LLM-as-judge calibration:** Galileo AI's research documented >50% error rates in uncalibrated LLM judges driven by position bias, length bias, and agreeableness bias. Mitigation: ensemble of judges with randomized presentation order, minority-veto ensembles for safety-critical outputs, and calibration against small human-annotated datasets. — [Agent Evaluation Framework](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Benchmarks measure the wrong thing.** WebArena, SWE-bench, and GAIA measure task success in clean conditions — they don't capture production variance from ambiguous inputs, API flakiness, or adversarial users. Use them for direction, not as a reliability proxy.
- **Single-run evaluations are noise.** An agent achieving 60% on one run of 20 tasks may score 80% on the next. Run 100+ executions per configuration and track the distribution, not the mean.
- **Success rate and quality are not the same.** An agent that completes 100% of tasks by returning wrong data scores 100% on completion metrics but 0% on quality. Separate the two.
- **Human reviewers don't scale but are still needed for calibration.** LLM judges need periodic human validation to catch drift. Without a small human-annotated golden dataset, you can't tell when your judge has quietly started favoring longer outputs or agreeing with everything.
- **Monitoring without enforcement is theater.** Tracing what the agent did after it already deleted the database is not safety — it's post-mortem. Pre-execution validation (like Rippletide's per-action enforcement) transforms reliability from a statistical property into a deterministic one.
