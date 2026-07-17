# S-1256 · The Agent Evaluation Stack — When You Ship on Vibes and Find Out in Production

You changed the system prompt on a Tuesday. It felt right in your five manual test cases. By Thursday it was live, and forty-seven users had gotten mangled responses before someone filed a bug report. Nobody caught it because nobody had a test that could. The agent "worked" until it didn't — and you had no way to know the difference.

## Forces

- **Agents are non-deterministic but your users need consistent behavior.** The same input can produce different outputs. Traditional `assert output == expected` fails immediately — but ignoring quality measurement entirely means you ship blind.
- **Discovery mode and defense mode are different jobs.** Manual testing answers "can this agent do X?" Evaluations answer "does this agent still do X after my changes?" Teams conflate them and skip the second.
- **Evaluation quality compounds; its absence compounds faster.** An eval suite that grows from production failures stops each failure from happening twice. Without it, you fix the same bug class in four branches across six months.
- **LLM-as-judge is powerful but requires its own calibration.** You can evaluate subjective qualities (tone, helpfulness, reasoning clarity) with a model — but the judge itself drifts and needs meta-evaluation.

## The Move

Build a three-layer evaluation stack that runs before every deploy and feeds back from production:

**Layer 1 — Evals as pre-deploy gate.**
Every prompt change, model swap, or tool modification triggers an eval run. The commit is blocked if scores regress. Structure evals as: **data** (test cases) + **task** (your agent logic) + **scorers** (grading functions). Run each test case multiple times to account for non-determinism.

**Layer 2 — Multi-level grading.**
Use three grader types in combination, not isolation:
- **Code-based graders** for deterministic checks — did the agent call the right tool with the right arguments? Did it return a structured output in the right format? These are fast, cheap, and objective.
- **LLM-as-judge** for nuanced qualities — is the response helpful? Is the tone appropriate? Is the reasoning sound? These require flexibility but introduce non-determinism in the grader itself. Calibrate with a small golden set of human-rated examples.
- **Human graders** for edge-case calibration and judge auditing. Expensive and slow — reserve for validating that your other graders are accurate.

**Layer 3 — Step-level and trajectory-level evaluation.**
Agents fail at two granularities: individual steps and the full chain. Score each tool call in isolation (did `check_policy` receive the right arguments?) AND the end-to-end trajectory (did the user get their refund?). A perfect final answer that called the wrong tool three times first is still a failure.

**Layer 4 — Production traces → regression tests.**
When a failure reaches production, extract the interaction, anonymize sensitive data, and add it to the eval suite permanently. This converts one-off incidents into durable prevention. The eval now says "this failure mode is unacceptable" and will catch it before the next deploy.

**Layer 5 — Continuous behavioral monitoring.**
Model weight shifts, upstream data changes, and tool API modifications can degrade agent quality without changing the code. Track key metrics (task completion rate, tool call accuracy, trajectory length, cost per task) over time and alert on regressions between eval runs.

## Evidence

- **Anthropic Engineering Blog:** "Demystifying Evals for AI Agents" (Jan 2026) — introduces the three grader types, distinguishes query agents from tool-using agents from subagent orchestration, and emphasizes running evals as a pre-deploy gate. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Google Cloud Blog:** "From Vibe Checks to Continuous Evaluation" (2026) — documents the shift from reactive discovery testing to systematic defense with production trace capture and CI-gated evaluation. — [URL](https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents)
- **Hacker News Discussion:** "Principles for Production AI Agents" (#44712315, 128 points) — practitioners unanimously identify evaluation as the foundational practice; HN user roadside_picnic: "Over, over again my experience building production AI tools has been that evaluations are *vital* for improving performance." — [URL](https://news.ycombinator.com/item?id=44712315)
- **Braintrust Blog:** "How to Eval LLMs and AI Agents in Production" (May 2026) — documents the eval loop pattern (data + task + scorers), production trace → test case feedback, and Notion's reported 10x velocity improvement after adopting structured evaluation. — [URL](https://www.braintrust.dev/articles/how-to-eval)
- **Show HN:** "Zalor — Automated Testing for AI Agents" (2025) — agents.zalor.ai: targets the specific problem of behavioral regressions caused by system prompt changes and tool modifications; runs automated regression suites against agent trajectories. — [URL](https://news.ycombinator.com/item?id=47270208)
- **Agents in Production 2025 Conference:** Annie Condon & Jeff Groom talk on "Evaluating AI Agents: Why It Matters and How We Do It" — frames evaluation as essential for delivering reliable, safe, effective agents aligned with user intent. — [URL](https://home.mlops.community/public/collections/agents-in-production-2025-2025-07-23)

## Gotchas

- **Length bias poisons LLM-as-judge scores.** Longer responses score higher even when no better. Fix: add an explicit conciseness criterion in the rubric to penalize padding.
- **A single eval run is not a verdict.** Run each test case 3-5 times and aggregate. A single pass on a non-deterministic system is noise.
- **Evals drift too.** If you're using an LLM as a judge, re-calibrate it quarterly against a human-rated golden set. A judge that hasn't been audited will misfire silently.
- **Coverage is not binary.** You can't evaluate "does the agent behave well?" with a single pass. Build eval datasets that represent the distribution of real user requests — including adversarial, ambiguous, and edge-case inputs.
- **Step-level scoring alone misses trajectory failures.** An agent that calls every tool correctly but in the wrong order can still fail end-to-end. Always evaluate both levels.
