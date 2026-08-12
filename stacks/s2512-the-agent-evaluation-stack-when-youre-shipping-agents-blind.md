# S-2512 · The Agent Evaluation Stack — When You're Shipping Agents Blind

Your agent passed every test. The benchmark says 94%. The final answer looks right. But the agent deleted the wrong database, ran 40 extra tool calls, and got lucky. Nobody caught it because nobody was looking at the path — only the destination. This is the agent evaluation problem: the failure mode that benchmarks miss is the failure mode that ships.

## Forces

- **Endpoint evals miss the real failure mode.** An agent can reach the right answer through a reckless path — wrong tool first, lucky recovery, ignored constraints that didn't bite this time. Endpoint scoring certifies answers, not behavior.
- **Agents amplify upstream errors.** A bad decision in step two corrupts step three, which corrupts step four. Standard LLM evaluation (single prompt → single response) has no concept of this cascading — it can't see the chain.
- **Production failures reveal what benchmarks can't.** 95% of GenAI pilots fail to deliver measurable ROI (MIT Project NANDA, 150 interviews + 300 deployments). 88% never reach production (CIO.com). The dominant cause isn't model quality — it's system integration failures that no benchmark catches.
- **Eval quality competes with eval velocity.** Teams skip evals to ship faster, then discover failures in production. But building a good eval harness once and automating it as a CI gate costs less than debugging production incidents.

## The Move

Use a three-level diagnostic stack with trajectory-first evaluation, golden datasets built from real failures, and automated regression gates in CI/CD.

**Three evaluation levels — use as a diagnostic stack:**
- **End-to-end:** Treat the agent as a black box. Did the task succeed? Binary pass/fail or task-completion rate on a golden dataset. This is your floor, not your ceiling.
- **Trajectory-level:** Score the full run — which tools were called, in what order, with what arguments, and whether each step satisfied policy. Catch reckless paths that got lucky.
- **Component-level:** Isolate which piece broke — a specific tool, the retriever, the model, or the prompt. Use when trajectory eval shows a failure but the cause is unclear.

**Calibrate LLM judges against real examples:**
- Use deterministic checks for exact things (tool name, JSON structure, API response codes) — no judge needed.
- Use LLM-as-judge for anything requiring judgment (reasoning quality, response appropriateness, policy compliance).
- Calibrate judges against a human-labeled subset before trusting scores at scale. Without calibration, GPT-4 shows self-preference bias (favors its own outputs — arxiv:2410.21819) and position bias (prefers first/last options regardless of content).
- For high-volume inline checks, small distilled judges (Galileo Luna-2 3B–8B, Prometheus 2 7B) deliver 97% cost reduction vs. large proprietary models at 0.88–0.95 accuracy. Reserve GPT-4o/Claude 3.7 for high-stakes verification.

**Build the golden dataset from production, not imagination:**
- Hand-crafted test cases reflect only what engineers imagined. Production failures surface the long tail: ambiguous phrasings, malformed inputs, unanticipated tool sequences.
- The Agent Development Flywheel: production failure → trace → test case → golden dataset → CI gate. The same failure cannot silently ship twice.
- Minimum viable setup: 50–200 real examples, per-step rubrics, 10+ runs per example for statistical significance, and a held-out set you never tune against.

**Automate as a regression gate in CI/CD:**
- Treat agent evaluation as a CI engineering problem. Full eval suite runs after every prompt change, model swap, or tool addition — not optional, not manual.
- Replay harnesses capture production traces and re-run them against new model versions without re-hitting live systems. Catch regressions before users do.
- AWS Labs Agent Evaluation provides built-in CI/CD hooks for Amazon Bedrock, Amazon Q Business, and custom targets. LangChain AgentEvals offers trajectory matching with golden trace comparison.

## Evidence

- **Blog post (jamesm.blog, June 2026):** "Endpoint evals miss the failure mode that hurts in production — an agent can reach the right answer through a reckless path." Introduces trajectory evaluation as the corrective: score which tools were called, in what order, with what arguments. Minimum viable: 50–200 real examples, per-step rubrics, 10+ runs per example, held-out set. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **Company engineering post (Arthur.ai, June 2026):** "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures." Documents the flywheel: trace → test case → golden dataset → CI gate. Contrasts synthetic tests (static, engineer-imagined) vs. production failures (reflect actual input distribution, continuously growing). — [arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Research survey (arXiv 2507.21504):** "Evaluation and Benchmarking of LLM Agents: A Survey" — comprehensive taxonomy of evaluation objectives (task performance, rationality, human preference, efficiency) and evaluation methods (rule-based, model-based, human-based). Notes that benchmarks designed for research settings often don't reflect production complexity. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **Company blog (Braintrust, February 2026):** "A prompt change that improves performance on one test case may degrade performance on another." Documents regression gates as the solution: automated scoring in CI, full suite run on every change, manual trace inspection as the complement to metrics. — [braintrust.dev/articles/ai-agent-evaluation-framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Research blog (Zylos Research, April 2026):** "Intrinsic self-correction is unreliable — prompting an LLM to check your work without external grounding degrades performance on reasoning tasks." Documents the six LLM-as-judge patterns (offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI, inference-time reward models) and the large-vs-small judge bifurcation. — [zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)
- **Open-source framework (AWS Labs):** Agent Evaluation provides CI/CD integration for Amazon Bedrock, Amazon Q Business, SageMaker, and custom targets. Test cases, built-in evaluators, and CLI hooks for regression gates. — [github.com/awslabs/agent-evaluation](https://github.com/awslabs/agent-evaluation)
- **Open-source framework (TribeAI/claude-evals):** Implements Anthropic's published eval patterns with 50-case golden dataset, native SDK hooks, one-command model comparison. — [github.com/TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)

## Gotchas

- **Evaluating only the final answer misses reckless paths.** If you only score outputs, a lucky wrong-path agent looks great. Always inspect trajectories — the path is the signal.
- **LLM-as-judge has documented failure modes.** Self-preference bias, position bias, and hallucinated scores are not edge cases — they're systematic. Calibrate against human labels and use deterministic checks where possible.
- **Synthetic test suites go stale.** If you're not capturing production failures as test cases, your golden dataset shrinks in relevance every week. Build the flywheel.
- **Statistical noise is real.** A single run per example gives you high-variance scores. Run 10+ iterations per example and track distributions, not just means.
- **Eval results are not model comparisons.** An agent that scores 85% on your golden dataset isn't "85% as good as GPT-4." It's 85% on your specific tasks, your specific tools, your specific distribution. Cross-model comparisons require the same harness.
