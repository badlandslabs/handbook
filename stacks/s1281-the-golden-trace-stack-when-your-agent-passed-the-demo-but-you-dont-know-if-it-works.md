# S-1281 · The Golden Trace Stack — When Your Agent Passed the Demo But You Don't Know If It Works

The demo worked. The pilot was impressive. But the agent is now in production with no systematic way to know whether it's still working next week — after a model update, a prompt change, or a tool signature shift. The default is to ship on vibes and discover regressions when users complain.

## Forces

- **Agents are non-deterministic by nature** — even at `temperature=0`, providers occasionally return different tokens. This makes traditional pass/fail unit tests inapplicable. An agent test must assert that a non-deterministic policy calling non-deterministic tools produced a reasonable outcome across a distribution of inputs. (72Technologies, June 2026 — https://www.72technologies.com/blog/agent-evals-ci-regression-tests)
- **Output evaluation misses path correctness** — an agent can reach the right answer via the wrong tool call, skip a required approval gate, or loop 40 times burning budget. Standard output scoring passes all of these. Trajectory evaluation — checking the multi-step path — catches what output-only evals miss. (genai.qa, 2026 — https://genai.qa/ai-agent-trajectory-testing-2026/)
- **Production drift is silent** — LLM systems drift through corpus changes, model updates, prompt evolution, and query distribution shifts. Traditional monitoring (latency, Recall@K) does not catch generation failures. Retrieval metrics can look healthy while the LLM produces ungrounded responses. (Alok Ranjan Daftuar, June 2026 — https://aloknecessary.github.io/blogs/llm-evaluation-in-production)
- **Most teams have no eval pipeline at all** — of 1,837 engineering leaders surveyed, only 95 had AI agents live in production. Of those, most still struggled to understand when their agents were right, wrong, or uncertain. The AI stack shifts faster than organizations can validate it. (Cleanlab, 2025 — https://cleanlab.ai/ai-agents-in-production-2025)

## The Move

The production agent eval stack has four layers. Skip any one and you have a gap.

### Layer 1 — Capture the right data

The eval loop runs continuously: production traces → test cases → evals → deploy → production traces. Don't start with synthetic data. Mine real usage — production logs and support tickets are the best source of tasks that actually happen. Cover the hard and unusual cases on purpose. Treat the dataset as versioned, maintained data rather than a one-time snapshot. (LangChain/LangSmith docs — https://www.langchain.com/langsmith/evaluation)

**What makes a dataset golden:** Each entry is a task plus the expected outcome, reviewed carefully enough that you are willing to treat a failure against it as a real regression. Quality matters more than size. A hundred well-chosen cases beat ten thousand noisy ones. Mature agent teams curate **50–500 golden trajectories** covering common flows, edge cases, regulatory-critical scenarios, and adversarial inputs as their canonical correctness dataset. (genai.qa — https://genai.qa/ai-agent-trajectory-testing-2026/)

### Layer 2 — Score at two levels: trajectory AND output

**Trajectory scoring** evaluates the path: tool-call sequence, state transitions, approval gate adherence, loop detection, budget adherence, and error recovery behavior. Ask: *was the path correct?*

**Output scoring** evaluates the final answer: faithfulness (grounded in retrieved context), answer relevance, and factual correctness. Ask: *was the answer correct?*

A correct answer via the wrong tool call, or correct answer skipping an approval gate, or correct answer at 40x cost (looping) — all pass output eval but fail trajectory eval. (genai.qa — https://genai.qa/ai-agent-trajectory-testing-2026/)

### Layer 3 — Pick your scorer type per criterion

| Scorer Type | Use For | Example |
|---|---|---|
| **Code-based / deterministic** | Format validation, JSON schema, length, exact-match | `json_edit_distance`, regex on output |
| **LLM-as-Judge** | Nuanced qualities code can't capture | Helpfulness, tone, faithfulness, coherence |
| **Dynamic ground truth** | Live/changing data sources | Executable code stored as reference, runs at eval time |
| **Trajectory comparison** | Multi-step path correctness | Golden trace vs. candidate trace |

For LLM-as-Judge specifically: express complex criteria in a written rubric, use chain-of-thought scoring, and choose a judge model that may differ from your task model. **Always pin the judge model to a specific version** — never use aliases like `claude-sonnet-latest`. If Anthropic or OpenAI updates the judge model, your score baselines shift even if your system did not change. Treat model upgrades as a baseline reset event. (Alok Ranjan Daftuar — https://aloknecessary.github.io/blogs/llm-evaluation-in-production)

**Calibrate before gating:** Before trusting LLM-as-Judge scores as a regression gate, calibrate against human judgments on a sample of 50–100 examples. Measure inter-annotator agreement using Cohen's Kappa. A Kappa above 0.6 is acceptable for production use. Below 0.4 means the judge prompt needs revision. (Alok Ranjan Daftuar — https://aloknecessary.github.io/blogs/llm-evaluation-in-production)

### Layer 4 — Gate CI/CD on trajectory regressions

The 4-Gate Pattern: modern agent pipelines gate pull requests on syntax, factual grounding, safety, and trajectory logic. Enforce `temperature=0` and fixed seed variables to make scores deterministic and reproducible. A successful CI evaluation suite must execute in under 15 minutes to avoid developer bottlenecking. (AgentClash — https://www.agentclash.dev/ci-cd-agent-evaluation)

```
agentclash run create --follow
```

Wire eval into the merge gate: model changes, prompt changes, RAG changes, and tool changes all trigger a regression run against the golden trajectory set. Block the merge if the candidate score falls below baseline. (AgentClash — https://www.agentclash.dev/ci-cd-agent-evaluation)

## Evidence

- **GitHub repo / evaluation framework:** AWS Labs open-sourced `agent-evaluation` (Apache-2.0, 369 stars) — a framework for testing virtual agents with configurable evaluators and targets for Amazon Bedrock, Knowledge Bases, and Amazon Q Business. (https://github.com/awslabs/agent-evaluation)
- **GitHub repo / 12 eval techniques:** `FareedKhan-dev/ai-agents-eval-techniques` (MIT, 45 stars) — hands-on implementations of 12 evaluation techniques including LLM-as-Judge, trajectory evaluation, RAGAS, dynamic ground truth, and pairwise comparison, using LangChain and LangSmith. (https://github.com/FareedKhan-dev/ai-agents-eval-techniques)
- **HN / production principles:** HN thread on "Principles for production AI agents" (2025) — consensus that LLM-as-Judge is easy to express but requires validation against sample annotated data, either by trial-and-error, prompt optimization (DSPy), or learning a correction model on top (LLM-Rubric). (https://news.ycombinator.com/item?id=44712315)
- **HN / Claude skill for evals:** "Agent-evals — Claude skill to build your own evals" on HN (2026) — CLI-based approach to writing, running, and iterating on agent evaluation datasets as code. (https://news.ycombinator.com/item?id=48013746)
- **Blog / CI regression:** 72Technologies — "Evaluating Agents in CI: Building Regression Tests That Actually Work" (June 2026) — documents the five failure modes (hallucination, refusal, drift, format breaking, context confusion), why traditional tests miss them, and the golden-dataset-plus-CI-gate pattern that catches them. (https://www.72technologies.com/blog/agent-evals-ci-regression-tests)
- **Blog / production eval pipeline:** Alok Ranjan Daftuar — "LLM Evaluation in Production" (June 2026) — the two-layer eval stack (retrieval layer + generation layer), pinning judge models, calibrating LLM-as-Judge with Cohen's Kappa, and the silent-drift failure mode. (https://aloknecessary.github.io/blogs/llm-evaluation-in-production)
- **Blog / trajectory testing comparison:** genai.qa — "AI Agent Trajectory Testing 2026: LangSmith vs Braintrust vs Arize Phoenix vs Galileo" — maps the four credible eval platforms to deployment shapes: DeepEval (pytest-native OSS), Braintrust (SaaS eval primitive), LangSmith (LangChain-stack bundle), Patronus (UAE data-residency). (https://genai.qa/ai-agent-trajectory-testing-2026/)

## Gotchas

- **Don't use output eval alone.** Correct answer via wrong path is a regression that output scoring won't catch. Always layer trajectory scoring.
- **Don't use floating judge model aliases.** `claude-sonnet-latest` silently upgrades and your baseline shifts. Pin to a dated version and treat upgrades as intentional events with re-calibration.
- **Don't confuse coverage with quality in your golden dataset.** Ten thousand noisy production traces are worse than a hundred hand-reviewed trajectories. Curate deliberately, cover edge cases, version the dataset.
- **Don't skip the <15-minute CI budget.** Evals that take an hour to run get bypassed. If your trajectory set is too slow, split into a fast gate (core paths only) and a slow suite (edge cases, nightly).
- **Don't gate on a single metric.** A composite scorecard (correctness + cost + latency + safety + tool-call precision) gives you release decision data; a single number gives you a false sense of security.
