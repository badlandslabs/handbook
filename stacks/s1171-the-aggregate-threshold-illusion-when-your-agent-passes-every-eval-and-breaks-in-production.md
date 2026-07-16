# S-1171 · The Aggregate Threshold Illusion: When Your Agent Passes Every Eval and Breaks in Production

Your agent scores 91% on your eval suite. You ship confidently. Three days later, users report a support agent that confidently misbooks appointments, citing the wrong policy documents — but the final answer happens to be correct, so no check caught it. The eval suite didn't know what to look for. It never does.

This is the aggregate threshold illusion: a single pass/fail number hides the specific dimensions that kill production reliability.

## Forces

- Offline evals on curated golden sets catch known failure modes but miss everything users actually do
- LLM-as-judge scales scoring but can be gamed, biased, and inconsistent across runs
- Traditional accuracy metrics miss the trajectories that produce outputs — an agent can succeed for the wrong reasons
- Teams set one aggregate threshold ("≥ 0.85 to ship") and hide a 0.62 on argument extraction behind a 0.97 on tool selection
- Silent model drift (providers update models without semantic version bumps) makes last week's passing eval meaningless this week
- Agents make 3–10x more LLM calls than chatbots — cost-per-task is a first-class production concern traditional evals ignore

## The Move

Measure three orthogonal layers, with per-dimension assertions, not aggregate scores. Wire the harness into CI so it blocks deploys that regress.

**Three-layer eval architecture:**
- **Offline regression suite** — golden dataset of labeled (input, expected trajectory, expected output) triplets. Catches obvious regressions on known failure modes. Run on every PR. Triggers in seconds with pinned model snapshots.
- **Shadow eval on sampled production traffic** — copy a percentage of live requests, run them through the eval harness without affecting users. Catches distribution shift and edge cases that never made it into the golden set.
- **Human-in-the-loop curation** — log interactive sessions, let humans flag failures, promote logged failures into permanent golden cases. The golden set grows from production, not from imagination.

**Per-dimension assertions instead of aggregate thresholds:**
- Assert `tool_selection_f1 >= 0.95 for 95% of cases`
- Assert `argument_validation_score >= 0.90 for 90% of cases`
- Assert `trajectory_efficiency_score >= 0.80` (not just outcome success)
- Assert `cost_per_task <= $X` for cost-sensitive use cases
- Block deploy if any dimension drops below its threshold

**Trajectory evaluation — evaluate the path, not just the destination:**
- Did the agent use the correct tools in the correct order?
- Did it skip a diagnosis step and get lucky?
- Did it hallucinate a tool call or misread a tool's response?
- Did it recover gracefully from a failed sub-step?
- Tool alignment score: compare expected trajectory (golden) vs actual trajectory, step by step

**Drift detection:**
- Track rolling win rates per eval dimension on sampled production traffic
- Alert when any dimension's 7-day moving average drops by >5%
- Re-pin model snapshots when provider updates land silently

## Evidence

- **Blog post (72Technologies):** "Unit tests don't catch agent regressions. Building an eval harness that runs in CI, fails fast on real breakages, and doesn't bankrupt you on token spend requires a fundamentally different testing approach." Documents non-determinism even at `temperature=0`, silent model drift, and compound failure surfaces as three factors that break traditional testing. — [https://www.72technologies.com/blog/agent-evals-ci-regression-tests](https://www.72technologies.com/blog/agent-evals-ci-regression-tests)

- **Google Cloud Blog:** "An agent can produce a correct output through an inefficient or incorrect process—what we call a 'silent failure'. For instance, an agent tasked with reporting inventory might give the correct number but reference last year's report by mistake." Proposes three eval layers: trajectory, agentic interaction, and manipulation resistance. — [https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)

- **Medium (Vinod Rane, Senior SWE at BBC):** "Most teams implement a single aggregate eval threshold 'overall score must be ≥ 0.85 to ship.' This is how you hide a 0.62 on argument extraction behind a 0.97 on tool selection and ship a broken agent with confidence." Documents per-dimension assertion config with concrete thresholds. — [https://medium.com/@vinodkrane/chapter-8-agent-evaluation-for-llms-how-to-test-tools-trajectories-and-llm-as-judge-788f6f3e0d52](https://medium.com/@vinodkrane/chapter-8-agent-evaluation-for-llms-how-to-test-tools-trajectories-and-llm-as-judge-788f6f3e0d52)

## Gotchas

- **Golden sets rot.** A dataset built in January reflects January's tool schema, January's prompt, and January's model behavior. Prompts and tools change; the golden set doesn't unless you actively curate it from production logs.
- **LLM-as-judge has its own failure modes** — position bias (favoring the first output when comparing two), verbosity bias (favoring longer, more elaborate responses), and self-preference bias (favoring outputs similar to the judge's own style). Target 0.80+ Spearman correlation with human judgment before relying on it.
- **You cannot evaluate what you cannot trace.** If you don't have structured traces of each tool call, its arguments, and its result, trajectory evaluation is impossible. Instrument your agent before you try to evaluate it.
- **Offline eval passing is necessary but not sufficient.** It tells you the agent didn't regress on known cases. It tells you nothing about what users will actually do or which edge cases your golden set missed.
