# S-2385 · The Private Eval Stack — When Your Public Benchmark Is a Lie

Your agent scores 91% on SWE-bench. Your team celebrates. Three weeks later, the same agent goes to production and starts silently skipping edge-case validation checks on real customer data. Your benchmark didn't lie — it measured the wrong thing. This is the evaluation gap: the distance between what benchmarks certify and what production requires. Closing it is the hardest unsolved problem in agentic systems in 2026.

## Forces

- **Public benchmarks plateau and contaminate.** GSM8K sits above 90% for all frontier models (GPT-4o, Claude 3.5, Gemini 1.5), providing no headroom. Worse, models partially memorize test sets — Zhang et al. introduced GSM1k as a fresh mirror of GSM8K and found several model families dropped measurably, revealing score inflation from contamination. SWE-bench shows a similar pattern: agents scoring 90%+ on the benchmark retained roughly 35% of that performance when deployed on real software engineering tasks.
- **Task completion is not behavior.** An agent can reach the correct final output through broken reasoning, skip verification steps it was supposed to take, or make a wrong tool call and then accidentally recover. Binary success/failure metrics miss all of this. The arXiv 2512.12791v2 paper (MontyCloud/IIIT-Hyderabad) documents substantial behavioral failures across tool orchestration and memory retrieval that standard task-completion scores don't surface — agents appeared to perform well while violating policies, making uninformed decisions, or skipping verification checks.
- **Evaluation shifts with model updates.** GPT-4 showed measurable behavior changes across versions: tasks at 97% accuracy in March 2023 dropped to 87% by June 2023 on the same benchmark (Chen et al., 2023). Agent behavior also shifts when tool APIs change or when the distribution of user inputs drifts. One-time certification is insufficient — evaluation must be continuous.
- **Multi-agent systems compound the problem.** Evaluating a single agent's variability is hard enough; evaluating the interaction effects between two or more agents introduces additional variance that single-agent evaluation frameworks miss entirely.

## The Move

Build a private evaluation system across four layers, where the bottom layer runs automatically in CI and the top layer runs continuously in production.

### Layer 1: Golden Dataset (Static, Pre-Deployment)

A versioned, hand-curated set of test cases with inputs, expected tool sequences, and acceptable output criteria. The most effective datasets are built from three sources: production logs (tasks that actually happened), support tickets (tasks that failed in use), and adversarial mining (tasks designed to expose failure modes). Each case includes the user input, the ground-truth tool sequence, acceptable final-output criteria (semantic similarity threshold or LLM-judge rubric), and a failure-mode annotation describing what the case is designed to catch.

Size calibration by risk: 50 cases for proof-of-concept, 100–200 for production deployment, 300–500+ for mission-critical domains like finance or healthcare. Quality over quantity — a hundred well-chosen cases beat ten thousand noisy ones.

### Layer 2: Multi-Dimensional Evaluation (Dynamic, CI-Gated)

Run the golden dataset through the agent and evaluate across four dimensions, not just task success:

- **Tool orchestration correctness** — did the agent call the right tools in the right order with the right arguments? Log and compare against the ground-truth tool sequence.
- **Reasoning soundness** — if the agent produces chain-of-thought reasoning, evaluate whether the logic is coherent. Agents that reach correct conclusions through broken reasoning are ticking time bombs.
- **Memory retrieval quality** — does the agent correctly ingest and recall relevant context across steps? This is a primary failure mode in multi-step agents that binary success metrics never catch.
- **Cost and latency efficiency** — track token count, latency, and cost per task to catch regressions that inflate inference spend.

### Layer 3: LLM-as-Judge (Runtime, Production)

Over 57% of surveyed production agent teams now use judge LLMs at runtime for quality gating, hallucination defense, and tool-call verification. Six patterns exist with different latency/cost tradeoffs:

