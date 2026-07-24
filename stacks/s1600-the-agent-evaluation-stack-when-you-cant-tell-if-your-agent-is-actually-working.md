# S-1600 · The Agent Evaluation Stack — When You Can't Tell If Your Agent Is Actually Working

Your agent ships. It returns answers. You check the output once, it looks fine, you deploy. Then a week later someone notices the agent called `list_all_customers` before `get_order` — wrong sequence, wrong policy, but it happened to reach a correct-looking answer this time. You had no way to know. This is the stack for measuring whether your agent is actually working: what to measure, at what layer, with what tools, and how to catch the failures that endpoint scoring misses.

## Forces

- **Endpoint scoring is necessary but insufficient.** A final-answer eval tells you whether the output looks right. It says nothing about whether the agent got there through the right steps — and in production, the wrong path eventually lands on the wrong answer.
- **Agents fail in cascading ways that single-turn evals can't see.** Tool calls, ordering, retries, and termination checks are each a failure point. A bad step early in the run compounds into wrong output at the end.
- **Standard benchmarks don't reflect production failure modes.** WebArena and SWE-bench are canonical but disconnected from how your specific tools, policies, and user inputs behave. Teams that rely on benchmarks ship agents that fail on real inputs.
- **The adoption gap is wide.** 89% of agent teams have some observability, but only 37% run online evals and 52% run offline evals (LangChain State of Agent Engineering survey). Most teams can inspect a bad run after it happens but can't prevent the same failure from shipping twice.
- **Agent behavior shifts with model updates, API changes, and input drift.** GPT-4 showed measurable behavior changes across versions — tasks at 97% accuracy in March 2023 dropped to 87% by June 2023 on the same benchmark. Point-in-time certification doesn't survive a model swap.

## The move

Measure the trajectory, not just the outcome. Build a three-layer evaluation stack and run it continuously.

### Layer 1 — Outcome metrics (was the task completed?)

Define task-level success criteria *before* measuring. Different agent types need different definitions: a customer support agent needs ticket resolution + tone + policy adherence; a coding agent needs PR acceptance + no regressions + passing tests.

Use deterministic checks where possible (exact string match, JSON schema validation, exit code), and LLM-as-judge for nuanced dimensions (tone, relevance, groundedness). When using LLM judges, apply Schema-Guided Reasoning (SGR) to constrain the judge's output format, and calibrate the judge against human labels before trusting it at scale.

Track the full distribution, not just pass/fail: what percentage of runs succeed? What are the failure categories and their frequencies?

### Layer 2 — Trajectory metrics (how did the agent get there?)

This is where most production failures live undetected. Score the entire run: which tools were called, in what order, with what arguments, whether each intermediate step satisfied policy.

Key trajectory dimensions:
- **Tool selection correctness** — did the agent call the right tool for the current sub-task?
- **Tool call ordering** — did the agent establish prerequisites before depending on them? (e.g., authenticate before querying)
- **Argument correctness** — did the tool receive valid, complete arguments? Did it handle errors from prior calls?
- **Termination logic** — did the agent stop at the right point? Did it retry on correctable failures?
- **Constraint adherence** — did the agent respect rate limits, scope constraints, or policy guardrails at each step?

Use deterministic checks for ordering, arguments, and loop detection. Use LLM judges for reasoning quality and policy adherence. The minimum viable setup: 50–200 real production examples, per-step rubrics, 10+ runs per example for statistical power, statistical regression tracking across runs, and a held-out evaluation set that isn't used for tuning.

### Layer 3 — Component metrics (where specifically did it fail?)

When trajectory scoring flags a problem, drill into the specific failing component: a retriever, a sub-agent, a tool wrapper, or the orchestration logic itself. Component-level evals isolate the bottleneck so a fix targets the right part.

### The eval loop

Build around this cycle: **trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring**. Every diagnosed production failure should leave behind a trace, a label, a dataset row, and a scorer. A repeatable failure belongs in the regression suite, not just a post-mortem.

Use replay harnesses to test against historical failure traces without hitting live systems. Regression suites built from production failures catch the specific failure modes that benchmarks miss.

### Tooling

