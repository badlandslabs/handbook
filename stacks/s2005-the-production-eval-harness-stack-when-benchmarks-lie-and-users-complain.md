# S-2005 · The Production Eval Harness Stack — When Benchmarks Lie and Users Complain

Your agent scores 77% on SWE-bench Verified. Your users are still filing bugs. The gap isn't a model problem — it's an evaluation problem. Benchmarks measure narrow task completion in controlled environments. Production agents face real APIs, rate limits, auth rot, schema drift, and users who give inputs nobody predicted. Without a structured eval harness, you find out your agent regressed when users tell you.

## Forces

- **Agents are nondeterministic in a way traditional software isn't.** A task can be completed correctly via multiple valid paths, and "correct" itself can be subjective. Your test suite can't just assert `expected_output == actual_output`.
- **Failures cascade across steps.** An agent completes steps 1–4 correctly, then calls a tool that returns an unexpected schema. The task is marked failed, but 80% of the work is lost unless you track state explicitly.
- **Success is context-dependent.** The same prompt produces different code depending on the repo state. The same search query returns different results depending on the API version. Your eval must account for environmental variation, not just agent behavior.
- **The benchmark-reality gap is measurable.** SWE-bench Verified scores of ~77% correlate with 12–18% tool call failure rates in production deployments. Benchmarks run in clean containers; production runs on real infrastructure with real instability.
- **Eval quality compounds.** Each eval run teaches you something about your agent. Without a harness, you learn from user complaints — the slowest feedback loop in engineering.

## The move

Build an eval harness before you ship, and treat it as a first-class engineering artifact, not a testing afterthought.

### Golden sets over benchmark scores

Construct a **golden set**: curated input-output pairs representing real production scenarios and edge cases. Start with 20–50 high-value cases (top user intents, known failure modes, compliance-critical paths). Add cases from every production incident. For deterministic outputs, use exact-match assertions. For open-ended tasks, use LLM-as-judge — a separate model evaluates whether the agent's output meets the success criteria.

**Hierarchical eval structure:**
1. **Task-level:** Did the agent complete the goal? (pass/fail)
2. **Step-level:** Did each tool call succeed? Were the arguments correct? (detailed breakdown)
3. **Quality-level:** Was the output good, not just present? (LLM-as-judge, human review)

### Step-level eval for ReAct loops

Anthropic's 2026 eval guidance recommends tracking each step in multi-turn agent loops separately. If an agent fails at step 3 of 7, you don't just know it failed — you know *which step* failed and why. This makes debugging tractable instead of guesswork. Store trajectory data (input → tool call → observation → next step) so you can replay failures.

### Incorporate production traffic sampling

The best offline eval harness still misses what users actually do. Sample real production interactions, auto-generate test cases from them, and feed them back into the golden set. This creates a feedback loop: production → eval → improved agent → better production.

### Define your eval cadence

Offline evals run on every commit (CI gate). Shadow mode evals run on a percentage of production traffic without affecting users. Full production mode is for critical regressions only. The cadence keeps the harness fast enough to gate merges without requiring constant maintenance.

### Treat the harness as testable itself

Your eval harness can have bugs too — false positives that fail a good agent, false negatives that pass a broken one. Run the harness against known-good and known-bad agent variants to calibrate. Cross-reference with user-reported issues to catch evals that are gaming the metric instead of measuring quality.

## Evidence

- **Engineering Blog:** Anthropic's eval guidance recommends hierarchical task/step/quality evals and emphasizes that "the strategies that work across deployments combine techniques to match the complexity of the systems they measure" — [Anthropic Engineering: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (Jan 2026)
- **Production Data:** SWE-bench Verified scores of ~77% correlate with 12–18% tool call failure rates in production deployments. Root cause: benchmarks run in controlled containers; production involves real APIs, rate limits, auth rot, and real-time failure decisions — [AgentMarketCap: Agent Tool Call Failures in Production](https://agentmarketcap.ai/blog/2026/04/10/agent-tool-call-retry-failure-mode-handling-production-2026) (Apr 2026)
- **Analyst Report:** Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps — [Gartner: AI Risk Management Predictions](https://www.gartner.com/en/articles/what-is-ai-risk-management) (2026)
- **Engineering Blog:** Neo4j's field CTO documents that most agent failures in production stem from insufficient or poorly organized context, not model limitations — [Neo4j: AI Agent Case Studies](https://neo4j.com/blog/agentic-ai/ai-agent-useful-case-studies/) (Feb 2026)

## Gotchas

- **Task-completion-only evals miss half the failure modes.** If your harness only checks whether the agent finished, you'll never catch that it's taking 3x the expected steps, calling the wrong tools, or producing subtly incorrect outputs that look right.
- **Golden sets decay in production.** User behavior changes, APIs evolve, and edge cases you didn't anticipate become common. Evals that aren't actively maintained become noise — passing for broken agents and failing for working ones. Budget ongoing maintenance, not just initial construction.
- **LLM-as-judge can be gamed or inconsistent.** Judge models have their own biases and failure modes. Validate judge decisions against human review periodically, especially for high-stakes or compliance-critical outputs.
- **Eval harness latency matters for CI.** If your eval suite takes 45 minutes to run, developers will skip it. Prioritize a fast subset (~5 min) for the CI gate, and reserve full suites for nightly or pre-release runs.
- **Shadow mode sampling rates are a cost-quality trade-off.** Too low and you miss regressions. Too high and you spend significant inference budget on non-user-facing evaluation. Monitor cost-per-failure-caught and tune accordingly.
