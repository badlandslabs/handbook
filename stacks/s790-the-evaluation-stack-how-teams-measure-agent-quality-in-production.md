# S-790 · The Evaluation Stack: How Teams Measure Agent Quality in Production

You shipped the agent. It works in the demo. You have no idea if it works in production — because you never built a way to find out. The agent passes the eyeball test. It also silently breaks every third friday. This is the evaluation gap: agents that run but aren't measured.

## Forces

- **Output-only evaluation misses the trajectory.** An agent can reach the right answer through the wrong path — calling the wrong tool, passing bad arguments, burning 40x the tokens. Final-output accuracy tells you nothing about which layer regressed.
- **Agents are non-deterministic where traditional tests aren't.** Exact-match testing breaks. The same input produces different outputs. You need evaluation primitives built for variance.
- **Evals decay faster than the stack.** 70% of regulated enterprises rebuild their AI agent stack every 3 months or faster. Every rebuild resets eval coverage unless the evaluation layer is treated as infrastructure, not a one-off.
- **Only 27% of teams run evals before every deployment.** The LangChain State of Agent Engineering report found that most teams evaluate reactively — after a production incident, not before a release.
- **The N-1 interaction problem.** When the agent changes, every eval case that simulated a multi-turn conversation is now simulating something the agent will never do again. Eval data must be versioned alongside the agent.

## The move

### Build a three-level evaluation stack — not a single aggregate score

1. **End-to-end (task success):** Did the agent achieve the user's goal? Binary or threshold. Fastest to implement, weakest for diagnosis.
2. **Trajectory-level:** Was the path correct and efficient? Tool selection accuracy, argument correctness, step count vs. expected. This is where you catch "lucky failures" — agents that reached the right answer via the wrong route.
3. **Component-level:** Which specific layer broke? Which retriever, tool, or sub-agent failed? Enables targeted fixes rather than broad prompt rewrites.

Score each independently. An aggregate pass/fail hides which layer regressed.

### Invest in the golden dataset first

The recommended composition (Databricks Agent Bricks pattern, Confident AI guidance):
- **70% representative edge cases** from real production logs
- **20% adversarial / known failure patterns** (injected from incident history)
- **10% synthetic data** generated from documentation for coverage gaps

Minimum viable: 100+ pairs for basic validation. Robust production: 500–1K. Treat the dataset like code — version-controlled, reviewed, and updated with every agent change.

### Layer LLM-as-a-judge with human review

Use LLM judges for speed and scale (trace scoring, rubric evaluation, consistency checks). Use humans for tone, trust, and contextual appropriateness — what automation systematically misses. The best pipelines combine both continuously. Key: pick the right judge per dimension — deterministic checks for tool correctness, LLM-as-a-judge for anything the agent produced.

### Make traces the evaluation backbone

Every agent run — success or failure — produces a trace: all tool calls, arguments, intermediate outputs, and final answer. Traces enable trajectory-level scoring, surface new failure modes you didn't anticipate, and keep LLM judges calibrated when reviewed periodically. LangSmith, DeepEval's `@observe` decorator, and AWS Agent Evaluation all provide trace-based evaluation infrastructure.

### Score six dimensions independently (Future AGI framework, 2026)

1. **Task completion** — did the goal get achieved?
2. **Tool selection** — right tool, or correctly no tool? (F1 with explicit "called tool that shouldn't have" bucket)
3. **Argument correctness** — are tool inputs schema-valid and semantically correct?
4. **Plan adherence** — did the agent follow the expected reasoning steps?
5. **Step efficiency** — was the trajectory shorter than the maximum allowed? (token cost proxy)
6. **Safety / policy** — PII handling, permission boundaries, refusal correctness

### Gate CI/CD on eval results

Run eval suites before every deploy — not just after incidents. Only 27% of teams do this. DeepEval's pytest integration makes this straightforward: `deepeval test run` in CI, failing builds on metric regressions. Braintrust and LangSmith both support experiment tracking with dataset versioning to catch regressions across prompt or model changes.

