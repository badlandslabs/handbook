# S-2279 · The Eval Harness Stack — When You Ship Agents and Hope for the Best

You have agents in production. You have no systematic way to know whether they're failing. Your benchmark said 95% — but that benchmark was a curated set of happy-path inputs, and production users are creative in ways your test suite never anticipated. The eval harness stack is how teams stop hoping and start measuring agent quality across the full surface: before deploy, during review, and after shipping.

## Forces

- **No single eval layer catches everything.** Anthropic's production playbook calls out three distinct layers — automated evals (pre-deployment), manual transcript review (early access), and production monitoring (post-deployment) — each catching failures the others miss. Teams that build only one layer have blind spots the others fill.
- **Scaffold matters as much as model.** AlphaEval (arXiv:2604.12162) analyzed 100 production agent deployments and found that in 41% of cases, scaffold design — not model quality — determined whether an agent succeeded or failed on a given task. The tool definitions, prompt structure, and orchestration logic around the model are as important as the model itself, yet most teams only benchmark the model.
- **Eval quality determines iteration velocity.** The KDD 2026 Nubank paper studied five production customer-support agent deployments at 100M+ user scale and found that evaluation pipeline quality was the single biggest lever on how fast teams could iterate. Teams with systematic evals shipped improvements in days; teams without them spent weeks triangulating whether a change actually helped.
- **Standard benchmarks don't reflect production complexity.** Existing agent benchmarks (SWE-bench, WebArena, OSWorld) evaluate agents on retrospectively curated tasks with well-specified requirements — conditions that diverge fundamentally from production, where requirements contain implicit constraints, inputs are heterogeneous multi-modal documents, and success is judged by domain experts whose standards evolve over time (AlphaEval, 2026).

## The move

Build a layered evaluation harness that operates across three phases — offline, regression, and online — with metrics tuned to agent-specific dimensions that standard LLM benchmarks miss.

**Offline evaluation — before deploy:**
- Curate a golden dataset from production failures and edge cases, not just ideal inputs. Refresh quarterly: add 10–20 new queries from new production failures, rebalance categories, and version with semantic versioning (datasops, 2025).
- Run automated metric suites targeting agent-specific dimensions: tool selection accuracy (did the agent call the right tool?), planning quality (was task decomposition coherent?), step-level faithfulness (does the reasoning trajectory match the output?), and final task completion.
- Use LLM-as-judge for cost-effective scaling, but calibrate against human annotations first. Microsoft's llm-as-judge framework and RAGAS metrics (faithfulness, answer relevancy, context precision) provide structured starting points. The KDD 2026 Nubank team used GEPA-optimized LLM judges with measured inter-rater agreement — calibrating judge scores against domain expert annotations before shipping to production scale.

**Regression testing — on every PR:**
- Gate CI/CD pipelines with automated eval suites. AgentMarketCap (2026) found that teams integrating evals into CI/CD reached stable production operation three times faster than teams that did reactive diagnosis post-deploy. Amazon's aws-labs/agent-evaluation framework (Apache-2.0, 370+ GitHub stars) is built specifically for orchestrating concurrent multi-turn conversations with agents and plugging into existing CI/CD pipelines.
- Run golden dataset regressions: any production failure that reveals a genuine gap should immediately produce a new test case in the eval suite. The arXiv:2606.08867 (Nubank) approach builds ideation-to-production validation loops where production failures directly feed evaluation criteria.

**Online monitoring — after shipping:**
- Trace production conversations at sample rate. LangSmith, Langfuse, or Phoenix provide open-source LLM observability for cost, latency, and quality drift tracking.
- Detect distribution shift: when production input patterns diverge from training eval distribution, alert and trigger golden dataset refresh.
- Capture step-level signals, not just final outputs. Agent-as-a-judge frameworks (arXiv:2508.02994) extend LLM-as-judge by evaluating reasoning trajectories — not just whether the final answer is correct, but whether the agent's intermediate steps were sound. This catches subtle failures where the agent gets the right answer for the wrong reason.

## Evidence

- **Research paper (KDD 2026):** Evaluation-driven agent framework at Nubank (100M+ users, five production deployments) achieved tNPS gains of +37pp in card delivery and +40pp in debt management by building systematic eval pipelines. The paper directly links eval quality to iteration velocity — "evaluation pipeline quality directly determines iteration velocity." — [arXiv:2606.08867](https://arxiv.org/html/2606.08867v1)
- **Research paper (arXiv 2026):** AlphaEval analyzed 100+ production agent deployments and identified six production-specific failure modes that standard benchmarks miss entirely. Found that scaffold design accounts for 41% of agent success variance — not model quality. Established a requirement-to-benchmark construction framework for production-complexity-preserving evals. — [arXiv:2604.12162](https://arxiv.org/pdf/2604.12162)
- **Engineering blog (Thoughtworks, June 2026):** Practical framework showing why traditional deterministic testing fails for probabilistic AI agents, with a three-layer eval approach mapping to pre-deployment, early-access, and production phases. Notes that 95% of AI projects fail — primarily due to measurement, not model capability. — [Thoughtworks Insights](https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)
- **GitHub (AWS Labs):** Open-source agent-evaluation framework (370 stars) purpose-built for orchestrating concurrent multi-turn agent conversations with CI/CD integration hooks. Supports custom evaluation hooks for integration testing alongside agent response quality. — [github.com/awslabs/agent-evaluation](https://github.com/awslabs/agent-evaluation)

## Gotchas

- **Don't eval only the final output.** Agents can arrive at correct answers through flawed reasoning. Measure the reasoning trajectory, not just the destination — step-level faithfulness catches the "right answer, wrong path" failure mode that outcome-only evals miss.
- **Golden datasets rot.** A static golden dataset built at launch will not reflect production drift six months later. Establish a cadence: add production failures to the eval suite immediately, do quarterly refreshes, and version the dataset. Without maintenance, your eval score becomes a vanity metric.
- **LLM-as-judge has position bias.** Without calibration, judges favor responses in certain positions and exhibit verbosity bias (longer answers score higher regardless of quality). Measure Spearman correlation against human annotations before trusting judge scores at scale.
