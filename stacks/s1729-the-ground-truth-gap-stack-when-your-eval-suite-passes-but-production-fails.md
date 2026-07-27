# S-1729 · The Ground Truth Gap Stack — When Your Eval Suite Passes but Production Fails

Your benchmark says 92%. Your users are leaving. The gap is real: static eval suites measure your agent on examples you already knew the answer to, while production serves inputs nobody predicted. The result is a false confidence that costs more than no evals at all.

You reach for this when your golden dataset hasn't changed in months, when you trust a benchmark score without knowing what it actually measures, when you're comparing model versions but only have one eval set, or when "we run tests" means running the same test cases you wrote on day one.

## Forces

- **The benchmark crisis** — UC Berkeley researchers found all 8 major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) exploitable by 2025. SWE-bench Verified specifically suffers from training data contamination: Claude Opus 4.5 scores 80.9% on Verified but only 45.9% on the cleaner SWE-bench Pro. GPT-5.2 drops from 80% to ~23%.
- **Static datasets rot** — Golden datasets capture what you knew was hard when you wrote them. Production inputs drift, users invent new intents, and edge cases you never imagined arrive daily. A test set that isn't growing is a test set that's losing coverage.
- **Task completion ≠ task correctness** — An agent can call every tool, return every step, and still produce wrong output. Most automated metrics measure completion rate or trace-level success. They don't measure whether the output is actually right.
- **LLM-as-judge has a loyalty problem** — Models consistently rate outputs from the same model family higher. Without human calibration, automated judge scores are systematically optimistic.

## The move

Build a two-layer eval architecture: offline evals against curated golden datasets as the PR gate, paired with continuous online evals sampling live production traces. Treat the golden set as a floor, not a ceiling.

**Offline eval setup:**
- Curate test cases from production traces — especially from failures. Every on-call incident is a potential new test case.
- Use both deterministic scorers (exact match, regex, code execution) for measurable properties and LLM-as-judge for subjective qualities — but validate the judge itself against human ratings before trusting it.
- Run evals at every meaningful change: prompt revision, model swap, retrieval logic change, tool schema update.
- Pin the dataset version and model version independently. When scores change, you need to know which variable caused it.

**Online eval / production monitoring:**
- Sample a percentage of live traces and run lightweight quality checks against them — no ground truth needed.
- Flag traces where confidence is low, latency spikes, tool calls fail, or the user escalates. Route uncertain cases to human reviewers for annotation.
- Use human annotations to improve evaluator prompts and periodically re-validate automated scorers against human agreement rates.

**The feedback loop:**
- Failing production traces get promoted into the golden dataset. This is the most valuable source of new test cases: real failures that your eval suite didn't catch.
- Run experiments: pin the dataset, run one experiment per prompt/model variant, compare score deltas against a designated baseline. Score drops trigger investigation, not deployment.
- Track coverage over time — what percentage of your production input distribution does your golden set represent? As this decays, false confidence grows.

**Multi-dimensional scoring:**
- Don't report a single accuracy number. Track task completion rate, output correctness, cost per task, latency, and safety/violation rate as separate dimensions.
- An agent can improve on one dimension while degrading on another. Single-number scores hide this.

## Evidence

- **Amazon engineering blog (Feb 2026):** Thousands of agents built across Amazon organizations required a fundamental shift from static benchmark evaluation to a holistic multi-dimensional framework covering agent behavior, capabilities, reliability, and safety across both offline curated datasets and online production traffic. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Notion AI case study (2025):** Notion's AI team of 70 engineers went from 3 issues resolved per day to 30 after adopting systematic evaluation with automated scoring against production traces. Their finding: eval engineering is not overhead — it *accelerates* shipping by replacing guesswork with measurable feedback per change. — [Braintrust Customers](https://www.braintrust.dev/customers/notion)
- **UC Berkeley / Paperclipped analysis (2026):** All 8 major agent benchmarks are exploitable. SWE-bench Verified contamination gap: 35 percentage points for Claude Opus 4.5 (80.9% → 45.9% on Pro). OpenAI stopped reporting Verified scores after finding evidence of frontier model training on Verified solutions. — [Paperclipped](https://www.paperclipped.de/en/blog/ai-agent-benchmarks-swe-bench-webarena)
- **Langfuse engineering guide (2025):** Golden datasets must be living artifacts — schema validation, deduplication, item versioning, and continuous promotion from production failures. A frozen dataset's coverage decays proportionally with time since last update. — [Langfuse](https://langfuse.com/resources/engineering/golden-dataset-evaluation)
- **Galileo Labs research (2026):** Teams that relied solely on static golden datasets shipped to production with confidence and were paged within weeks by edge cases absent from their test sets. The recommended pattern: sample live traffic, route uncertain traces to SMEs for annotation, use annotations to improve automated evaluators. — [Galileo AI](https://galileo.ai/blog/beyond-golden-datasets-static-evals-failures)

## Gotchas

- **Benchmark scores ≠ production performance.** The contamination problem means published leaderboard scores measure training data overlap more than genuine capability. Use benchmarks to compare architectures, not to predict real-world deployment reliability.
- **Golden sets need maintenance, not just creation.** The hard part isn't building an initial test set — it's keeping it representative as production evolves. Budget engineering time for it, or it will silently decay.
- **LLM-as-judge needs its own eval.** Before trusting automated judge scores, validate them against human agreement on a sample. A judge that rates itself generously will give you false pass rates.
- **Sampling production traces without annotation creates noise, not signal.** Online evals that flag issues but never route to human review create alert fatigue with no improvement loop. The annotation step is where the data flywheel starts.
