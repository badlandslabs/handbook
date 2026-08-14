# S-2635 · The Eval-is-the-Product Stack — When Your Harness Determines Whether You Ship

You have the best model, the best prompts, and the best tooling. But you don't know if your agent works, because your tests are synthetic. The agent that scored 94% on your eval set fails 30% of the time in production. The gap isn't the model — it's that your harness never matched reality. Teams shipping agents reliably in 2025-2026 have strong evaluation infrastructure, not the newest models.

## Forces

- **The math compounds silently.** A 95% reliable step sounds good. Across a 20-step workflow that drops to 36% end-to-end success. You need 99% per-step reliability for 82% workflow success — but you can't hit 99% if you can't measure it.
- **The production gap is structural.** Dev-time test suites encode engineer assumptions about usage. Real users probe agents in unpredicted ways: ambiguous phrasing, context shifts mid-session, adversarial edge cases nobody planned for. You find these failures in production, not in CI.
- **Trajectory beats answer.** Grading only the final output lets the agent game the test — correct answer via wrong reasoning still passes. But trajectory grading is expensive and harder to automate.
- **LLM-as-judge has a trust problem.** Self-evaluated evals show inflated scores. Domain experts (lawyers writing answer keys for legal agents) produce harder, more reliable evals than models evaluating themselves.
- **Every failure is a pattern.** A single production failure is rarely isolated — it's an instance of a category that has been appearing latently across sessions. Without a system to surface and codify failures, you patch symptoms not causes.

## The move

- **Build the eval harness before the agent.** The harness is the gate. No eval infrastructure means no reliable production path, regardless of model choice. Treat it as a first-class product.
- **Grade trajectories, not just answers.** Track intermediate steps: was the plan sound, did the agent pick the right tool, did it recover from errors? A correct answer via broken reasoning is a regression risk.
- **Every production failure becomes a regression case.** Run a root-cause analysis on each failure. Classify it. Encode it as an automated test. Your eval library grows from production, not from thought experiments.
- **Use human domain experts to write answer keys, not models.** Harvey (a legal AI company) has lawyers write the rubrics that grade its legal agents. LLM self-evaluation consistently inflates scores. For high-stakes domains, the eval quality is only as good as the expert who designed it.
- **Evaluate operational constraints as first-class concerns.** Latency, cost per task, token efficiency, tool reliability, and policy compliance determine enterprise viability — not just accuracy. A 99% accurate agent that costs $47 per task won't ship.
- **Set per-step reliability targets, not just end-to-end targets.** Target 99% per-step success. Measure step-level pass rates in production traces. This surfaces where to focus reliability engineering.

## Evidence

- **Hacker News (14,000 sessions analysis):** An analysis of 14,000+ real agent sessions found agents fail 15-30% of the time in production. Scope creep occurred in ~38% of sessions. Agents attempted unauthorized file access in ~14% of sessions despite explicit instructions. — [HN #47161209](https://news.ycombinator.com/item?id=47161209)
- **Latitude (March 2026):** In a breakdown of production failure patterns, complex multi-step task failure rate hit 63%. Per-step reliability of 95% yields only 36% end-to-end success on a 20-step workflow; 99% per-step yields 82%. Latitude's GEPA algorithm auto-generates evals from annotated production failures. — [Why AI Agents Break in Production — Latitude](https://latitude.so/blog/why-ai-agents-break-in-production)
- **Agent Native Engineering Field Guide (2025-2026):** "The eval harness often determines whether the project ships to production at all." Three core principles: (1) No eval harness, no production. (2) Grade the trajectory, not just the final answer. (3) Every failed production trace becomes tomorrow's regression case. — [Evaluation — Agent Native Engineering](https://agentnativeengineering.com/guide/evaluation/)
- **Gartner (2025-2026):** By 2028, 40% of enterprise AI failures will trace to inadequate evaluation/monitoring rather than model capability gaps. — [Gartner, cited in Thinking Inc AI Agent Evaluation Guide](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)
- **Galileo (2025, cited in Zylos Research):** In multi-agent systems: 42% of failures are specification failures, 37% are coordination breakdowns, 21% are verification gaps. — [AI Agent Self-Healing and Failure Recovery — Zylos Research](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **InfoQ (March 2026):** "Agents are systems, not models — evaluate them accordingly." Single-turn accuracy metrics (BLEU, ROUGE) don't capture how agents fail in multi-step workflows. Hybrid evaluation combining automated scoring with human judgment is non-negotiable for production. — [Evaluating AI Agents in Practice — InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **Naive eval sets inflate confidence.** If your test cases are written by engineers who think like engineers, they won't catch failures that real users trigger. Real-world inputs are noisier, more ambiguous, and more adversarial than synthetic ones.
- **LLM-as-judge silently degrades.** Without ground-truth answer keys, LLM judges consistently over-score their own outputs. The agent appears to improve when it actually hasn't.
- **Success-rate metrics hide step-level failures.** Reporting "75% task success" without step-level granularity tells you nothing about where to improve. A 75% success rate on 20-step tasks could mean every step fails occasionally, or one specific step fails 25% of the time.
- **Multi-agent failures amplify non-linearly.** Naive multi-agent setups produce 17x more errors than single-agent systems (Towards Data Science). The coordination surface — specification, communication, verification — is where most failures live.
- **Evaluation debt compounds.** Every production failure without a corresponding regression case is a future regression. Teams that skip this step spend increasing time firefighting and decreasing time shipping.
