# S-1249 · The Eval Stack: When Your Agent Passes Every Test and Still Fails in Production

Your agent scores 87% on your eval suite. Your users say it's broken. The benchmark says green. The production trace says it called the wrong API 12 times in a row, retried a failed auth token 7 times, and produced output that looked plausible and was completely wrong. Your eval was measuring the wrong thing.

## Forces

- **Standard LLM benchmarks measure the model, not the system.** Single-turn accuracy, ROUGE scores, and leaderboard rankings tell you nothing about whether your agent selects the right tools, recovers from errors, or prevents silent cascades of bad data through a multi-step trajectory.
- **Benchmarks are contaminated.** UC Berkeley research found SWE-bench Verified scores inflated by 30+ percentage points due to training data contamination. SWE-bench Pro and SWE-bench Live exist as cleaner alternatives, but most teams still use the contaminated variant. — [PaperClipped.de, AI Agent Benchmarks Explained](https://www.paperclipped.de/en/blog/ai-agent-benchmarks-swe-bench-webarena)
- **Errors cascade through trajectories.** An early wrong tool call doesn't cause a crash — it produces subtly bad data that the next step treats as valid input. By the time the final output looks wrong, the failure is buried 6 steps deep. Scoring only the final output is structurally blind to this.
- **Non-determinism means a passing score today can fail tomorrow.** The same agent on the same task produces different results each run due to sampling. A single eval run is a sample, not a verdict.
- **The input space is unbounded.** Unlike traditional software, you cannot enumerate every possible input. Production distributions surface edge cases no engineer would have invented.
- **Eval is downstream of architecture, not a substitute for it.** Picking DeepEval over Ragas, or Braintrust over LangSmith, is the wrong first question. The right first question is what your eval *architecture* looks like. — [Big Data Boutique, LLM Evaluation in Production](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)

## The Move

Build a three-layer eval architecture, score trajectories not outputs, mine regression cases from production, and instrument circuit breakers.

### Layer 1 — Offline regression suite (CI/CD gate)

Run before every deploy. Fast, deterministic, high-confidence.

- **Deterministic checks first:** exit status, required files present, output format, credential boundaries, API response schema. These catch the class of failures that deterministic checks can catch — they are cheap and reliable.
- **Trajectory scoring, not just output scoring.** Score the plan, tool selection, tool arguments, and completion — not just the final assistant message. A bad tool call in step 2 corrupts everything after it. — [Braintrust, AI Agent Evaluation Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Score every span, not just the final output.** Individual tool-call quality matters independently of end-to-end task success. — [FutureAGI, Best LLM Evaluation Frameworks 2026](https://futureagi.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **Every confirmed production failure becomes a frozen regression case.** Promote prod failures into test cases, not just bug tickets. This is the highest-signal dataset you will ever get — an authentic edge case with a real input and a concrete definition of "broken." — [Arthur.ai, Regression Test Datasets From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

### Layer 2 — Shadow evaluation (live traffic sampling)

Mirror production traffic through the eval harness without affecting real users.

- **Sample 1-5% of live requests** through the eval suite. This catches the distribution gap between your eval dataset and real user behavior.
- **Run three experiment types at the right level of isolation:** prompt experiments (fastest, swap prompt version against known inputs), RAG experiments (catches silent failures where bad context produces confident wrong answers), and agent experiments (end-to-end, most expensive, most realistic). — [Arthur.ai, Regression Test Datasets From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Calibrate LLM judges against human labels.** An LLM judge that hasn't been validated against human ground truth produces confident wrong scores. Run human-in-the-loop calibration on a subset before trusting automated scoring at scale.

### Layer 3 — Online monitoring (production observability)

Track what is actually happening in deployed agents.

- **Track the five critical metrics:** task completion rate (did the agent finish the job?), regression introduction rate (did changes to the agent break things that were working?), review loop count (how many times did a human have to intervene?), blast radius on failure (when it breaks, how bad?), and trajectory efficiency (steps per task, cost per task). — [Adaline Labs, Evaluating Coding Agents in Production](https://labs.adaline.ai/p/evaluate-coding-agents-production)
- **Implement sliding-window meltdown detection** over tool-call sequences. Repeated identical tool calls, rapidly growing context without measurable progress, or tool outputs that contradict earlier successful calls are meltdown precursors. — [PaperClipped.de, AI Agent Benchmarks](https://www.paperclipped.de/en/blog/ai-agent-benchmarks-swe-bench-webarena)
- **Distinguish "tool ran and found nothing" from "tool error."** Both return a value to the agent; the LLM marks the step complete in both cases. This is the equivalent of HTTP having 200 but no 404. Add a ToolResolutionError exception class so the model can retry instead of silently passing garbage forward. — [HN Show HN: Forge — Guardrails for 8B models](https://hacker-news.penportal.net/item/48192383)

### The eval-framework stacking pattern

Different frameworks are strongest at different surfaces. Use them together:

- **DeepEval** — CI regression, offline test suites, fastest feedback loop
- **Braintrust** — experiment tracking, dataset-first approach, model-agnostic
- **LangSmith** — production traces, LangChain/LangGraph-native observability

The mistake is picking one platform for everything. The pattern is: DeepEval in CI, Braintrust for ablation experiments, LangSmith for production traces. — [BestAIWeb, Agent Evaluation Pipeline with LangSmith, Braintrust, DeepEval](https://www.bestaiweb.ai/how-to-build-an-agent-evaluation-pipeline-with-langsmith-braintrust-and-deepeval-in-2026/)

## Evidence

- **Blog — Braintrust:** "AI Agent Evaluation: A Practical Framework for Testing Multi-Step Agents" — establishes the two-layer reasoning/action architecture for agents, argues trajectory scoring is structurally required because errors in early steps corrupt everything after. — [URL](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Blog — Arthur.ai:** "How to Build Regression Test Datasets for AI Agents From Production Failures" — documents the production flywheel: every production failure is a test case you could not have invented; trace → test case → golden dataset → CI/CD gate. — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Blog — Big Data Boutique:** "LLM Evaluation in Production: Frameworks, Metrics, and the Layered System That Ships" — argues the eval architecture question precedes the framework-selection question; maps the three-layer system (offline regression, online/shadow, human calibration) and why traditional ML metrics fail on every axis for LLM applications. — [URL](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **HN Show HN — Forge:** "Guardrails take an 8B model from 53% to 99% on agentic tasks" — documents ToolResolutionError as a new exception class distinguishing "found nothing" from "error," and meltdown detection via sliding-window context monitoring. — [URL](https://hacker-news.penportal.net/item/48192383)
- **Blog — PaperClipped.de:** "AI Agent Benchmarks Explained: SWE-bench, WebArena & AgentBench" — reports Berkeley contamination findings: SWE-bench Verified scores inflated 30+ points; SWE-bench Pro (1,865 multi-language tasks, cleaner sourcing) and SWE-bench Live (live GitHub issues) as more reliable alternatives. — [URL](https://www.paperclipped.de/en/blog/ai-agent-benchmarks-swe-bench-webarena)
- **Blog — Adaline Labs:** "How to Evaluate Coding Agents in Production" — documents the four specific metrics for coding agents in production: task completion rate, regression introduction rate, review loop count, blast radius on failure. — [URL](https://labs.adaline.ai/p/evaluate-coding-agents-production)

## Gotchas

- **Scoring only the final assistant message makes tool-call regressions invisible.** The output layer cannot see what happened in step 3. Score the full trajectory.
- **Defining pass thresholds after measuring current behavior** produces thresholds calibrated to broken behavior. Define thresholds and metric weights before the first run, then measure against them. — [BestAIWeb, Agent Evaluation Pipeline](https://www.bestaiweb.ai/how-to-build-an-agent-evaluation-pipeline-with-langsmith-braintrust-and-deepeval-in-2026/)
- **Trusting vendor benchmark leaderboards uncritically.** No live ELO-style leaderboard exists for agent eval platforms — rankings are editorial, not measured. Re-evaluate tools against your actual task set, not someone else's.
- **Running evals at only one lifecycle point.** Run evals at three points: pre-deploy (offline regression), post-deploy (shadow sampling), and ongoing (production monitoring). Each catches different failure modes.
- **Not distinguishing between a tool returning empty results versus a tool error.** Both look like a successful tool call to the agent. Without explicit signal, the LLM marks the step complete and continues with bad data.
