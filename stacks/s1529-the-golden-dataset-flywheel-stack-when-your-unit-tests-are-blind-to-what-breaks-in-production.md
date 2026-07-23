# S-1529 · The Golden Dataset Flywheel Stack — When Your Unit Tests Are Blind to What Breaks in Production

Your agent passed every unit test, every lint check, and every integration run. It still broke in production — silently, in a way no engineer anticipated. The agent produced the correct answer through an incorrect process, called the wrong tool with the right arguments, and surfaced a stale data source as if it were current. Your test suite never caught any of it because it was designed for functions, not reasoning systems. This is the Golden Dataset Flywheel: the pattern that converts every production failure into an unskippable release gate, so the same failure cannot ship twice.

## Forces

- **Agents are non-deterministic by design.** The same task can succeed through different tool-call sequences, fail for unrelated reasons on retry, or succeed and fail simultaneously (correct output, broken process). Your standard `assert output == expected` can't hold any of this.
- **Synthetic test data misses the real distribution.** Hand-crafted prompts cover what engineers can imagine. Production surfaces what engineers could not have invented — authentic edge cases, real input drift, surprising tool interactions.
- **The eval flywheel is easy to defer and hard to recover from.** Teams skip building eval infrastructure at launch because it's "not urgent." By the time they have enough production failures to build a useful dataset, they've accumulated months of un-captured traces and are retrofitting observability into a system that was never instrumented for it.
- **Benchmarks tell you relative model quality, not absolute system quality.** AgentBench, SWE-bench, and WebArena rank models on standardized tasks. They do not tell you whether *your* agent will call *your* APIs correctly on *your* input distribution. That number only comes from your own data.

## The move

The Golden Dataset Flywheel converts production failures into permanent, automatically-executed regression tests. It runs continuously, gets sharper with every incident, and gates every release.

**Step 1 — Instrument traces before you need them.**
Every agent run should produce a structured trace: user input, tool calls with arguments and outputs, intermediate reasoning steps, final output, and execution time. Capture this in production at sampling rate (1–10% depending on cost sensitivity) and always at 100% on failures. If you only capture on failure, you have no baseline to compare against.

**Step 2 — Convert failures into test cases automatically.**
When a production failure occurs, the trace becomes a candidate test case. A human annotator reviews it, labels the expected behavior, and adds it to the golden dataset. Even a single annotator adding 3–5 cases per week builds a meaningful regression suite in months. Per Arthur AI's analysis, 20–50 high-signal production cases is a strong starting point — enough to catch regressions without drowning in noise.

**Step 3 — Build the flywheel loop.**
```
Production Failure → Trace Capture → Human Annotation → Golden Dataset → CI/CD Release Gate → Regression Caught → Next Failure Detected Sooner
```
Run the golden dataset on every prompt change, model swap, retrieval pipeline update, and tool API modification. A regression in the suite means the new version must not ship — no exceptions.

**Step 4 — Combine deterministic checks with LLM-as-judge.**
Deterministic checks (schema validation, exact-match assertions, tool-call signature verification) are fast, cheap, and unambiguous — use them as the first gate. LLM-as-judge handles the cases that need reasoning: Was the planning coherent? Did the agent recover appropriately from the tool error? Did the output tone match brand guidelines? See s1526 (judge calibration) for the failure modes of this layer.

**Step 5 — Track trajectory-level metrics, not just outcome.**
Two runs can produce identical correct outputs through very different trajectories. The correct trajectory matters because it predicts future reliability: an agent that gets lucky via wrong reasoning is more likely to fail on the next input. Key trajectory metrics include:
- **Tool selection accuracy** — did it call the right tool?
- **Planning coherence** — did subgoals map to the actual task?
- **Error recovery** — did it detect and correct its own mistakes?
- **Efficiency** — did it reach the goal in a reasonable number of steps?

**Step 6 — Choose pass@k vs pass^k based on cost tolerance.**
From τ-bench (Mastra AI's analysis): `pass@k` (succeeds at least once in k attempts) applies when one correct answer suffices and retries are cheap. `pass^k` (succeeds every time in k attempts) applies when consistency matters more than raw success — financial transactions, compliance outputs, medical decisions. Measuring the wrong metric gives you false confidence.

## Evidence

- **Survey:** LangChain's State of Agent Engineering 2026 (1,340 practitioners, Nov–Dec 2025) found **quality is the #1 production blocker at 32%** — nearly 14 points above the overall average for small companies at 45.8%. 57% of organizations have agents in production, but 32% cite quality as the top barrier. This is the problem the flywheel solves. — [LangChain State of Agent Engineering 2026](https://www.langchain.com/state-of-agent-engineering)
- **Primary source — production-to-test pipeline:** Arthur AI's analysis describes the flywheel explicitly: "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures. Every time an agent does something wrong in front of a real user, it hands you a test case you could not have invented." A production failure becomes a trace, the trace becomes a test case, the test case joins the golden dataset, and the golden dataset becomes a release gate in CI/CD. — [Arthur AI — Regression Test Datasets From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Primary source — layered eval framework:** Google Cloud's evaluation guide (November 2025) describes three complementary data sources for golden datasets: (1) synthetic conversations generated by "dueling LLMs" for scale, (2) anonymized production user interactions for authenticity, and (3) human-in-the-loop curation of saved interactive sessions from logs and traces. Their five eval dimensions — task success, trajectory quality, tool selection, efficiency, and safety — provide the measurement schema for the flywheel's output. — [Google Cloud — A Methodical Approach to Agent Evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Benchmark gap:** AgentBench (Liu et al., 2024) evaluates across 8 distinct environments, but its ~1,000 aggregated cases represent the intersection of what researchers could operationalize, not the tail of what production users actually do. SWE-bench evaluates repository-level code repair; WebArena evaluates web automation. None of these tell you whether your customer-service agent handles your specific edge cases. The gap between benchmark performance and production performance is the space the flywheel occupies. — [AgentBench on OpenReview](https://openreview.net/forum?id=zAdUB0aCTQ)

## Gotchas

- **Traces without instrumentation are useless.** If you wait until a failure to start capturing traces, you have no data on the "correct" version's behavior for comparison. Instrument first; evaluate later. Retrofitting tracing into an untraced agent is an order of magnitude harder than instrumenting from the start.
- **Golden datasets drift.** Input distributions change, product features evolve, and test cases that were representative six months ago may no longer match production. Prune or relabel stale cases quarterly, or the dataset becomes a false-positive machine that blocks valid changes.
- **LLM-as-judge needs its own regression test.** The judge model can itself regress — a prompt change to the judge can make it more lenient or more severe, changing your quality gate without changing the agent. Track judge agreement rates against human annotation over time. See s1526 (judge calibration) for the full failure taxonomy.
- **Sampling in production creates blind spots.** If you only sample 1% of successful runs, you won't catch the class of failure that happens in 5% of cases. Calibrate sampling rate against known failure frequency, not just cost budget.
- **pass@k hides consistency failures.** Measuring only `pass@1` on a task where `pass@5 = 95%` but `pass^5 = 60%` tells you the agent can succeed with enough retries — not whether it will succeed reliably in production. Know which metric maps to your actual risk.
