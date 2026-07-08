# S-829 · The Eval-First Stack — When You Don't Know If Your Agent Is Working

You shipped an agent. It runs. It responds. But you have no idea if it's doing the right thing, degrading after model updates, choosing the wrong tools, or hallucinating answers your users will trust and act on. You need evals — not vibes.

## Forces

- **Agents degrade silently.** Unlike traditional software that throws exceptions on failure, an agent can drift toward wrong tools, shallow reasoning, and context-ignored answers without a single error log. Traditional CI passes while users suffer.
- **Eval complexity traps teams.** The moment you reach for "comprehensive evaluation," you build a framework that takes 6 months and is already stale. Teams either over-engineer evals or skip them entirely.
- **LLM outputs are non-deterministic, but behavior isn't.** You can't assert exact output strings — but you can assert reasoning quality, tool selection accuracy, and task completion. Knowing which dimension to measure is the whole game.
- **Eval quality compounds.** Every test case you add to a harness is a permanent regression guard. Every prompt change, model swap, or architecture refactor gets validated automatically. Teams without evals spend the first 3 weeks of every change validating manually.

## The Move

Build a lightweight eval harness **before** the agent reaches production. Focus on five dimensions that matter, use two eval types that cover the right ground, and gate deployments on a subset that runs in under 90 seconds.

### The five dimensions that actually matter

1. **Task completion rate** — Did the agent achieve the stated goal end-to-end? Binary or graded. The single most important metric.
2. **Tool call accuracy** — Did it call the right tool with the right arguments? Tool calling fails 3–15% of the time in production, often silently.
3. **Reasoning coherence** — Does the agent's trace show logical step progression, not shortcut jumps or hallucinated tool calls?
4. **Context grounding** — Are responses grounded in retrieved/session context, not training data confabulation?
5. **Cost per success** — Total API calls or tokens spent per successful task. An agent that achieves 95% task completion but costs 40× more than a simpler approach is a real business problem.

### Two eval types that cover the right ground

**Unit evals (CI gate):** Fast (<90s), code-first, pytest-compatible. Test specific tool selections, prompt response quality against golden examples, and boundary conditions (empty context, malformed input). Tools: DeepEval (open-source, code-first), Promptfoo (CLI-first, free), or Azure AI Agent Evaluations (for Azure teams).

**End-to-end traces (staging gate):** Full multi-turn conversation traces evaluated by LLM-as-a-judge. The judge rates task completion, reasoning coherence, and safety on a defined rubric. Run in staging before every prod deploy. Tools: LangSmith, Braintrust, or MLflow with custom judges.

### The CI/CD pipeline for agents

Four stages, each with a distinct eval gate:

1. **PR-time fast checks** — Unit evals only. Tool selection correctness, prompt response assertions. Must pass before merge.
2. **Staging deployment** — Full LLM-as-judge evaluation against a curated test suite. Grades task completion, tool accuracy, and reasoning quality.
3. **Canary / progressive rollout** — Route 5% of traffic to new version. Monitor task completion and human intervention rate in real time.
4. **Production** — Continuous sampling: evaluate a random 1–5% of production traces. Alert on degradation. Amazon's guidance: deploy with statistical validation and acknowledge expert agreement limitations on judge prompts.

### The four-tool production stack

| Tool | Role | CI/CD Native |
|---|---|---|
| DeepEval | Open-source pytest-native unit evals | Yes |
| LangSmith | Tracing + staging LLM-as-judge | Yes |
| Braintrust | Enterprise dataset + CI gates + production monitoring | Yes |
| Arize Phoenix | High-volume production trace monitoring | Via SDK |

## Evidence

- **AWS Labs (2026):** Publishes an open-source agent evaluation framework with explicit CI/CD integration. Recommends a pipeline: Source Repo → Build (unit tests) → Staging (eval gate) → Production. Source commits trigger evaluation runs before deployment. — [awslabs.github.io/agent-evaluation/cicd](https://awslabs.github.io/agent-evaluation/cicd/)
- **AgentMarketCap (April 2026):** Reports deployments that skip evaluation infrastructure take 3× longer to reach stable production operation. 57% of organizations already have agents in production, but only 32% have systematic eval infrastructure — meaning most ship without failure detection. — [agentmarketcap.ai/blog/2026/04/10/building-ai-agent-evals-cicd-2026](https://agentmarketcap.ai/blog/2026/04/10/building-ai-agent-evals-cicd-2026)
- **Amazon engineering blog (2026):** Since 2025, thousands of agents have been built across Amazon organizations. Their guidance: deploy LLM-as-judge with statistical validation, use explicit rubrics with few-shot examples, integrate evals into CI/CD with three trigger types (PR, staging, canary), and note that agentic eval must assess emergent system behavior — tool selection accuracy, reasoning coherence, and memory retrieval efficiency — not just model benchmarks. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Anthropic (Dec 2024):** Teams consistently shipping the most reliable agents use simple, composable patterns rather than complex frameworks. Evals should focus on task success criteria and feedback loops — not architectural complexity. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **LLM-as-a-judge has a position bias** — judges favor first or last positions in comparisons. Mitigate by swapping order and requiring consensus across multiple judges.
- **A passing eval is not a working agent.** You are measuring against your test suite, which captures only what you anticipated. Adversarial inputs, prompt injections, and novel tool combinations will not appear in unit tests. Supplement with automated red-teaming.
- **Task completion is necessary but not sufficient.** An agent can "complete" a task by taking the wrong path, burning 10× the tokens, and returning a subtly wrong answer. Track cost per success alongside completion rate.
- **Human intervention rate is a domain signal, not a failure.** In healthcare and finance, high autonomy can mean safety guardrails are missing. Always interpret autonomy metrics in context.
