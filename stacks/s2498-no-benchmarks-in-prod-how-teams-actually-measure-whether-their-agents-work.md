# S-2498 · No Benchmarks in Prod · How Teams Actually Measure Whether Their Agents Work

When your agent demo works perfectly but production is a mystery — you have no idea whether it's succeeding, failing silently, or doing something entirely unanticipated, and deploying a new prompt change feels like rolling dice.

## Forces

- **The invisible regression problem:** Retrieval metrics look healthy, the agent completes tasks, but draws inferences the source data never made. No alarm fires. The system drifts silently until a user complains.
- **Stochastic outputs break binary assertions:** Traditional tests assume same-input-same-output. Agents produce different trajectories each run. A "pass" rate of 85% is often the realistic ceiling, not a failure signal.
- **Cascade failures are invisible to single-turn metrics:** An agent correctly handles step one, then silently skips step two because an API returned an unexpected error format. The final output looks fine. The error never surfaced.
- **The evaluation gap between lab and production:** AgentBench, SWE-bench, GAIA, and τ-bench tell you how agents perform on academic tasks. They say almost nothing about whether YOUR agent does what YOUR users need.
- **Production input distribution is unknowable at design time:** Teams engineer test cases from imagination. Real users find Unicode names (O'Brien, José, 北京), null values, concurrent requests, and adversarial prompts that no one anticipated.

## The Move

Build a layered evaluation system across three phases: development regression testing, CI/CD quality gates, and production monitoring — with feedback flowing from production failures back into the development suite.

**Key implementation points:**

- **Build a golden dataset from two sources:** (1) Handcrafted cases covering happy paths, known edge cases, and safety boundaries — start with 20-50 high-signal cases, not hundreds. (2) Production traces that expose failures — every real user failure is a test case you could not have invented. The highest-value regression set is harvested, not imagined.
- **Use LLM-as-judge for scoring, not just humans:** A second LLM evaluates agent outputs against rubric-defined criteria (task completion, tool selection correctness, safety boundary compliance). Keeps the loop fast enough to run on every commit. Use a different model than the one being evaluated to avoid gaming.
- **Track trajectory-level metrics, not just final outputs:** Measure steps-to-completion, tool call accuracy, plan quality, and error recovery — not just whether the final answer looks right. A right answer via wrong reasoning is a latent bug.
- **Gate CI/CD with evaluation, not just linting:** Every prompt change, model swap, or tool refactor must run against the golden dataset and pass score thresholds before merging. Report which cases improved, which regressed, and by how much. Version test datasets alongside code in the same commit.
- **Sample production traces continuously and feed low-scoring ones back into the golden set:** Set score thresholds; when live traces fall below, turn them into regression cases. This closes the loop between what users actually send and what the test suite validates.
- **Distinguish semantic failures from functional failures:** Observability tools catch the latter (timeouts, API errors). For the former — agent looks like it worked but didn't — you need trace-level inspection, semantic scoring, and automated clustering of similar failure modes (LangSmith Insights Agent, Langfuse, or Lemma are purpose-built for this).

## Evidence

- **HN Ask discussion (harperlabs):** 50+ test cases covering 7 failure modes — hallucination under unexpected inputs, edge case collapse (null values, Unicode names, empty fields), prompt injection via external content, context limit surprises, and cascade failures where tool call errors compound silently. Gartner projects 40%+ of AI agent projects will fail by 2027; a January 2026 prompt injection in a customer support agent processed a $47,000 fraudulent refund. — [HN Ask HN #47325105](https://news.ycombinator.com/item?id=47325105)
- **Braintrust practical framework:** Identifies two distinct agent layers — the reasoning layer (plan quality, tool selection) and the action layer (API calls, tool execution) — requiring separate evaluation strategies. Their evaluation pipeline version-controls datasets alongside agent code, runs automated scoring in CI, and feeds production traces back into the test suite. — [Braintrust: AI Agent Evaluation Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Arthur.ai regression loop:** Production failure → full execution trace capture → test case extraction → golden dataset addition → CI/CD release gate. Captures entire trajectories, not just final outputs, because correct final answers via wrong reasoning are latent reliability risks. — [Arthur.ai: Regression Test Datasets From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **OpenAI evaluation guidance (via Melanated In Tech synthesis):** Golden set runs should answer: did the agent complete the intended task, use the right tool, stop when information was missing, respect permissions and approval boundaries, and regress on quality/cost/latency. — [Golden Set Playbook](https://melanatedintech.com/knowledge/agent-evaluation-golden-set)
- **LangSmith production monitoring:** Automated clustering of live traces surfaces usage patterns, error modes (incorrect tool selection, retrieval failures, intent misunderstanding), and edge cases — without requiring engineers to specify what to look for upfront. — [LangChain: Production Monitoring](https://www.langchain.com/blog/production-monitoring)
- **LangWatch Evaluation Wizard:** Demonstrates that you don't need massive datasets to start — the wizard generates a starting set from traces or synthetic data, and LLM-as-judge can score quality checks without manual labeling. — [LangWatch: Agent Evaluation Framework](https://langwatch.ai/blog/framework-for-evaluating-agents)
- **ArXiv survey (2025):** A systematic survey of LLM agent evaluation taxonomy across two dimensions — what to evaluate (behavior, capabilities, reliability, safety) and how to evaluate (interaction modes, benchmarks, metric computation, tooling) — noting that enterprise-specific challenges like role-based access, reliability guarantees, and compliance are often overlooked in current research. — [arXiv: Evaluation and Benchmarking of LLM Agents: A Survey (2507.21504)](https://arxiv.org/abs/2507.21504)

## Gotchas

- **Using the same model as both generator and judge** — it will score its own outputs generously. Use a different model class for evaluation.
- **Only testing happy paths in the golden set** — the real value is edge cases and adversarial inputs, which are impossible to engineer from imagination alone. Harvest from production failures.
- **Tracking pass/fail rate without trajectory metrics** — a 90% final-answer accuracy rate conceals that the agent took 3× more steps than necessary, called the wrong tool twice, and recovered by luck. Measure the path, not just the destination.
- **No semantic failure detection in production** — functional observability (errors, timeouts) misses agents that look fine but produce subtly wrong outputs. You need trace-level inspection and automated semantic scoring to catch these.
- **Evaluating once at launch** — evaluation is a continuous loop. Prompt changes, model upgrades, and tool API changes all introduce regressions that only surface in production unless you gate them in CI.