| Tool | Strength | Best for |
|------|----------|----------|
| **LangSmith** | Deep LangChain integration, trace exploration | Teams already in LangChain ecosystem |
| **Braintrust** | Eval-first design, dataset tooling, prompt playground | Prompt iteration, human-in-the-loop review |
| **Opik (Comet)** | Open-source, framework-agnostic, production observability | Teams wanting full ownership, on-premise options |
| **DeepEval** | Unit-test-like evals, tight CI/CD integration | Developers who want evals as code |
| **Galileo AI** | Trajectory scoring, rubric-based multi-dimension analysis | Production monitoring with rubric governance |

Choose tools based on where your team spends the most time: observability and trace inspection (LangSmith/Opik), prompt iteration (Braintrust), or CI-integrated regression testing (DeepEval).

## Evidence

- **Practitioner HN thread:** HN users with production agent experience strongly endorse evals as non-negotiable — "If some team was just winging it without robust eval practices they're not to be trusted." Multiple practitioners describe cases where prompt tweaks "passed an initial vibe check, but when run against the full eval suite revealed regressions." — [Hacker News, "Principles for production AI agents" thread, 128 points, 19 comments](https://news.ycombinator.com/item?id=44712315)

- **Independent survey (5.5B tokens):** The Kamiwaza Agentic Merit Index (KAMI) benchmark, developed from evaluating agents at enterprise scale, finds that traditional LLM benchmarks fail on two fronts: training data contamination and inability to assess agentic multi-step tool use under uncertainty. Paper explicitly calls for evaluation methods reflecting real-world deployment, not laboratory conditions. — [arXiv 2511.08042, Jesus Vicente Roig, November 2025](https://arxiv.org/abs/2511.08042)

- **Engineering survey:** The LangChain State of Agent Engineering survey (2025) finds 57.3% of respondents have agents in production, but only 37.3% run online evals and 52.4% run offline evals — revealing a large gap between observability capability and systematic evaluation practice. — [LangChain State of Agent Engineering](https://www.langchain.com/state-of-agent-engineering)

- **Practitioner blog (KDD 2025):** SAP Labs researchers' survey of LLM agent evaluation at KDD '25 establishes a two-dimensional taxonomy: evaluation objectives (agent behavior, capabilities, reliability, safety) crossed with evaluation process (interaction modes, datasets, metric computation, tooling). Enterprise-specific challenges — role-based access, reliability guarantees, long-horizon interactions, compliance — are consistently overlooked in current benchmarks. — [arXiv 2507.21504, Mohammadi et al., KDD 2025](https://arxiv.org/abs/2507.21504)

- **Show HN (Zalor, 4 months ago):** Team building an agent testing platform describes the core problem: "Agents often break when you tweak system prompts, swap models, or change workflows." Built around regression suites that capture specific failure modes. — [Hacker News, "Show HN: Automated Testing for AI Agents", zalor.ai](https://news.ycombinator.com/item?id=47270208)

- **Practitioner guide:** Author James M documents the hidden failure problem: a refund agent can produce a correct-looking final answer after calling tools in the wrong order, violating policy at intermediate steps, and recovering by luck. Demonstrates the trajectory scoring table showing why endpoint evals pass this case while trajectory evals catch it. Recommends minimum viable setup of 50–200 real examples, 10+ runs per example, and statistical regression tracking. — [jamesm.blog, "Evaluating Agents in Production: Trajectory Metrics, Not Just Final Answers", June 2026](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)

## Gotchas

- **"It passed the eval" is not the same as "it works."** If your eval set doesn't cover the failure mode, the agent can fail in production undetected. Coverage of failure modes, not quantity of examples, is what matters.
- **LLM judges are helpful but not authoritative.** Judges have their own biases, can be gamed, and drift across model versions. Calibrate against human labels before using judge scores as the source of truth for high-stakes decisions.
- **Running evals once is not enough.** Model updates, tool API changes, and input distribution shifts all shift agent behavior. Treat evaluation as a continuous pipeline, not a pre-deployment gate.
- **Public benchmarks give false confidence.** A high WebArena score doesn't mean your internal tooling agent will handle your specific Slack integration correctly. Build domain-specific eval datasets from your actual production failure traces.
- **The held-out set is your only real signal.** If you're also using your eval set for prompt tuning, you're testing your ability to optimize, not your agent's ability. Keep a genuinely held-out evaluation set that is never used for tuning.
