# S-1259 · The Synthetic Eval Stack — When Your Agent Succeeds in Tests but Fails in Production

Your eval suite covers the happy path. Your agent passes. You ship. Then production surfaces a failure you never imagined — a negative invoice, a deleted record, a tool called in the wrong state. Your test cases weren't wrong; they were incomplete. The gap between what you tested and what can go wrong is the gap between a demo and a product.

This is the test coverage problem for agents: building enough test cases manually is slow, expensive, and biased toward what you already imagined. The mature pattern is to synthesize test cases from production failures, use the agent's own failures as the curriculum, and gate deployments on the resulting scores.

## Forces

- **Manual test authoring is the bottleneck, not model quality.** Writing enough diverse test cases to cover edge cases, multi-turn flows, and adversarial inputs takes days. The agent outpaces the test suite, not the other way around.
- **Production surfaces failures your imagination can't.** Teams that write all their test cases upfront miss the failure modes that only appear under real load, with real data, from real users. The most valuable test case is one you didn't write — it came from production.
- **Eval non-determinism requires statistical framing, not pass/fail.** Running a test once and seeing success doesn't mean the agent is reliable. Running the same test ten times and seeing 7/10 success means you have a 30% failure rate, which most teams never measure.
- **The 37% gap between lab and real-world performance is documented.** LangChain's 2026 State of AI Agents survey found that agents scoring well on benchmark tests often perform far below those scores in production. Static task-completion benchmarks reward correctness on idealized inputs; they miss constraint decay, context sensitivity, and multi-step error cascades. (Zylos Research, 2026)
- **Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation, not model capability gaps.** (Gartner, cited by Zylos Research, 2026)

## The Move

**Build a feedback loop: production failures become synthetic test cases, which become regression gates, which prevent the next production failure.**

### 1. Capture failures as test seeds automatically

When a user reports a problem or production monitoring detects an anomaly, extract the full interaction — user input, agent trajectory, tool calls, final output. Anonymize sensitive fields. Add it directly to the regression test set. This is the highest-value test case you will ever have: it already happened.

The AlphaEval paper found that production agent evaluation averages 2.8 leaf-node evaluation types per task. Structure your test cases to capture multiple dimensions — tool correctness, output format, semantic accuracy, constraint compliance — so one failure produces multiple test signals. (Augment Code, 2026)

### 2. Synthesize diverse test variants from seeds

Rather than one fixed test case, generate diverse rephrasings and persona-varied inputs from each failure seed. Vary the phrasing, the implicit context, the edge condition. This expands coverage without hand-authoring every variant. Google's AI research team reports that simulation-based testing identifies 85% of critical issues before production deployment. (Zylos Research, 2026)

For agent trajectories specifically, LangChain's AgentEvals framework provides two complementary approaches: **trajectory match** (hard-coded reference trajectories validated step-by-step) for well-defined workflows, and **LLM-as-judge** for nuanced qualities like efficiency and appropriateness. Combine both — trajectory match for correctness, LLM-as-judge for quality. (LangChain Docs, 2025)

### 3. Run statistical evals, not single-shot tests

Run each test case a minimum of 5–10 times to account for non-determinism. Report success rate, not pass/fail. A 70% success rate is actionable data; a single pass/fail result hides it. Set quality thresholds as a contract, not a slider — define the minimum acceptable rate before tuning, not after. (BestAIWeb, 2026)

For structured output specifically: schema compliance (valid JSON, correct types) is measurable deterministically and fast. Semantic correctness (did the JSON contain the right values?) requires LLM-as-judge or code-based assertion. Separate these two concerns — run the cheap checks first, invoke the expensive grader only when the cheap checks pass. (Augment Code, 2026)

### 4. Gate CI/CD on eval scores with explicit thresholds

The concrete pattern, adopted by the most mature teams: a CI action automatically triggers eval runs against the golden dataset on every pull request. Scores are posted as a PR comment with comparison to the reference baseline. If any score falls below the predefined quality threshold, deployment is automatically blocked. An engineer must fix the regression or explicitly justify lowering the threshold with formal business sign-off.

This changes team dynamics. "Did quality improve?" stops being a debate and becomes a number. Braintrust and Promptfoo both provide CI/CD integration for this pattern — Braintrust for automatic PR regression detection, Promptfoo for OWASP-aligned security red-teaming. (Augment Code, 2026; Zylos Research, 2026)

### 5. Calibrate LLM-as-judge with a golden set

LLM judges introduce non-determinism into the grader itself. Calibrate by running the judge against a small set of human-annotated examples and measuring agreement. A judge that disagrees with human annotators on 30% of cases is unreliable at measuring your agent. As one HN commenter put it: "LLMs don't have taste — it's easy to get an LLM to give praise, and easy to get an LLM to give criticism, but getting an LLM to praise good things and criticize bad things is currently impossible for non-trivial inputs." Calibrate using trial and error, prompt optimization (e.g., DSPy), or a small correction model on top of judge outputs (e.g., LLM-Rubric, Prediction Powered Inference). (HN, "Principles for production AI agents," 2025)

