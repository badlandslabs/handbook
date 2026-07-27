# S-1725 · The Attribution Gap Stack — When Your Agent Fails and You Can't Tell Why

Your agent bombed on a production task. You don't know if the model chose wrong, the prompt misled it, the tool integration broke, or the orchestration logic sent it down the wrong path. You run it again and it works. You ship the "fix" — whatever you changed — and two weeks later the same failure mode resurfaces. You're flying blind because your evaluation infrastructure stops at "it worked" and "it didn't."

You reach for this when you can't reproduce a failure, can't attribute a regression to a specific layer, or can't tell whether a model update actually improved your agent.

## Forces

- **General benchmarks and production tasks are mismatched.** Agents score well on SWE-bench, GAIA, and MMLU but bomb on loosely-worded business requirements that no benchmark covers. AlphaEval (arXiv 2604.12162, April 2026) documents this: 63% of companies report low confidence that model updates actually improve their deployed products. The evaluation that ships with your agent is measuring the wrong thing.
- **Failure attribution is a multi-layer problem.** A degraded outcome can trace to the model's reasoning, the prompt's framing, the tool schema, the orchestration logic, the API latency, or the user's ambiguous intent — and they compound. Teams collapse all of these into "the agent failed" and change the model, which often misses the real cause.
- **Developer testing is not evaluation.** The same survey found 70.4% of teams rely on developers testing agents as a side task. This is ad hoc, non-reproducible, and unrepresentative of the diversity of real inputs. It catches obvious regressions but not subtle capability regressions across task types.
- **Production signals are noisy and delayed.** Users don't report failures cleanly — they work around them, switch tasks, or stop using the feature. By the time you notice a pattern, the session context is gone.

## The Move

Treat evaluation as a layered, attributive system — not a single pass/fail gate but a decomposition that isolates failure modes at each layer.

**1. Decompose the agent into evaluation layers.**
Separate concerns: (a) the model's core capabilities (reasoning, instruction-following, factual accuracy), (b) the orchestration layer's tool selection and sequencing, (c) the tool integrations' correctness, and (d) end-to-end task success. Run targeted evals per layer so a regression in layer (b) doesn't trigger a full model swap.

**2. Build a task taxonomy before building evals.**
AlphaEval's framework distills production requirements into 4 stages: requirement understanding → domain knowledge retrieval → task decomposition → execution. Map your agent's failure modes to this taxonomy. A task that fails at "requirement understanding" needs a different fix than one that fails at "execution."

**3. Track production signals with semantic awareness.**
Traditional observability catches crashes and timeouts. What it misses is semantic failure: the agent completed, the API returned 200, but the output was subtly wrong. Lemma (YC W25) specifically addresses this — catching silent failures where the agent delivered something that looked plausible but missed the actual intent. Instrument your agent to capture semantic correctness signals, not just technical success.

**4. Build regression suites per task cluster.**
Cluster your agent's inputs into task types (e.g., data extraction, classification, code generation, synthesis). For each cluster, maintain a golden set of inputs with expected outputs. Run these on every model update. A 2% accuracy drop on a minor cluster is often invisible without this — and often symptomatic of a scaffolding change, not the model.

**5. Use systematic failure classification.**
When a failure occurs, route it through a taxonomy before attempting a fix: model capability gap, prompt misalignment, tool error, orchestration misrouting, ambiguous input, or external dependency failure. Document each classification with the session ID and input. This builds institutional knowledge that prevents repeated misdiagnosis.

## Evidence

- **AlphaEval research paper:** Found that 63% of companies lack confidence in model-update impact on their agents; 25.9% have no explicit evaluation criteria; 80%+ of agent deployments are in production or pilot phases despite this. Proposes a 4-stage requirement-to-benchmark pipeline for production-grounded eval. — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162)
- **Anthropic SWE-bench engineering post:** Achieved 49% on SWE-bench Verified (state-of-the-art at the time) through a specific agent scaffold around Claude 3.5 Sonnet — multi-round tool use, structured file editing, Bash command orchestration. The gain came from agent architecture, not the base model alone. — [Anthropic Engineering](https://www.anthropic.com/engineering/swe-bench-sonnet)
- **Survey of LLM agent evaluation:** Systematic review of evaluation methods across two dimensions: objectives (behavior, capability, reliability, safety) and process (interaction modes, benchmarks, metrics). Notes the fragmentation in how teams approach agent eval and the gap between research benchmarks and production realities. — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)
- **Lemma (YC W25):** Production monitoring for AI agents that catches semantic failures invisible to traditional observability. Specifically targets the case where the agent completes without error but delivers the wrong result. — [Y Combinator](https://www.ycombinator.com/companies/uselemma)
- **Agent-evals Show HN:** Built as a Claude Skill to make systematic evaluation accessible to engineering teams without data science backgrounds. Notes that eval fluency is the main bottleneck for startups building agents. — [HN item #48013746](https://news.mcan.sh/item/48013746)

## Gotchas

- **A green unit-test suite doesn't validate your agent.** Unit tests verify code correctness; they say nothing about whether the agent does the right thing given your specific inputs. You need behavioral evals on production-representative data.
- **Changing the model is the easiest but often wrong fix.** Most agent failures in production trace to orchestration, tool integration, or prompt framing — not the model's core capability. Evaluate the layer before swapping the model.
- **Human eval is slow but irreplaceable.** Automated metrics (BLEU, ROUGE) are poor proxies for agent quality. Human eval on a sampled subset of production inputs remains the gold standard for task correctness. Use automated evals for regression detection at scale; use human eval for calibration and validation of automated metrics.
- **Silent failures outnumber loud ones in production.** If your only failure signal is an exception or timeout, you're missing the majority of degraded outcomes. Instrument for semantic correctness.
