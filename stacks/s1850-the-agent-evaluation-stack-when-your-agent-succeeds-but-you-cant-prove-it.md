# S-1850 · The Agent Evaluation Stack — When Your Agent Succeeds But You Can't Prove It

Your agent answers questions, calls tools, completes tasks. It never crashes. Your logs show clean traces. But you have no idea if it's actually getting better or worse across model versions, whether your latest prompt change helped, or whether the agent is completing 40% or 80% of tasks. This is the agent evaluation problem: the harder question of whether the agent is doing the right thing, not just doing something.

## Forces

- **Final-answer eval misses the point** — an agent can reach a correct answer via a catastrophic trajectory (30 wasted tool calls, a policy violation, a hallucinated ID sent to a payment system). A pass/fail on the output hides all of this.
- **Agents are non-deterministic** — the same input can produce different tool sequences, different reasoning paths, different end states. A single run tells you almost nothing.
- **Synthetic benchmarks diverge from production** — the community's most-cited evals (SWE-Bench, Tau-Bench) test agent scaffolding on toy problems. Your agent's actual failure modes are in your specific tool chain, your specific data, your specific edge cases.
- **Evaluation cost compounds** — running LLM-as-judge on every production trace is expensive. Running a human-in-the-loop on every failure is slow. Teams default to "it looks fine" because proper evaluation is expensive.
- **Eval data is the moat, not the framework** — DeepEval runs 600K evaluations/day in CI across BCG, AstraZeneca, AXA. The differentiator isn't the framework. It's the test cases. The teams winning are the ones with curated failure-case datasets, not better tooling.

## The Move

Build a layered evaluation system across three levels, using production traces as the primary source of truth:

**1. Define success criteria before the first eval runs.** Answer: what does "the agent did its job" actually mean? Task completion (binary end-state)? Trajectory quality (right tools, right order, no loops)? Per-turn correctness (did this specific step make sense)? Each layer answers a different question. Don't collapse them into one metric.

**2. Capture production traces, not just outcomes.** Instrument the agent to record every LLM call, tool invocation, tool result, and state transition as a structured trace. The trace is the primary artifact. The final output is just the last entry. Capturing traces costs almost nothing; it enables everything.

**3. Build the eval dataset from real failures, not synthetic scenarios.** The MrTalecky/agent-evals framework captures this philosophy precisely: "Don't guess what's broken. Let the agent fail, record the failure, never repeat it." When the agent fails in production, add the exact input + correct output to your test suite. Synthetic benchmarks can't anticipate your specific tool chain quirks.

**4. Evaluate at three layers, not one:**
- **Final-answer layer** — did the agent achieve the correct end state? Binary or partial credit.
- **Trajectory layer** — did the agent follow a sensible path? Did it call the right tools? Did it loop? Did it recover from errors? This is where TheAgentCompany benchmark lives: even the best model (Gemini 2.5 Pro) achieves only 30.3% full task completion on real-world office tasks.
- **Per-turn layer** — at each reasoning→action→observation cycle, was this step correct? One forward pass, <90ms latency, catch drift before it compounds.

**5. Choose your judge by what you're measuring.** Deterministic checks (exact match, JSON schema validation, tool-name match) for things that don't require judgment. LLM-as-judge for tone, reasoning quality, policy adherence, and anything requiring context. The four documented LLM-as-judge failure modes (positional bias, verbosity bias, self-preference, known-answer bias) mean you need guardrails — calibration examples, reference grounding, and multi-judge voting.

**6. Run evals in CI, not just manually.** DeepEval's 600K/day figure comes from CI integration, not ad-hoc human runs. The eval suite should fire on every prompt change, model swap, or tool-chain modification. If you only run evals when you remember to, you have no trend line.

**7. Track cost-per-task alongside quality.** TheAgentCompany benchmark includes cost-per-instance as a first-class metric: `Cost = (Prompt tokens × token cost) + (Completion tokens × token cost)`. An agent that achieves 90% task completion at 3× the cost of a competitor isn't clearly better. Efficiency and quality are both required.

## Evidence

- **GitHub repo / framework:** `MrTalecky/agent-evals` — minimal production-failure-driven eval loop. Agent fails → case added to `cases.json` with correct answer → `score.py` runs → agent improves. Zero external dependencies beyond the Anthropic API. Philosophy: real failures as test cases, not synthetic predictions.
- **Company engineering blog / survey:** TheAgentCompany benchmark (arXiv:2412.14161v2, `the-agent-company.com`) — evaluates agents on real professional tasks in a simulated company: browse web, write code, run programs, send emails. Finding: best model achieves 30.3% full autonomous completion on consequential real-world tasks. Documents cost-per-instance as a first-class metric.
- **HN discussion / framework:** DeepEval (YC W25, `confident-ai.com`, `github.com/confident-ai/deepeval`) — 600K evaluations/day in CI across enterprise users including BCG, AstraZeneca, AXA, Capgemini. Differentiator is eval dataset quality, not framework features. Four-layer metric taxonomy: task completion, tool calling, planning/reasoning, safety.
- **HN discussion / critique:** "Why eval startups fail" (HN:110pts, `thomasliao.com/eval-startups`) — independent eval startups die because the same talent that builds good evals is more valuable building post-training pipelines. Key insight: eval data quality >> eval framework choice. The teams with curated production-failure datasets win; the teams chasing better tooling lose.
- **Industry guide / framework comparison:** Agent eval frameworks in 2026 split into two families: code-first frameworks for offline CI gates (DeepEval, promptfoo, RAGAS) and eval-plus-observability platforms for production tracing (LangSmith, Langfuse, Arize Phoenix, Braintrust). Most teams use one from each family. DeepEval leads on breadth (50+ metrics, pytest-native), RAGAS leads on retrieval-specific metrics, LangSmith leads for LangChain stacks, Braintrust leads for SaaS-first teams wanting logging + eval + prompt management in one place.
- **HN post / startup launch:** Confident AI launch (HN:117pts, `news.ycombinator.com/item?id=43116633`) — "Think Pytest for LLMs." Enterprise traction cited as evidence that eval-as-code is the engineering-led deployment shape, not a niche preference.

## Gotchas

- **Synthetic benchmarks predict nothing about your agent** — TheAgentCompany's 30.3% full completion rate on realistic tasks should humble every team that assumes their agent "works fine." Benchmark performance ≠ production performance on your specific tool chain.
- **LLM-as-judge has documented failure modes** — positional bias (prefers first/second answer), verbosity bias (rewards longer outputs), self-preference (prefers outputs similar to its own style), known-answer bias (over-confident on topics it knows). You must calibrate judges against reference examples, not just prompt them and hope.
- **Cost-per-task is a first-class metric, not an afterthought** — trajectory quality and task completion mean nothing without efficiency. An agent with 95% task completion at 5× cost is not a 95th-percentile agent.
- **Eval suites drift faster than agents** — as your agent improves, your eval dataset must expand. Yesterday's edge case is tomorrow's expected input. The teams that treat evals as a one-time setup project find their eval accuracy degrading silently over months.
- **Human-in-the-loop is irreplaceable for policy violations** — no eval framework catches novel policy violations, novel hallucinations into real systems, or novel failure modes that don't match existing test patterns. Automated evals are a floor, not a ceiling.