| Pattern | Latency | Cost | Best For |
|---------|---------|------|----------|
| Offline eval harness | None (async) | High | CI regression suites |
| Online runtime verifier | 76–162ms | Medium | User-facing output gating |
| Self-consistency loops | High | High | Math, formal code domains |
| Reflexion/reflection | Medium | Low | Iterative task improvement |
| Constitutional AI/RLAIF | Variable | Medium | Guardrails, training-time alignment |
| Inference-time reward | High | High | Reasoning task verification |

Small distilled judges (e.g., 8B models fine-tuned on judge data) can match larger general-purpose models on specific evaluation dimensions at a fraction of the cost. The key is to match judge model capability to evaluation dimension — don't use GPT-4o to grade email tone.

### Layer 4: Human-in-the-Loop Sampling (Continuous, Production)

Sample a percentage of production outputs for human review — typically 5–15% depending on risk level. Route samples by: low-confidence outputs (agent's own uncertainty signal), high-stakes outputs (financial, medical, legal content), and random sampling for drift detection. Human reviewers flag issues that LLM judges miss, particularly around business policy nuance, tone, and domain-specific quality.

## Evidence

- **arXiv paper:** *Beyond Task Completion: An Assessment Framework for Evaluating Agentic AI Systems* (2512.12791v2) — MontyCloud/IIIT-Hyderabad research documents the four-pillar evaluation framework (LLM, Memory, Tools, Environment) and finds that behavioral failures in tool orchestration and memory retrieval are systematically invisible to task-completion metrics. Validated on MOYA multi-agent framework across three production-motivated CloudOps scenarios. — https://arxiv.org/html/2512.12791v2

- **GitHub (TribeAI):** *claude-evals* — production eval framework for Claude Agent SDK implementing Anthropic's published eval patterns with native SDK hooks into `PreToolUse`, `PostToolUse`, and `SubagentStop` lifecycle events (not just final output). Ships with a 50-case golden dataset for contract review. README emphasizes: mine real usage from production logs, cover the hard and unusual cases on purpose, and treat the dataset as versioned maintained data. — https://github.com/TribeAI/claude-evals

- **Research blog (Zylos):** *LLM-as-Judge in Production* (April 2026) — 57%+ of surveyed production agent teams now use judge LLMs at runtime. Documents six patterns with latency/cost profiles. Finds small distilled judges can match large models on specific eval dimensions. — https://zylos.ai/research/2026-04-10-llm-as-judge-production-agent-verification-2026/

- **Industry analysis (CB Insights):** Y Combinator 2025 Summer Batch analysis noting: "Agents scoring 90%+ on SWE-bench retained roughly 35% in production" — the survival ratio problem. Public benchmarks certify narrow capability, not production reliability. — https://www.cbinsights.com/research/y-combinator-summer2025/

- **Engineering blog (Thoughtworks Australia):** *Evaluating AI Agents in Production* (June 2025) — cites MIT research (~95% of AI projects fail) and frames evaluation as the primary obstacle. Documents the shift from deterministic testing to probabilistic evaluation with rubrics, LLM judges, and continuous monitoring. — https://www.thoughtworks.com/en-au/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production

## Gotchas

- **Benchmark contamination hides regressions.** If your eval harness uses the same public benchmarks as your CI, model updates that partially memorize the test set will show score improvements that don't translate to production. Maintain a private held-out set that never touches the training pipeline.
- **Golden datasets drift if not maintained.** A dataset built from January 2025 production logs reflects January 2025 user behavior. As user inputs evolve, your dataset must evolve too. Treat it like a codebase — PR workflow, review, version tags. Stale datasets produce false confidence.
- **LLM judges have biases that compound at scale.** Larger models are more lenient judges. Smaller models are more brittle. A judge model that disagrees with human reviewers more than 20% of the time will systematically misgate your production outputs. Calibrate your judge against human ground truth before deploying it as a gate.
- **Multi-agent interaction effects are the most invisible failure class.** Evaluating each agent in isolation against its own golden dataset misses coordination failures — agents passing the wrong context to each other, duplicating work, or creating circular dependencies. You need end-to-end traces across the full agent graph, not per-agent unit tests.