### Treat operational constraints as first-class metrics

Latency, cost per task, token efficiency, and tool reliability aren't afterthoughts — they determine whether a technically capable agent is viable at scale. Track these per-release alongside accuracy metrics.

## Evidence

- **KDD 2025 Tutorial (Mohammadi, Li, Lo, Yip):** Comprehensive evaluation taxonomy covering interaction modes (static vs. dynamic), evaluation data sources, and the distinction between LLM eval and agent eval. Framework: evaluate at dimension, subcategory, and interaction-mode levels. — [https://sap-samples.github.io/llm-agents-eval-tutorial/2025_KDD_Evaluation_and_Benchmarking_of_LLM_Agents.pdf](https://sap-samples.github.io/llm-agents-eval-tutorial/2025_KDD_Evaluation_and_Benchmarking_of_LLM_Agents.pdf)
- **LangChain Blog (Feb 2025):** ReAct agent benchmarking study — found that context degradation (more tools + more context = worse performance) requires trajectory-level evaluation to detect, since final-output accuracy held even as step efficiency degraded. — [https://www.langchain.com/blog/react-agent-benchmarking](https://www.langchain.com/blog/react-agent-benchmarking)
- **InfoQ Article (March 2026):** Hybrid evaluation (LLM-as-a-judge + human judgment) is non-negotiable for production agents. Operational constraints — latency, cost per task, token efficiency, tool reliability, policy compliance — are first-class evaluation targets, not afterthoughts. — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)
- **Cleanlab Enterprise Survey (August 2025):** Out of 1,837 engineering leaders, only 95 had AI agents live in production. Of those, <1 in 3 were satisfied with observability and guardrail solutions. 63% plan to improve evaluation and observability in the next year. 70% of regulated enterprises rebuild their agent stack every 3 months or faster. — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Anthropic Research (February 2026):** Analyzed millions of human-agent interactions across Claude Code and the public API. Found that effective oversight requires new post-deployment monitoring infrastructure: agents that operate autonomously for hours need trajectory-level visibility that single-turn accuracy metrics cannot provide. — [https://www.anthropic.com/research/measuring-agent-autonomy](https://www.anthropic.com/research/measuring-agent-autonomy)
- **aunhumano Blog (September 2025):** "Models constantly change and improve but evals persist" — the biggest eval challenge is keeping N-1 interaction simulations current as the agent changes. Start with end-to-end success criteria, add trajectory metrics as coverage grows. — [https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)
- **Future AGI (2026):** Six independent evaluation dimensions for agentic systems. Most "agent eval" frameworks are LLM eval frameworks with a trajectory bolted on — pick trajectory-first tooling. — [https://futureagi.com/blog/agent-evaluation-frameworks-2026](https://futureagi.com/blog/agent-evaluation-frameworks-2026)
- **Turion.ai (May 2026):** DeepEval + LangSmith integration tutorial — pytest-native scoring with `deepeval test run` and LangSmith tracing via `@observe` decorator. — [https://turion.ai/blog/agent-evaluation-testing-2026](https://turion.ai/blog/agent-evaluation-testing-2026)

## Gotchas

- **Aggregate scores hide regressions.** A 90% pass rate is meaningless if the regression is entirely in tool argument correctness. Always decompose.
- **Golden datasets drift.** When you change the agent's prompt, every multi-turn eval case is now simulating a conversation that won't happen. Version the dataset, or your evals give false confidence.
- **LLM-as-a-judge has its own failure modes.** Judges are non-deterministic, biased toward longer outputs, and can be gamed. Deterministic checks (schema validation, exact-match on tool names) should replace LLM judges where possible.
- **Eval cost can exceed inference cost.** Running a full trace through an LLM judge for every eval case adds significant compute. Budget for it — and prioritize trajectory-level scoring for high-risk agents, not every call.
- **Production traffic is your best eval data.** Synthetic data covers gaps. Real production logs cover reality. Teams that don't instrument their agents in production have no path to an accurate golden dataset.
