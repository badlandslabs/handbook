# S-1384 · The Agent Eval Stack — Writing the Test Before the Agent Breaks Production

You've shipped an agent. It works in demos. A week later, a customer support agent processes a $47,000 fraudulent refund, and you can't prove it was a regression because you have no eval. The problem isn't that the agent failed — it's that you had no way to measure whether it was succeeding.

## Forces

- **Agents are probabilistic; traditional QA assumes determinism.** The same input can produce different outputs, different tool-call orders, different reasoning paths. You can't assert against a single expected value.
- **Outcome and trajectory are different failure modes.** An agent can reach the right final answer via a path that will fail under slightly different inputs. Outcome scoring misses this. Trajectory scoring catches regressions outcome scores won't surface.
- **The observability-eval gap is enormous.** 89% of teams running agents have observability. Only 52% have evaluation frameworks — a 37-point gap that explains why model upgrades "feel like rolling dice."
- **40% of organizations see significant quality regressions within 90 days of production deployment.** Without a baseline, you can't tell which upgrade caused it.

## The Move

### Build a layered eval system across three levels

**End-to-end eval** — does the agent complete the task? Binary or rubric-scored. Ask: "Did the customer ticket get resolved?"

**Trajectory-level eval** — was the path efficient and safe? Tool-call ordering, step count, argument correctness, whether it recovered from errors. Braintrust's 2026 research confirms trajectory scoring catches regressions that outcome scoring misses.

**Component-level eval** — which specific part failed? Pin to the retrieval step, the tool call, the synthesis, or the handoff.

### Instrument deterministic checks AND LLM-as-judge

Use deterministic checks for verifiable facts: tool correctness (did it call the right API with the right params?), format correctness, argument validity, JSON schema adherence. Use LLM-as-judge for context-dependent quality: answer relevancy, safety, tone, whether reasoning was sound.

### Calibrate LLM-as-judge with domain rubrics

Raw LLM-as-judge achieves ~80% agreement with human evaluators, but drops to 60–70% in expert domains (legal, medical, specialized code). The fix: a 5-point rubric with concrete behavioral anchors for each score level. Without rubrics, judge agreement varies by up to 30% across different prompts for the same content.

### Use cross-model judging

If your agent runs on Claude, use GPT-4o as the judge — and vice versa. Same-model judging introduces systematic bias. RaftLabs calls this standard practice across every agent they ship.

### Curate a golden dataset from three sources

Mine production logs for real inputs that actually happened. Pull from support tickets and bug reports for edge cases. Add adversarial cases deliberately — Unicode names (O'Brien, José, 北京), null values, concurrent requests, prompt injection attempts. Real production examples beat synthetic ones; edge cases matter more than happy paths. Quality over quantity: 50–200 well-chosen cases outperform 10,000 noisy ones.

### Gate CI/CD on eval results

A regression budget is a defined performance floor — if pass rate drops below threshold on the golden dataset, block the deploy. Track tool-use distribution drift and output-distribution drift as leading indicators of degradation before human-visible failures occur.

## Evidence

- **HN Ask Thread (2025):** "How are you testing AI agents before shipping to production?" — 7 core failure modes identified across respondents: hallucination under unexpected inputs, edge case collapse (nulls, Unicode, concurrent requests), prompt injection, context length surprises, tool call loops, silent data corruption, and context misranking. — [HN #47325105](https://news.ycombinator.com/item?id=47325105)

- **RaftLabs engineering post (May 2026):** Found 52% of agent teams have evaluation frameworks vs. 89% with observability — 37-point gap. Cross-model judging identified as standard practice. GAIA benchmark top score at 61% even for frontier models. — [RaftLabs](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)

- **Microsoft AutoGen AgentEval (2024):** Three-agent eval architecture: CriticAgent defines criteria from task + example traces, QuantifierAgent scores against those criteria, verification step tests quantifier robustness. Validated on 12,500-problem math dataset and ALFWorld multi-turn environment. — [Microsoft / AutoGen](https://microsoft.github.io/autogen/0.2/blog/2024/06/21/AgentEval)

- **Confident AI / DeepEval (June 2026):** Core metrics for agent eval: task completion, step efficiency, argument correctness, tool correctness, plan adherence, reasoning quality, safety, latency, cost. Tracing ties every score to the exact span that caused it. — [Confident AI](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

- **Galileo AI / Braintrust research (2026):** Trajectory scoring catches regressions outcome scoring misses — an agent can succeed at the final step while taking a path that fails under slightly different inputs. Always run both. — [Galileo AI](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Maxim AI golden dataset guide (2025–2026):** Three-layer eval-set design: core set (50–200 cases), edge-case set (30–100), production-sampled set (10–50). Version and maintain as a living artifact, not a one-time snapshot. — [Maxim AI](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide)

## Gotchas

- **Eval once and call it done.** Golden datasets decay. After 4–12 weeks, production traffic diverges from your calibration set. Re-sample production logs quarterly.
- **Using the same model for agent and judge.** Introduces systematic bias — the judge rates its own outputs favorably. Always cross-model.
- **Scoring only the final answer.** Trajectory failures (wrong tool, wrong order, unnecessary loops) can produce correct-looking final outputs. Score the path, not just the destination.
- **Treating eval as a pre-deployment gate only.** Online eval (scoring every production execution) catches regressions that offline eval misses — particularly drift in tool-use patterns and output distributions.
- **Optimizing for benchmark scores, not production behavior.** Standard benchmarks (GAIA, WebArena) tell you baseline capability, not whether your agent survives your specific production environment. Domain-specific test suites are required in addition to generic benchmarks.
