# S-2459 · The Ground Truth Stack — When Your Agent Ships But Nobody Knows If It's Good

Your agent passes all your tests. It ships. Weeks later, support tickets surface a class of failure no one caught — confident wrong answers on edge cases your eval suite never included. The problem isn't the agent; it's that "passing tests" and "being good" are different things for probabilistic systems. The fix is a layered eval strategy: golden datasets, LLM-as-judge, ablation, and production monitoring wired together into a single feedback loop.

## Forces

- **Golden datasets go stale fast** — agent behavior changes with every prompt or model update; a dataset that was representative six months ago may not be today.
- **Ground truth is expensive to create** — human annotation at scale is the gold standard but doesn't scale with the pace of agent iteration.
- **LLM-as-judge has its own biases** — it judges surface polish well, but systematically over-rates confidence and under-detects subtle factual errors.
- **Ablation is underused** — most teams never systematically test whether adding an agent actually improves output quality, so over-engineered pipelines persist.
- **Agent changes come in threes** — code, prompts, and model weights shift together, making it hard to attribute regression to any single cause.

## The move

Build a three-layer eval stack that fires at different cadences:

**Layer 1 — Unit eval with golden datasets (CI gate)**
- Curate a "golden set" of 50–200 representative inputs with known correct outputs. Include known failure cases surfaced from production.
- Run every PR through the dataset. Use deterministic pass/fail checks for structured outputs; use LLM-as-judge with a rubric for open-ended ones.
- Track pass rate, average score, and per-metric breakdown over time. A regression in any metric should block the PR.
- Version your dataset in git alongside the agent code. Treat dataset drift with the same urgency as code drift.

**Layer 2 — LLM-as-judge for qualitative signals (pre-deploy)**
- Calibrate your judge model against 20–50 human-annotated examples. Measure correlation (Spearman or Cohen's kappa) before trusting it at scale.
- Run the judge on a broader sample (500–1000 cases) than the golden set covers. Score on rubric dimensions: correctness, safety, completeness, coherence.
- Use a different model as judge than the one generating the output (e.g., judge with Claude Opus, generate with Claude Sonnet) to reduce self-serving bias.
- Tag outputs the judge is uncertain about for human spot-check — don't automate what you can't verify.

**Layer 3 — Production telemetry with interaction pattern analysis (always-on)**
- Instrument every agent run: input hash, output, tool calls made, latency, token spend, and a quality signal (thumbs up/down, downstream task success rate, or escalation count).
- Run quarterly ablation studies: remove one agent from a multi-agent pipeline and compare end-to-end quality. If the agent's removal doesn't measurably degrade output quality, it's overhead — cut it.
- Monitor inter-agent communication traces for patterns: agents passing work back and forth without converging (loop), one agent consistently dominating latency (bottleneck), or silent propagation of bad inputs (error cascade).
- Set automated alerts on quality signal drift — a 5% drop in task success rate should page someone before tickets pile up.

**Sampling rule:** Not every production run needs human review. Sample 2–5% of runs for human evaluation, biased toward high-stakes domains, novel input clusters, and cases where the judge was uncertain.

## Evidence

- **Engineering blog:** Anthropic's guide on building effective agents recommends starting with the simplest solution and only adding agents when needed — ablation testing is the empirical check that justifies complexity. — [Anthropic Engineering: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **GitHub repo:** Microsoft Foundry's eval GitHub Action runs agent evaluations offline in CI, collecting latency, token counts, and statistical significance testing to distinguish real regressions from random variation. — [microsoft/ai-agent-evals](https://github.com/microsoft/ai-agent-evals/blob/main/README.md)
- **Industry analysis:** One team ran quarterly ablation and found a dedicated "tone adjustment" agent in their content pipeline added zero measurable quality — removing it cut pipeline latency by 18% and cost by 15%. — [The Thinking Company: AI Agent Evaluation in Production (2026)](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)
- **GitHub repo:** MLflow's evaluation docs recommend building golden datasets from known production failures, versioning them in git, and using them as regression gates in CI. — [MLflow: Building Agent & LLM Evaluation Datasets](https://mlflow.org/docs/latest/genai/datasets)
- **Benchmark framework:** LangChain's evaluation guide distinguishes reference-based metrics (BLEU, ROUGE, exact match — for structured tasks with ground truth), reference-free metrics (perplexity, fluency — screening only), LLM-as-judge (nuanced quality at scale, needs calibration), and human annotation — each with different tradeoffs appropriate for different eval stages. — [LangChain: Evaluating LLMs and Agents](https://www.langchain.com/resources/how-to-evaluate-llms)

## Gotchas

- **Golden dataset overfitting** — if your dataset only contains cases you've seen before, it won't catch novel failure modes. Actively inject adversarial and edge cases.
- **Judge model bias** — LLM judges systematically prefer longer, more confident outputs. Calibrate on human annotations or you'll ship agents that sound good but are wrong.
- **Measuring the right thing** — an agent can produce a correct answer in 60 seconds when the user expected 5 seconds. Latency and cost matter alongside quality.
- **Evals go stale** — re-annotate a sample of your golden set every quarter. Model updates and prompt changes shift the behavior surface.
