# S-2544 · The Agent Evaluation Stack — When Your Agent Passed the Benchmark But Failed in Production

{You shipped an agent. It scored well on your test set. It fails silently in production — returns the wrong data, takes 47 steps instead of 3, calls the wrong tool at the wrong time, and nobody notices until a customer complains. The benchmark told you the engine was powerful; the evaluation stack tells you whether the system actually works.}

## Forces

- **Benchmarks measure engines, not systems.** MMLU, GSM8K, HumanEval — these score the model's knowledge in isolation. Agents plan, call tools, maintain state, and adapt across turns. Single-turn accuracy and classical NLP metrics (BLEU, ROUGE) don't capture how agents fail in practice.
- **Evaluation is systematically undervalued until it's too late.** The MAP study found that 74% of deployed agents still rely on human evaluation. MIT found 95% of AI agents fail in production — not from bad models, but from lack of observability and evaluation. Yet only 5% of teams cite tool calling accuracy as their top challenge; 37% cite reliability. The gap between what teams measure and what actually breaks is wide.
- **The benchmark paradox.** Passing an offline benchmark gives false confidence. Production agent behavior is path-dependent — the same agent can succeed or fail based on tool availability, state history, and step order that no curated test set captures. Yet without benchmarks, you can't regression-test before deploy.

## The Move

Build a three-layer evaluation stack: offline eval harness in CI, runtime guardrails via LLM-as-judge, and human sampling for drift detection. Treat evaluation as a production system, not a research checkbox.

### Offline Eval Harness (CI Gate)

- Run a **golden dataset** of task cases with known expected outputs before every deploy. Minimum 30–50 cases covering happy paths, edge cases, and known failure modes.
- Use **LLM-as-judge** to score agent outputs automatically — faster than human review, repeatable, git-diffable. Calibrate the judge model annually against human labels.
- Track **trajectory metrics**: step count, tool call count, token usage, cost per task, latency. A slow correct answer may still be a regression.
- Supplement with **synthetic test generation** — prompt the agent to generate adversarial cases for itself. Anthropic's tools-for-agents post shows using Claude to optimize its own tool descriptions, which also generates test cases.
- Use **trace replay** for regression: capture a production trace that failed, add it to the golden dataset, verify the fix before shipping.

### Runtime Guardrails (LLM-as-Judge at Inference Time)

- More than 57% of surveyed production agent teams now use judge LLMs at runtime for quality gating, hallucination defense, and tool-call verification — LLM-as-judge has crossed from eval harness into load-bearing infrastructure.
- Two judge tiers: **large proprietary judges** (GPT-4o, Claude 3.7 Sonnet) for high-stakes final verification; **small distilled judges** (Prometheus 2 7B, Patronus Lynx 8B) for high-throughput inline checks at each step. Small models deliver ~97% cost reduction with ~0.88 correlation to human judgment on inline checks.
- Six runtime patterns: offline eval (batch CI), online runtime verifier (per-step gate), self-consistency loops (multiple rollouts → vote), Reflexion (critique → revise), Constitutional AI / RLAIF (policy-aligned judge), and inference-time reward models. Choose based on latency budget and stakes.
- **Key distinction from offline eval:** runtime judges add latency (50–500ms per check) and cost — budget accordingly. Not every step needs a judge; gate only at decision boundaries.

### Human-in-the-Loop Sampling (Drift Detection)

- Sample 5–10% of production traces for human review. Random sampling catches novel failure modes that neither automated eval nor known-case coverage finds.
- Use **hybrid evaluation pipelines**: automated scoring (trace analysis, LLM-as-judge) at scale for repeatability + human judgment for tone, trust, and contextual appropriateness.
- Operational constraints are first-class evaluation targets: latency, cost per task, token efficiency, tool reliability, and policy compliance. These are observable and can be regression-tested.
- Separate **agent evaluation** from **model evaluation**: evaluate the system's end-to-end behavior in dynamic environments, not just the model's knowledge in isolation.

## Evidence

- **Research survey (MAP Study):** Of 306 survey responses and 20 in-depth case studies across 26 domains, 70% of deployed agents use off-the-shelf models. 68% of agents execute 10 or fewer steps before human intervention. 74% rely on human evaluation. 37% cite reliability as the top production challenge. — [arXiv:2512.04123v1](https://arxiv.org/html/2512.04123v1)
- **Enterprise survey (Cleanlab, 2025):** Of 95 engineering/AI leaders with agents live in production, fewer than 1 in 3 teams are satisfied with their observability/guardrails. 63% plan to improve observability/evaluation. Only 5% cite tool calling accuracy as a top challenge — indicating most production agents aren't yet doing sophisticated multi-step reasoning. — [Cleanlab AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **HN discussion (543 points):** Anthropic's "Building Effective Agents" guide is widely cited as the clearest practical framework. HN consensus: "Start with LLM APIs directly — many patterns can be implemented in a few lines of code." The strongest HN comment: "None of the frameworks. You are better off coding up your workflow in some normal language, like Python, using normal programming techniques." — [Hacker News #44301809](https://news.ycombinator.com/item?id=44301809)
- **Industry guidance (NVIDIA):** "Agents are systems, not models — evaluate them accordingly." Trajectory efficiency, tool call accuracy, and graceful recovery from failures matter more than benchmark scores. — [NVIDIA Technical Blog: AI Agent Evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)
- **Research finding (Zylos, 2026):** LLM-as-judge has crossed from eval harness into production infrastructure. >57% of surveyed production teams use judge LLMs at runtime. Six distinct patterns exist with different latency/cost profiles. Field bifurcated into large proprietary judges and small distilled judges (97% cost reduction, 0.88 human correlation). — [Zylos Research: LLM-as-Judge in Production 2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)

## Gotchas

- **Golden dataset staleness.** Test cases go stale fast in production. Re-generate adversarial cases regularly — at minimum quarterly, or whenever a new failure mode is discovered in production. A 6-month-old golden dataset is a false negative factory.
- **Judge model drift.** The model used as judge evolves (new versions, fine-tunes, API changes). A judge that scored 92% human-aligned in January may score 87% in June. Re-calibrate against human labels at least annually.
- **Over-automation.** Fully automated eval pipelines miss contextual failures: tone, user trust, edge-case appropriateness. Human sampling is not a sign of weakness — it's the only signal that catches novel failure modes. Aim for hybrid, not binary.
- **Step-count inflation.** Agents that take 40 steps may produce the same output as agents taking 4. Step count is a cost and reliability signal, not a quality signal. Track both independently.
- **Benchmark gaming.** When eval results gate deploy, agents (or their prompts) get tuned to pass the eval, not to solve the actual problem. Keep a holdout set that never gets used for tuning — this is standard ML practice but frequently skipped in agentic systems.
