# S-2176 · The Endpoint Eval Mirage Stack — When Your Agent Passes Every Test and Still Fails in Production

Your eval dashboard is green. Task success rate: 82%. You're shipping with confidence. Three weeks later, your agent is selecting the wrong tool first and recovering by luck, ignoring cost constraints on every call, and silently dropping the last step of a six-step workflow 30% of the time. The dashboard never showed you any of this. Endpoint evaluation measured whether the agent finished — not how it got there or whether it got there reliably.

## Forces

- **Compounding failure math punishes multi-step agents.** An agent that succeeds 85% of the time per step completes a 10-step workflow only ~20% of the time. Your endpoint eval showing 85% pass rate is measuring the wrong thing entirely — it certifies answers, not behavior.
- **The right answer via the wrong path is still a failure.** An agent that calls the wrong API first, then recovers, and reaches the correct output has technically "passed" your eval. It will fail on the next task that doesn't have a recovery path.
- **Pass@k hides reliability.** Pass@1 is what ships. Pass@10 is what your agent achieves in production when users give up and retry. A 95% pass@10 means your users experience an 80% failure rate on the first attempt — but your eval dashboard shows 95%.
- **Trajectory failures don't raise exceptions.** Agents fail by going quiet, looping, or producing subtly wrong output — not by crashing. Your monitoring stack, built for traditional software, sees no errors and flags no alerts.

## The move

Measure the trajectory, not just the endpoint. Treat agent evaluation as a behavioral test suite, not a quality scorecard.

- **Separate trajectory metrics from outcome metrics.** Trajectory measures *how* the agent worked: which tools it called, in what order, with what arguments, whether each step satisfied policy constraints. Outcome measures *whether* the task completed and the output was correct. Both are necessary; neither is sufficient alone.
- **Apply the compounding failure lens to set your eval baseline.** For an N-step workflow, target per-step accuracy high enough that your overall success rate is acceptable. If you need 70% end-to-end success on a 10-step workflow, you need ~97% per-step accuracy — not 70%.
- **Build per-step rubrics, not just end-state checks.** Score each tool call: was the right tool selected? Were the parameters correct? Did the output get used correctly in the next step? A rubric with 5–10 scoring dimensions per step catches the failure modes that compound.
- **Run eval on the trajectory trace, not the final output.** Capture the full execution trace (tool calls, intermediate outputs, reasoning steps) and score against it. This is what lets you debug *why* an agent failed, not just that it did.
- **Integrate eval into CI/CD with a regression gate.** Treat prompt changes, model swaps, and tool modifications as code changes: run the full eval suite before merge. A GitHub Actions job running Microsoft Foundry's evaluation action or a custom eval harness with pytest `@mlflow.test` decorators gates the merge when trajectory quality regresses.
- **Use replay harnesses for offline regression.** Capture production traces and re-run them against new model versions or policy changes without hitting live systems. This catches silent regressions between deploys.
- **Calibrate LLM-as-judge with Cohen's kappa.** Automated judges drift; a single judge scores inconsistently across raters. Require 0.80+ Spearman correlation or Cohen's kappa ≥ 0.75 between the judge and human ground truth before trusting automated scoring.

## Evidence

- **Blog post — Prefactor.tech:** An agent with 85% per-step accuracy completes a 10-step workflow only ~20% of the time. Trajectory-level evaluation measures the full reasoning path step by step, scoring quality across the whole sequence rather than at the endpoint alone. — [Prefactor.tech](https://prefactor.tech/blog/step-level-accuracy-trajectory-evaluation-production-agents)
- **Blog post — jamesm.blog:** Endpoint evals miss the failure mode that hurts in production — an agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints that did not bite this time. Trajectory evaluation scores the full run: which tools were called, in what order, with what arguments, and whether each step satisfied policy. — [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **GitHub repo — microsoft/ai-agent-evals (97 stars):** Microsoft Foundry Evaluation GitHub Action enables offline evaluation of AI agent applications using model-as-judge, content safety, and mathematical metrics — designed to gate CI/CD merges. Runs eval suites as regression checks against agent traces. — [github.com/microsoft/ai-agent-evals](https://github.com/microsoft/ai-agent-evals)
- **Blog post — Galileo AI:** Production agents can achieve 60% success on single runs, dropping to 25% across eight runs. Traditional monitoring shows green because agents technically complete every task, even when outputs are corrupted. Over 40% of agentic AI projects will be canceled by end of 2027 (Gartner). — [Galileo AI](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Blog post — Maxim AI:** A three-layer evaluation framework: System Efficiency (latency, tokens, tool calls), Session-Level Outcomes (task success, trajectory quality), and Node-Level Precision (tool selection, step utility). — [Maxim AI](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices/)
- **GitHub repo — ashishlandiwal/agent-eval-harness:** Evaluation & observability harness with Cohen's kappa calibration for LLM-as-judge, drift monitoring, and a CI regression gate. — [github.com/ashishlandiwal/agent-eval-harness](https://github.com/ashishlandiwal/agent-eval-harness)

## Gotchas

- **Over-indexing on pass@k without trajectory scoring.** Pass@10 is not your user experience. Users get pass@1. If your agent achieves 90% pass@10 but 55% pass@1, you are shipping a frustrating product with a flattering metric.
- **Tuning your eval against the held-out set.** If you iterate on prompts or model choices using your evaluation dataset, you've contaminated it. Keep a held-out set you never tune against; measure final quality on that, not the set you optimized on.
- **Ignoring cost and latency in the eval score.** An agent that achieves 95% accuracy at 10x token cost and 5x latency is not a 95% agent. Factor in efficiency alongside correctness — especially in workflows where the agent runs hundreds of times per day.
- **Scoring only the happy path.** Your eval suite should include adversarial cases, partial failures, ambiguous inputs, and edge conditions. A suite that only tests clean inputs will pass and then fail on the first real user.
- **LLM judges hallucinate confidence.** An LLM judge can assign a high score to a trajectory that has subtle errors. Always spot-check judge outputs against human review, especially on high-stakes tasks.
