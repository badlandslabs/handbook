# S-1904 · The Eval Stack — Knowing Whether Your Agent Actually Worked

You ship a new agent. Task completion looks fine in staging. Two weeks later, a customer report surfaces a class of failures you never caught: the agent has been confidently wrong, returning 200 OKs with hallucinated facts. Your eval suite was green. The problem is your evals were testing the wrong thing. This is the eval stack problem: most teams don't evaluate their agent — they evaluate a proxy of it.

## Forces

- **Endpoint vs. trajectory evaluation.** Standard LLM evals score a single prompt-response pair. Agent evals must score multi-step workflows where errors compound across dozens of steps. A correct final answer via broken steps is different from a correct final answer via sound steps.
- **Non-determinism cascades.** A chat model's temperature affects one generation. An agent's temperature affects every tool call, every retry, every decision to read another file. Small variations cascade into wildly different trajectories and costs.
- **Operating envelope vs. quality.** Agents can be slow-but-correct, fast-but-wrong, cheap-but-incomplete. Task completion alone is insufficient — you also need cost, latency, and step-count budgets.
- **The circular judge problem.** LLM-as-judge is the dominant approach, but using an LLM to evaluate an LLM introduces alignment drift. "Metric green, user red" is a documented failure mode.
- **Eval infrastructure is expensive to build right.** Docker sandboxes, parallel evaluation workers, trace collection, benchmark harnesses — the infra to run evals reliably is often 10x the cost of the agent itself.

## The Move

Separate evaluation into three independent layers, each with its own grader, and run them in a continuous pipeline.

### Layer 1 — End-to-end task completion

- Run agents through full trajectories against golden datasets (known inputs with known correct outputs)
- Use **deterministic code-based checks first** (file changed, API called, database row updated) wherever outputs are verifiable
- Supplement with **LLM-as-judge** for subjective dimensions: relevance, clarity, instruction following
- Key metric: task completion rate (% of tasks where the agent actually solved the problem)

### Layer 2 — Component-level trace checks

- Audit individual tool calls: was the right tool selected? Were arguments correct?
- Check for **false task completion** — agent reports "done" but nothing changed
- Detect **reasoning thrash** — circular summaries or repeated failed attempts without progress
- Catch **drift from user intent** across multi-turn sessions
- Track **tool call accuracy** (% of tool calls that were necessary) and **mean tool calls per task** (efficiency)

### Layer 3 — Operating envelope monitoring

- Track cost per task, P95 latency, and token budgets per trajectory
- Set hard caps: if a task exceeds N tool calls or N tokens, terminate and flag
- Monitor **false success rate** (task completion with wrong output) separately from **false failure rate** (correct output flagged as wrong)
- Alert on cost/latency regressions, not just quality regressions

### The eval workflow

1. **Pre-deploy:** Run golden dataset + deterministic checks in CI. Gate on pass/fail thresholds. This is your regression firewall.
2. **Staging:** Run LLM-as-judge on sampled traces. Calibrate judges against human rubrics on a 20-50 case subset before trusting scores.
3. **Production:** Continuous trace collection with statistical sampling. Run online evals on production traffic for cost, latency, and qualitative signal. Human review on sampled failures.
4. **Meta-eval:** Periodically audit your judges — run agent-as-judge evaluations through themselves to detect drift. The ICML 2025 "Agent-as-a-Judge" paper formalizes this as a multi-agent evaluation framework with self-consistency checks.

### Tools in the eval stack

| Layer | Tools |
|-------|-------|
| Tracing & observability | LangSmith, Langfuse, Phoenix (Arize), Confident AI |
| Eval execution | DeepEval (Confident AI), Promptfoo, Braintrust |
| Agent benchmarks | SWE-bench (software engineering), GAIA (general assistants), Terminal-Bench, OSWorld (computer use) |
| Judge approaches | LLM-as-judge (GPT-4o, Claude as evaluator), code-based assertions, agent-as-a-judge |

## Evidence

- **Engineering blog:** Anthropic's "Demystifying Evals for AI Agents" — defines the core taxonomy: *tasks* (test cases with success criteria), *trials* (single attempts, run multiple times for variance), *graders* (logic scoring success). Emphasizes that evals compound in value over an agent's lifecycle and prevent reactive-fix loops. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **HN/Ask thread (43 comments):** "The vast majority of AI companies I talk to seem to evaluate models mostly based on vibes." — Teams bootstrapping AI-as-judge from PM-created question sets; ~20 minutes to test a new model with parallelization; multi-dimensional output testing (relevance, instruction following, hallucination rate, clarity). Bottleneck is rate-limiting, not compute. — [URL](https://news.ycombinator.com/item?id=47319587)
- **Engineering guide:** Promptfoo's agent eval guide — documents the core challenge: "Non-determinism compounds. A chat model's temperature affects one generation. An agent's temperature affects every tool call, every decision to read another file." Recommends capability tier testing (Tier 0 text → Tier 4 full autonomous agents) and separating eval of the system from eval of the model. — [URL](https://www.promptfoo.dev/docs/guides/agent-eval/)
- **Research paper:** Zhuge et al., "Agent-as-a-Judge: Evaluate Agents with Agents" (ICML 2025) — formalizes using agents as evaluators with self-consistency checks and meta-evaluation. Dataset and implementation at `github.com/metauto-ai/agent-as-a-judge`. — [URL](https://mlanthology.org/icml/2025/zhuge2025icml-agentasajudge/)
- **Company guide:** Confident AI's evaluation guide — documents false task completion as the #1 subtle failure mode: agent says "done" but nothing changed. Recommends tracking cost/latency alongside quality metrics, and calibrating LLM judges against human rubrics to detect "metric green, user red" failures. — [URL](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Don't skip deterministic checks for verifiable outputs.** If you can check whether a file was written or an API returned 200, do that before reaching for LLM-as-judge. Code-based checks are faster, cheaper, and more reliable.
- **Treat LLM-as-judge scores as ordinal, not cardinal.** A judge score of 0.7 vs 0.73 is not meaningfully different. What matters is whether the score crosses your pass/fail threshold consistently across runs. Re-running with different temperature or judge model can shift scores ±10%.
- **Golden datasets go stale.** Agent behavior changes with model updates, prompt changes, and tool changes. Re-label your golden cases quarterly or whenever you make non-trivial changes to the system.
- **Multi-agent pipelines need end-to-end eval, not just unit eval of each agent.** Two agents at 95% success = ~90% end-to-end. Eval each agent in isolation and you miss the handoff failures and error propagation that only manifest in the full pipeline.
