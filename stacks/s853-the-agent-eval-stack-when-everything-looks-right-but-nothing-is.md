# S-853 · The Agent Eval Stack — When Everything Looks Right but Nothing Is

Your agent passes the benchmark. It generates confident, fluent output. But it's calling broken URLs, running localhost in production, and flagging real CVEs as hallucinations. The eval framework scored it 94. Your users found five failures in a week. This is **The Agent Eval Stack**: a layered approach to evaluating agent behavior end-to-end, so you're measuring what actually matters — not just output quality.

## Forces

- **Determinism is dead for agents.** Traditional testing assumes same input → same output. Agents generate varied outputs even from identical inputs, making assertion-based testing insufficient.
- **Output quality ≠ agent quality.** A polished, confident response can come from a broken tool chain or a hallucinated API call. You must evaluate the entire trace, not just the final output.
- **Most eval failures are system-level, not model-level.** Practitioners report broken URLs, environment mismatches, and external dependency failures dropping scores 20–40 points — none of which a model benchmark catches.
- **LLM judges carry their own biases.** Position bias, length bias, and self-preference mean an LLM-as-judge can systematically misrank agent outputs without calibration.
- **Coverage is sparse.** Only ~15% of organizations achieve elite eval coverage (high breadth across dimensions, low false negative rate); most teams measure what they can, not what matters.

## The Move

Use a **three-layer evaluation stack** that evaluates trajectory, not just output:

### Layer 1 — Deterministic Rule Checks
- Tool call structure validation: did the agent call the right tools in the right sequence?
- API response schema validation: do tool return values match expected format?
- Hard constraint checks: did it avoid prohibited actions (localhost in cloud, PII exfiltration, missing auth)?
- Cost bounds: did it stay within token/step budgets?
- These are fast, free, and catch the highest-value failures first.

### Layer 2 — LLM-as-Judge for Process Quality
- Evaluate the full execution trace: tool call sequence, intermediate outputs, failure recovery behavior.
- Score on dimensions that require semantic judgment: reasoning quality, tool appropriateness, answer completeness, hallucination presence.
- **Calibrate your judge.** Use pairwise comparison (judge A vs. B) and consistency checks. LLM judges exhibit position bias, length bias, and self-preference. Apply calibration prompts and multi-judge ensembles to reduce variance.
- Reference: ACL 2025 survey "From Generation to Judgment" and arXiv:2604.23178 "Judging the Judges" document systematic bias patterns and mitigation strategies.

### Layer 3 — Human-in-the-Loop for High-Stakes Traces
- Flag traces where automated eval confidence is low for human review.
- Sample representative traces across task types for periodic human evaluation.
- Use human verdicts to bootstrap and calibrate Layer 2 judges — never as the primary eval path, but as the calibration signal.

### The Four Eval Dimensions
- **Task completion:** Did the agent achieve the end goal? (binary or threshold)
- **Tool use accuracy:** Did it call the right tools, in the right order, with valid parameters?
- **Reasoning quality:** Is the chain of reasoning sound across steps? Does it recover from errors?
- **Safety and guardrails:** Did it avoid prohibited actions, hallucinations, PII leaks, and injection vectors?

## Evidence

- **AWS ML Blog (March 2026):** Strands Evals uses a three-layer approach — output correctness, tool use validation, and process correctness — emphasizing that "traditional testing relies on deterministic outputs: same input → same expected output → every time. AI agents break this assumption." — [AWS Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-for-production-a-practical-guide-to-strands-evals/)
- **HN Practitioner Post (April 2026):** Developer colinfly documented a small eval test suite where "broken URLs in tool calls → score dropped to 22; agent calling localhost in a cloud environment → got stuck at 46; real CVEs flagged as hallucinations → evaluation issue, not model issue; Reddit blocking requests → external dependency failure." Most failures were system-level, not model-level. — [Hacker News](https://news.ycombinator.com/item?id=47416033)
- **Gartner (2026):** Projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps. — [Thinking Inc. Summary](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production) citing Gartner "AI Risk Management Predictions," 2026
- **MachineLearningMastery (Feb 2026):** "Evaluating language models versus evaluating agents is like testing a calculator's display versus testing an entire financial system. One focuses on output quality, the other on whether the system accomplishes its intended purpose reliably under real conditions." — [MLMastery](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance/)
- **AWS Labs Agent Evaluation (2025):** Open-source framework (368 stars, 276 commits) with per-call tracing, rule-based scoring across 3 layers, and custom benchmark support. Supports agents for Amazon Bedrock, Knowledge Bases, Amazon Q Business, and SageMaker. — [GitHub](https://github.com/awslabs/agent-evaluation)
- **ACL 2025 + arXiv:2604.23178:** Systematic analysis of LLM-as-judge biases (position bias, self-preference, length bias) and mitigation strategies. 2025 survey "From Generation to Judgment" documents the state of the field. — [ACL Anthology](https://aclanthology.org/2025.emnlp-main.138/), [arXiv:2604.23178](https://arxiv.org/abs/2604.23178)
- **RAGAS + DeepEval:** Open-source eval frameworks for RAG and agent pipelines. RAGAS provides context precision/recall, faithfulness, and answer relevancy metrics using LLM judges. DeepEval offers pytest-compatible test authoring for agent outputs. — [RAGAS GitHub](https://github.com/explodinggradients/ragas), [DeepEval GitHub](https://github.com/confident-ai/deepeval)

## Gotchas

- **Golden datasets go stale.** Agents evolve; a golden dataset from 3 months ago may validate outdated behavior. Re-annotate periodically, especially after tool schema changes.
- **LLM judges fail silently.** A judge that always returns 0.9 is useless. Monitor judge consistency — run pairwise comparisons against itself, and calibrate with human-verified samples every sprint.
- **Score > threshold ≠ success.** A task "succeeded" by the metric but through the wrong reasoning path is a false positive. You need trajectory-level eval, not just outcome eval.
- **External dependencies are part of your eval surface.** If your eval suite doesn't test tool availability, URL validity, and auth token freshness, broken URLs and blocked requests will silently corrupt your results.
- **Eval coverage is expensive.** You can't evaluate every dimension on every run. Prioritize: critical path success and safety guardrails on every commit; process quality on a sampled basis; human review only for high-stakes traces.
