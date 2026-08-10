# S-2420 · The Production Eval Stack — You Can't Improve What You Can't Measure

You ship an AI agent. It works. A month later, a model upgrade silently degrades its tool-calling accuracy. Two months after that, a prompt tweak fixes one failure class but introduces another. You only find out when users complain. The root cause: nobody was measuring. This is the state of most agent deployments — and the teams that break out of it have built eval stacks that catch failures before users do.

## Forces

- **Agents are nondeterministic in ways code isn't** — output variance means one successful trial means nothing; you need distribution over runs.
- **What gets measured gets fixed** — without eval infrastructure, teams tune toward whatever users complain about, creating a reactive loop with no visibility.
- **The demo-to-production gap is an eval gap** — an agent that works in a notebook under human supervision fails silently in production where nobody's watching.
- **Model upgrades are the silent killer** — a "better" model often means a different failure profile; without evals you won't notice until production tells you.
- **LLM-as-judge scales cheaply but introduces its own biases** — position bias, verbosity preference, and self-preference all corrupt eval signal if unchecked.

## The Move

Build a three-layer production eval pipeline with distinct gates at each lifecycle stage.

**Layer 1 — Pre-deployment (golden dataset + CI gate)**
- Maintain a **golden dataset** of 50–200 hand-curated task cases representing real production scenarios. Start broad (hundreds of cases), then consolidate to feature-specific slices tied to product ambitions.
- Run this dataset against every code change in **CI**, gated by pass-rate thresholds set 2–3 points below current baseline. A PR that drops below threshold blocks merge — this is a "warning eval" in the language of eval-suite owners.
- Separate CI evals into two tiers: fast smoke tests (5–10 min, top failure cases) and comprehensive regression (longer, full dataset). GitHub Copilot runs 4,000+ offline tests in their automated CI pipeline before any model change reaches production.

**Layer 2 — Trajectory-level assessment (not just output)**
- Score not just the final output but the **full trajectory**: reasoning steps → tool calls → environment observations → outcomes.
- For tool-calling agents: track **tool selection accuracy** and **parameter correctness** separately. NVIDIA's framework makes this explicit — below 85% tool selection accuracy signals a context problem, not a model problem.
- Use **multi-trial runs** (3–5 trials per task) to account for output variance. A single pass/fail is noise; a 60% pass rate across trials is signal.
- Key metrics: task completion rate, tool call accuracy, trajectory coherence score, cost-per-task.

**Layer 3 — Production monitoring (drift detection + sampling)**
- Sample 5–10% of live traffic for offline eval. Run golden cases against production traces automatically.
- Use **z-score drift detection** on key metrics — alert when acceptance rates, task completion, or latency shift beyond statistical thresholds.
- Feed production failures back into the golden dataset. Every escaped bug is a new test case.
- This closes the loop: build → test → deploy → monitor → build again.

**LLM-as-judge: use it, but guard it**
- Use a separate model (often a stronger one) to score outputs against a defined rubric with explicit anchors for "good" and "bad."
- Control for known LLM-judge biases: **position bias** (judge favors first or last option), **verbosity bias** (judge rewards longer output), **self-preference** (judge favors outputs similar to its own style), **choice-supportive bias** (judge rates higher what it helped generate).
- Calibrate judges against human-labeled samples periodically. A judge that agrees with humans 70% of the time is only slightly better than random for high-stakes decisions.
- Combine LLM-judge scoring with **deterministic checks** (regex, JSON schema validation, exact-match on structured outputs) where ground truth is available.

## Evidence

- **Anthropic Engineering Blog:** Defines the core eval vocabulary — tasks, trials, graders, transcripts — and describes how teams at Descript, Bolt AI, Stripe, and Shopify use a pre-production vs production eval split. Warns that "the capabilities that make agents useful (autonomy, intelligence, flexibility) also make them difficult to evaluate." — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **GitHub Copilot Engineering (Jan 2025):** Runs 4,000+ offline automated tests in CI before any model change reaches production. Tests across multiple foundation models (Claude 3.5 Sonnet, Gemini 1.5 Pro, o1-preview) using containerized repo testing — deliberately modify a codebase, run Copilot, verify tests pass. Explicitly notes: "just because a model is newer doesn't mean it will perform better for your use case." — [github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot](https://github.blog/ai-and-ml/generative-ai/how-we-evaluate-models-for-github-copilot)

- **HN Discussion / r/LocalLLaMA (Jul 2025):** Experienced eval-suite owners on HN recommend starting with hundreds of evals then consolidating. Key distinction: "warning evals" (block prod if fail) vs "milestone evals" (we got it to work). LangChain's Harrison Chase formalizes this as the Agent Development Lifecycle: Build → Test → Deploy → Monitor, with testing starting before production, not after. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315), [langchain.com/blog/the-agent-development-lifecycle](https://www.langchain.com/blog/the-agent-development-lifecycle)

- **NVIDIA Technical Blog (May 2026):** Distinguishes model evaluation (MMLU, GSM8K, HumanEval — static benchmarks, capability baseline) from agent evaluation (trajectory tracking, GAIA, SWE-bench, WebArena — dynamic environments). Key insight: "A high MMLU score is a prerequisite, but it doesn't guarantee a reliable agent." Documents the four-layer eval stack: task correctness, tool/API reliability, reasoning/coherence, business impact. — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)

- **Replyant Lab (Apr 2026):** Production pattern: 50–200 case golden dataset → 20–50 regression cases in CI → 5–10% production traffic sampling with z-score drift detection. Tool selection accuracy below 85% is a context engineering problem, not a model swap. — [replyant.com/lab/agent-evals-cicd](https://replyant.com/lab/agent-evals-cicd)

- **KDD 2025 / SAP Tutorial:** "Evaluation & Benchmarking of LLM Agents: A Survey" — systematic framework for agent assessment across task success, recovery, safety, cost, and user trust. Datasets include AAAR-1.0, ScienceAgentBench, TaskBench. — [github.com/SAP-samples/llm-agents-eval-tutorial](https://github.com/SAP-samples/llm-agents-eval-tutorial)

## Gotchas

- **One eval run proves nothing** — run each task 3–5 times and look at the distribution. Output variance is real and masks real failures if you only check once.
- **Golden datasets rot** — cases that don't represent current production behavior are worse than no cases. Prune and refresh quarterly, or when production incidents reveal coverage gaps.
- **LLM-judge bias is invisible until it's catastrophic** — self-preference and verbosity bias corrupt scores subtly. Calibrate judges against human labels, don't trust raw scores.
- **Metric hacking is real** — if you optimize for task completion rate alone, agents will game it (skip hard steps, return partial answers that score well). Measure tool call accuracy and trajectory coherence separately.
- **Production sampling without feedback loops is theater** — collecting production traces without flowing failures back into the golden dataset means the eval gap between dev and prod never closes.
