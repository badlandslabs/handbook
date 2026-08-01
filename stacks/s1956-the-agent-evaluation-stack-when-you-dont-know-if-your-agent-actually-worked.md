# S-1956 · The Agent Evaluation Stack — When You Don't Know If Your Agent Actually Worked

Deploying an agent without evals is flying blind. The demo worked. The happy path works. Then it processes a $47,000 fraudulent refund through a prompt injection, or silently misbehaves when the context window fills up, or invents data when the input is slightly off-format. Without evaluation infrastructure, you discover these failures in production — after the damage.

## Forces

- **Non-determinism vs. verification** — a single successful run proves nothing. Agents vary across attempts, so one pass is not a validation. You need multiple trials to establish reliability.
- **Output vs. outcome** — traditional LLM evals check if text matches. Agent evals must check if the world changed correctly (database state, file system, API calls). The output can look perfect while the action is wrong.
- **Scalability vs. coverage** — writing test cases by hand is brittle and doesn't scale. But the space of real inputs explodes combinatorially, and you can't anticipate every edge case before deployment.
- **Eval cost vs. confidence** — human graders are the gold standard but cost $5–50 per task. Running them on every commit is infeasible. Cheap automated evals catch regressions but miss nuance.
- **Eval drift vs. business evolution** — benchmarks are built once; production requirements shift. An eval suite that validated the agent six months ago may no longer reflect what the business actually needs.

## The move

**Build a layered evaluation pipeline with execution-based verification as the foundation.**

### Define success by end-state, not output

The agent's final message is not the success criterion. Verify the actual state change:

- **Code agents**: run the test suite, check lint, verify the file was written correctly
- **Data agents**: re-run the query, compare against a known-good baseline
- **Customer-facing agents**: check the ticket status, DB record, or email sent
- **Research agents**: verify cited sources are real and numbers check out

> "tau-bench checks the database state, SWE-Bench runs the test suite, tau2-bench's pass^k measures whether the agent succeeds reliably across attempts rather than once. A benchmark that only checks tool-call syntax or final text would pass agents that look right and do the wrong thing." — [InfoQ, March 2026](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

### Layer three grader types (Anthropic's framework)

| Grader type | Speed | Cost | Reliability | Use for |
|---|---|---|---|---|
| **Code-based** | Fast | Cheap | Deterministic | Tool call arguments, format checks, DB state assertions |
| **Model-based** (LLM-as-judge) | Medium | Per-call | Non-deterministic | Tone, reasoning quality, contextual appropriateness |
| **Human** | Slow | Expensive | Gold standard | Calibration, edge case review, final sign-off |

Start with code graders for everything verifiable. Add LLM-as-judge for qualities that need judgment. Reserve humans for calibration — not production scoring.

> "Code-based graders are fast, cheap, and objective but brittle. Model-based graders are flexible and handle nuance but are non-deterministic. Human graders are the gold standard but expensive and slow. We recommend combining all three." — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Harvest eval data from production traces, not thought experiments

The highest-quality test cases come from real agent runs:

1. **Capture every production trace** — store full transcripts (input, tool calls, reasoning, outputs, final state) in a trace store
2. **Convert failures to test cases** — when a production failure occurs, write the failing input + expected end-state as a permanent test case
3. **Adversarial perturbation** — take successful production traces and mutate inputs (nulls, Unicode names like O'Brien or 北京, empty fields, concurrent requests) to stress-test robustness
4. **LLM-generated test cases** — use a separate LLM to generate edge-case inputs from your domain description; AWS agent-evaluation framework (369 stars) uses an LLM evaluator agent to orchestrate multi-turn conversation test scenarios against your agent

> "The eval loop: production traces become test cases, evals run ahead of deploys. Eval data is not authored — it's harvested." — [Braintrust](https://www.braintrust.dev/articles/how-to-eval)

### Run evals in CI on every commit; gate deploys on pass rate

Automated evaluation must be part of the deployment pipeline:

- **Pre-deploy gate**: run full eval suite on every PR/commit; block merge if pass rate drops below threshold
- **Shadow mode**: deploy the new agent version alongside the old one in shadow mode — compare outputs on real traffic without user impact
- **Continuous production monitoring**: lightweight sampling of live traces scored by LLM-as-judge; alert on degradation

> "Pre-deployment validation answers whether you should release this agent version. Run comprehensive test suites covering edge cases, stress scenarios, and adversarial inputs to establish baseline capabilities. Continuous production monitoring tracks performance drift over time." — [LangWatch](https://langwatch.ai/blog/framework-for-evaluating-agents)

### Measure pass^k, not pass@1

Because agents are non-deterministic, run k trials and measure what fraction succeed. A pass@1 of 90% might mean 90% of users see a working agent, or it might mean 100% of users see it work 90% of the time. These are very different product experiences.

## Evidence

- **Anthropic engineering post:** Detailed breakdown of code-based, model-based, and human graders with guidance on when to use each. Covers the grader/assertion/transcript/task/trial vocabulary that became standard framing. — [Anthropic Engineering: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **AlphaEval (arXiv 2604.12162, April 2026):** Survey of 27 AI product companies: 63% report low confidence that model updates actually improve their products; 25.9% have no explicit evaluation criteria; 70.4% rely on developers performing testing as a side task. Proposes production-grounded benchmark of 94 real tasks from 7 companies across 6 occupational domains. — [AlphaEval: Evaluating Agents in Production](https://arxiv.org/pdf/2604.12162)
- **Hacker News / Harper Labs (2025):** Field report on 7 core agent failure modes discovered from production deployments: hallucination under unexpected inputs, edge case collapse (nulls, Unicode, empty fields), prompt injection, context limit surprises, tool call failures, slow responses, cascading failures. Real incident: Jan 2026 — prompt injection in customer support agent processed a $47,000 fraudulent refund. — [HN Ask: How are you testing AI agents before shipping to production?](https://news.ycombinator.com/item?id=47325105)
- **Braintrust:** Notion achieved a 10x improvement in issue discovery velocity after adopting structured evaluation with data+task+scorer patterns. Describes the trace-to-test-case pipeline: production traces become the eval dataset, evals run ahead of deploys as a quality gate. — [How to evaluate LLMs and AI agents in production](https://www.braintrust.dev/articles/how-to-eval)
- **AWS Labs agent-evaluation (369 stars, Apache 2.0):** Open-source generative-AI-powered framework where an LLM evaluator agent orchestrates multi-turn conversations against the target agent, evaluating responses during conversation. Supports Amazon Bedrock, Q Business, and SageMaker out of the box; extensible to custom agents. — [github.com/awslabs/agent-evaluation](https://github.com/awslabs/agent-evaluation)

## Gotchas

- **Don't write eval cases from intuition.** Authored test cases miss real failure modes. Harvest from production traces, especially failures. The 7 failure modes above (Unicode names, null handling, context overflow) almost never appear in manually authored suites.
- **LLM-as-judge has a.self-confidence problem.** Models are reluctant to fail other models' outputs. Calibrate your judge against human-labeled examples; without calibration, pass rates will be artificially high.
- **A single trial is not a measurement.** Always use pass^k (≥10 trials) for non-deterministic agents. A one-off success proves nothing about reliability.
- **Eval suite staleness is invisible.** When business requirements change, old evals silently stop reflecting what "good" means. Treat eval maintenance as a first-class engineering task, not an afterthought.
- **Don't evaluate text, evaluate state.** Checking whether the agent's final message looks correct misses the most dangerous failure mode: the agent says the right thing but does the wrong thing (wrong database record, wrong file, wrong API call).
