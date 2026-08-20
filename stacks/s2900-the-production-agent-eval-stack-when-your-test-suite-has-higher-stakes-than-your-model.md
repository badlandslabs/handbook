# S-2900 · The Production Agent Eval Stack — When Your Test Suite Has Higher Stakes Than Your Model

The gap between a demo agent and a production agent isn't the model — it's whether you've built a test harness that catches failures before customers do. In 2025-2026, Gartner estimates 40%+ of agentic AI projects get cancelled not because the model failed, but because the evaluation pipeline failed. You can't improve what you can't measure, and for agents, "what you measure" is a multi-dimensional problem that deterministic tests can't solve alone.

## Forces

- **Agents compound errors in ways singletons don't.** A 20-step agent where each step succeeds 90% of the time has a ~12% overall success rate. One bad early decision corrupts every subsequent step. Standard unit testing covers happy paths; it misses the failure modes that define real-world agent behavior.
- **Evaluation methods that work for LLMs fail for agents.** Exact-match metrics are too brittle (valid SQL and valid API approaches get different scores). Human review doesn't scale to thousands of daily interactions. You need something between the two.
- **Eval is usually an afterthought.** The HN "Ask: How are people doing AI evals?" thread (43 comments, 2025) surfaced a consistent pattern: most teams evaluate "by vibes," write scripted tests from production logs ad-hoc, and ship without regression gates. The teams that succeed treat evals as first-class engineering artifacts, not post-hoc quality theater.
- **The retry cascade problem.** A missing retry cap allowed 1,279 Claude Code sessions to run 50+ consecutive compaction failures each, burning ~250,000 API calls in a day. The agent executed its recovery logic perfectly — the logic just had no ceiling. Evaluation infrastructure that doesn't cap resource consumption can itself become the failure.

## The Move

Build a **three-level eval stack** with separate metrics for outcomes, trajectories, and components. Use deterministic checks where possible, LLM-as-judge where interpretation is required, and integrate the whole thing into CI/CD as a regression gate.

**Three-level metric taxonomy:**
- **Outcome metrics** — Did the agent complete the task correctly? Binary or graded final result (task completed / not completed). Easiest to define, hardest to attribute.
- **Trajectory metrics** — Was the reasoning path sound? Did the agent pick the right tools in the right order? Did it retry appropriately? Did it terminate when done? These require trace analysis.
- **Component metrics** — Did the retrieval layer return relevant context? Did the tool call use correct arguments? Did the memory layer persist the right facts? Unit-level, independently testable.

**LLM-as-judge with calibration:**
- Use an LLM judge for trajectory and outcome evaluation where human interpretation is required.
- Calibrate the judge against human-labeled examples targeting **0.80+ Spearman correlation** with human judgment before trusting scores.
- Build rubric-engineered prompts with Schema-Guided Reasoning (SGR) — structured output formats that constrain judge variance.
- Track Cohen's Kappa (inter-rater agreement between judge and human) alongside raw scores.

**Build versioned eval datasets from production traces:**
```
trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring
```
Collect failing traces from production, label them, cluster by failure type, dedupe, add to the eval suite. The dataset becomes a living artifact that grows with your production incident history.

**CI/CD integration as the regression gate:**
```yaml
# GitHub Actions snippet from slavadubrov.github.io (2026)
- name: Run agent evaluation suite
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    python -m evaluation.run_suite \
      --config agent-configs/research-agent/v1.1.yaml \
      --dataset eval-datasets/research-agent/v2.3.jsonl \
      --threshold 0.82
```
Set pass/fail thresholds per agent version. Block merges when scores drop. Run on every commit, on a schedule (weekly regression), and on-demand after major prompt changes.

**Cost and latency as first-class metrics:**
- Track cost-per-task alongside accuracy. Benchmarks show 50x cost variation ($0.10–$5.00) for similar accuracy — domain-specific agents achieve 82.7% accuracy vs 59-63% for general LLMs at 4.4-10.8x lower cost (Aisera CLASSic framework).
- Track pass@1 vs pass@8 — performance often drops from 60% to 25% under stricter success criteria. Know which threshold your production SLA requires.

## Evidence

- **Academic research:** arXiv:2511.14136v1 (Nov 2025) — "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems" — analyzed 12 benchmarks and found 50x cost variation for similar accuracy, 8/10 benchmarks with validity issues, and that LLM-as-judge evaluation introduces ranking changes in 41% of SWE-bench results. https://arxiv.org/html/2511.14136v1
- **HN Ask thread (43 comments, 2025):** "Ask HN: How are people doing AI evals these days?" — real practitioner consensus that most teams still evaluate by vibes, scripted tests from production logs are the most common structured approach, and domain-specific test datasets outperform general benchmarks. https://news.ycombinator.com/item?id=47319587
- **HN Show HN (79 points, 37 comments, 2026):** "Show HN: agent-skills-eval" — open-source tool comparing agent runs with/without skills; top comment surfaced that even 720-byte CLAUDE.md instructions are ignored by Opus 4.7 ~30% of the time for specific tool selection, illustrating why behavioral eval (did the agent use the right tool?) matters more than output quality alone. https://news.ycombinator.com/item?id=48046023
- **Engineering blog:** slavadubrov.github.io (Jun 2026) — "AI Agent Evaluation in Production: Traces to Test Suites" — three-level taxonomy (outcome/trajectory/component), CI integration pattern, and failure taxonomy showing that evaluation harness defects cause agent failures even with a stronger base model. https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/
- **Industry report:** Galileo Labs (Feb 2026) — "How to Build an Agent Evaluation Framework" — 3-tier rubric system (7 dimensions → 25 sub-dimensions → 130 items), recommendation to implement LLM-as-judge targeting 0.80+ Spearman correlation, CI/CD integration with commit/scheduled/event-driven triggers. https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks
- **Failure case study:** AgentMarketCap (Apr 2026) — 1,279 Claude Code sessions running 50+ compaction failures each = ~250,000 API calls. Demonstrates that retry logic without circuit breakers and resource caps causes runaway costs. https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery

## Gotchas

- **Don't trust your LLM judge without calibrating it.** An uncalibrated judge will have systematic biases — preferring verbose outputs, favoring its own model's style, conflating fluency with correctness. Measure inter-rater agreement against human labels before going to production scale.
- **Pass@1 vs pass@8 will give you whiplash.** Teams celebrate 90% pass@1 scores, then watch their agent succeed only 25% of the time when asked to complete tasks correctly on the first attempt. Set the threshold that matches your SLA, not the one that looks better.
- **Eval datasets go stale fast.** Prompt drift, model updates, and upstream API changes can shift agent behavior without triggering a test failure if your eval dataset doesn't cover the new distribution. Re-label and version your datasets regularly — at minimum on major model updates.
- **Skills and instructions are frequently ignored.** Even well-specified CLAUDE.md files and agent skills get dropped ~30% of the time for specific tool-selection decisions. Behavioral evaluation (did the agent use the right tool?) catches this; output-quality evaluation misses it entirely.
- **Offline/hybrid eval doesn't replace online monitoring.** Eval suites run on curated datasets against known failure modes. Production surfaces novel failure modes continuously. You need both: offline regression gates + online drift monitoring with alerts.
