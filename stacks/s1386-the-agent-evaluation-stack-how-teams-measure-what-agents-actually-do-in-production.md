# S-1386 · The Agent Evaluation Stack — How Teams Measure What Agents Actually Do in Production

The paradox: agents are some of the most expensive software to operate and the least-measured. A prompt change that "feels better" ships to production. Two days later, a class of queries starts failing silently. You have no idea until a user complains. This is the agent evaluation problem: building the measurement infrastructure to catch regressions before users do, and to make the case for quality improvements with numbers, not vibes.

## Forces

- Agents are non-deterministic in ways normal software isn't — a prompt change, a model swap, a retrieval tweak can shift behavior in ways not obvious from a few hand-tested examples
- Existing benchmarks (MMLU, HumanEval, etc.) measure general capabilities, not production-specific behavior — they saturate quickly and don't reflect the actual task your agent runs
- The "feel better" heuristic is dangerously misleading for agents because output quality is multidimensional and subjective
- Teams build agents faster than they build the infrastructure to measure them, creating a growing quality debt

## The Move

Build a **three-layer eval harness** that runs on both curated golden data and live production traces:

1. **Offline layer (golden dataset):** A held-out suite of representative queries with known expected outputs. Run against any candidate version (new model, new prompt, new retrieval) to catch regressions before deploy. Use deterministic scorers where possible (exact match, regex, code execution) and LLM-as-judge for nuanced qualities (tone, coherence, policy compliance). A handful of high-quality examples goes further than thousands of mediocre ones.

2. **Shadow layer (production sampling):** A slice of live traffic replayed against candidate versions continuously. Catches drift that only appears on real user queries — the long tail of edge cases that never make it into a curated set. This is where you find the failure modes that "felt fine" in offline testing.

3. **Systematic review layer:** Every real user failure gets added to the golden set. Build a workflow (Slack bot, issue template) so anyone on the team can log a failure with the input, the bad output, and the expected output. This is the most reliable way to grow coverage over time.

**What to measure at the step level (component):**
- Tool selection correctness — did the agent call the right tool?
- Tool argument construction — were the parameters correct?
- Retrieval relevance — did the retrieved context actually help?
- Handoff correctness — did multi-agent handoffs preserve state?

**What to measure at the end-to-end level (outcome):**
- Task completion rate — did the agent finish the job?
- Response quality (LLM-as-judge) — helpfulness, accuracy, coherence
- Policy/safety compliance — did the agent avoid disallowed actions?
- Operating envelope — cost per task, latency, step/token budget

**The golden dataset itself:**
- Start small: 20–50 well-chosen examples covering happy paths, edge cases, and known failure modes
- Each entry = prompt + input context + expected output + metadata (task type, difficulty, domain)
- Version the dataset alongside agent code; a change to the eval set is a code reviewable artifact
- Align with governance frameworks (NIST AI RMF, EU AI Act) so evals double as compliance evidence

## Evidence

- **Anthropic Engineering:** Their eval framework appendix recommends Braintrust, LangSmith, Ragas, and Arize-Phoenix, noting that "the right choice depends on your agent type" and that production evaluation of agents requires evaluating both end-to-end outcomes and individual tool-calling steps. They worked with customers including Stripe, Shopify, and Bolt to develop eval practices in production. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **AlphaEval (GAIR-NLP, 2026):** A production-grounded eval framework covering 94 tasks from 7 companies across 6 O\*NET occupational domains. Key finding: the best agent scored 64.41/100 on real-world production requirements — well below human expert baselines. Identified six production-specific failure modes and showed that scaffold/architecture choices matter as much as model choice. — [github.com/GAIR-NLP/AlphaEval](https://github.com/GAIR-NLP/AlphaEval) | [arxiv.org/abs/2604.12162](https://arxiv.org/abs/2604.12162)
- **Braintrust (production eval guide):** Documents the "velocity paradox" from working with Notion's AI team — eval-driven iteration improved AI feature quality 10x over six months by making quality measurable. Recommends data + task + scorers as the core eval primitive, with two scorer types: code-based for deterministic checks and LLM-as-judge for nuanced qualities. — [braintrust.dev/articles/how-to-eval](https://www.braintrust.dev/articles/how-to-eval)
- **Skill Trek (Apr 2026):** "The dirty secret of LLM evaluation is that most eval harnesses measure the wrong thing. They test the model on a fixed golden dataset, catch up to the last known failure mode, and miss everything that actually happens in production." Documents the three-layer approach (offline + shadow + systematic review) as the minimum viable production eval infrastructure. — [skilltrek.dev/blog/eval-harness-production](https://www.skilltrek.dev/blog/eval-harness-production)
- **SAP Labs / KDD 2025:** Comprehensive survey establishing a two-dimensional taxonomy — evaluation objectives (behavior, capabilities, reliability, safety) and evaluation process (interaction modes, benchmarks, metrics, tooling). Highlights enterprise challenges: role-based access, reliability guarantees, dynamic long-horizon interactions, and compliance. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **Confident AI:** "Metrics green, user red" — surfaces the gap between component-level scores and actual user satisfaction. Recommends human rubrics on a sample of traces to calibrate LLM-as-judge. Notes that stochasticity means critical scenarios need multiple runs, not a single pass/fail. — [confident-ai.com/blog/definitive-ai-agent-evaluation-guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Golden dataset staleness:** A fixed eval set catches regressions on known failure modes but misses new ones. The only fix is a systematic review workflow that converts every real failure into an eval entry — no manual gatekeeping, make it part of the incident response flow.
- **LLM-as-judge is not neutral:** It inherits the biases of the judge model and can agree with a wrong answer. Calibrate it against human-labeled samples; don't treat its scores as ground truth.
- **Benchmark saturation:** Published benchmarks (MMLU, HumanEval) saturate quickly on frontier models. They measure general capability, not task-specific production quality. Build your own benchmarks.
- **Single-run pass/fail is misleading:** Agents are stochastic. Run each eval scenario 3–5 times and report the distribution, not just pass/fail. A "passing" eval that passes 30% of the time is not a passing eval.
- **Measuring the wrong thing:** Throughput and step count are easy to measure but don't correlate with quality. Always pair operational metrics (cost, latency) with quality metrics (task completion, accuracy).