### 6. Use trajectory-level evaluation for multi-step agents

Don't evaluate only the final output. Evaluate the full execution path — which tools were called, in what order, with what arguments, and whether intermediate states were correct. AWS Labs Agent Evaluation framework provides structured evaluators for agent trajectories with support for multiple targets (Amazon Bedrock, Bedrock Knowledge Bases, Amazon Q Business, SageMaker). Trajectory evaluation catches failures that final-output checks miss, like calling the right tool with wrong arguments, or taking an inefficient path that happens to arrive at the right answer. (AWS Labs, agent-evaluation GitHub, 2025)

## Evidence

- **Academic paper:** "Constraint Decay: The Fragility of LLM Agents in Backend Code Generation" — EURECOM researchers tested agents across 80 greenfield and 20 feature-implementation tasks spanning 8 web frameworks. Assertion pass rates dropped by an average of 30 percentage points from unconstrained to fully specified tasks, revealing that agents collapse under accumulated structural constraints. The paper calls this "constraint decay" and notes it affects all model families tested. — [https://arxiv.org/abs/2605.06445](https://arxiv.org/abs/2605.06445) (arXiv, May 2026; discussed on HN, 2026)
- **HN discussion (128 points, 19 comments):** Thread on "Principles for production AI agents" surfaced the "LLMs don't have taste" observation about LLM-as-judge calibration, the critical importance of having evals at all ("If you don't have evals, you really don't know if you're moving the needle at all"), and the shift from vibe-based to evidence-based agent quality management. — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315) (Hacker News, 2025)
- **Industry survey:** LangChain's 2026 State of AI Agents found 57% of organizations have agents in production, with 32% citing quality as the single biggest barrier to wider deployment. The 37% gap between benchmark scores and real-world performance is documented across multiple sources. — [https://zylos.ai/research/2026-04-20-ai-agent-testing-strategies-simulation-regression](https://zylos.ai/research/2026-04-20-ai-agent-testing-strategies-simulation-regression) (Zylos Research, 2026)
- **Open-source tool:** Giskard (5,597 stars, Apache-2.0) — modular, async-first open-source library for evals, red-teaming, and test generation for agentic systems. v3 is a full rewrite for dynamic multi-turn agent testing. — [https://github.com/Giskard-AI/giskard-oss](https://github.com/Giskard-AI/giskard-oss) (GitHub, active 2022–present)
- **Open-source tool:** TruLens (3,445 stars, MIT) — evaluation and tracking for LLM experiments and AI agents with stack-agnostic instrumentation. Captures every retrieval call, rerank, and prompt as a structured span for trajectory-level debugging. — [https://github.com/truera/trulens](https://github.com/truera/trulens) (GitHub, active 2020–present)
- **Open-source tool:** LangChain AgentEvals (646 stars, MIT) — readymade evaluators for agent trajectories with trajectory-match and LLM-as-judge approaches. — [https://github.com/langchain-ai/agentevals](https://github.com/langchain-ai/agentevals) (GitHub, Feb 2025)
- **Cloud tool:** AWS Labs Agent Evaluation — structured evaluators for agent trajectories supporting Bedrock, Bedrock KBs, Amazon Q Business, and SageMaker targets. — [https://awslabs.github.io/agent-evaluation](https://awslabs.github.io/agent-evaluation) (AWS Labs, 2025)

## Gotchas

- **Golden datasets grow stale.** Test cases built on last quarter's production failures may not cover new edge cases from this quarter's traffic. Treat the dataset as a living artifact — review and prune quarterly, add from production continuously.
- **LLM-as-judge agreement varies by domain.** A judge calibrated on code generation quality may not transfer to customer service tone. Build domain-specific rubrics; don't reuse judge prompts across qualitatively different tasks.
- **Statistical runs are expensive.** 10 runs per test × 100 test cases × expensive API calls = real money. Budget for eval infrastructure the same as you budget for CI infrastructure. Consider smaller models as judges for cost efficiency (e.g., SLMs like Luna-2 for hallucination detection per the Galileo approach).
- **Coverage metrics lie.** High coverage percentage (e.g., "we test 80% of our tool calls") doesn't mean the 20% you don't test are safe. It means your imagination has limits. Synthetic generation from production failures is the only way to catch the blind spots.
- **Constraint decay is architectural, not fixable by better models.** The EURECOM paper found that performance degradation under accumulated structural constraints persists across model families and frameworks. Better models reduce absolute error rate, but the decay pattern — performance dropping as structural constraints accumulate — is a consequence of token-by-token generation, not a model capability gap. The practical fix is better tooling around the agent: structural verifiers in the loop, framework-specific evaluators, and explicit constraint checking. Don't expect the next model to solve it.
