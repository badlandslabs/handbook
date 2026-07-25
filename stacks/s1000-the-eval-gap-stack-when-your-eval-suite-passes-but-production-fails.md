# S-1000 · The Eval Gap Stack — When Your Eval Suite Passes But Production Fails

Your eval suite is green. Pass rate: 82%. You ship. Two weeks later, the agent is failing on inputs that look nothing like anything in your test set — real user data, edge cases you never imagined, the actual distribution your deployment exposes. The eval wasn't lying; it was measuring the wrong thing. This is the eval gap: the structural mismatch between what your suite validates and what production demands.

## Forces

- **Eval suites cover history, not distribution.** Golden datasets are built from past failures. Production throws genuinely novel inputs. The suite tells you the agent doesn't repeat known mistakes; it says nothing about unknown ones.
- **Single-run pass rate is a lie.** Agents achieving 60% success on a single run drop to ~25% across eight runs of the same task. Single-run evals overestimate reliability by a factor of 2–3×.
- **Benchmarks don't transfer.** Standard benchmarks (SWE-bench, MMLU, GAIA) are trained on different distributions than your deployment. AWS research found a 37% performance gap from lab to production.
- **Agents are non-deterministic.** The same input can trigger different tool selections and reasoning paths. Traditional software testing assumes determinism; agents break that assumption at every level.
- **Outcome metrics hide trajectory failures.** An agent can reach the right answer via a degraded path — one that will fail on harder inputs of the same class.

## The move

Build a layered eval system that closes the gap between what you test and what production reveals.

### Layer 1 — Offline regression from real failures (golden datasets)

Use actual production failures as test cases, not synthetic benchmarks. Every production failure is a test case you didn't have to invent.

- Log every failure with input, expected output, actual output, and full trace
- Add each to a golden dataset (structured: input → expected → metadata)
- Run the full dataset on every prompt change, model swap, retrieval tweak, or tool update
- Treat additions to the dataset as a first-class engineering discipline, not an afterthought

### Layer 2 — Multi-run consistency scoring

Never report pass rate from a single run. Run each test case at minimum 8 times and report the consistency rate.

- Run the same input 8 times; count successes → consistency score
- Borderline responses have the highest instability; these are the most valuable to catch
- A single eval run can be off by ±0.15 on pass rate
- Use variance as a signal: high-variance cases need prompt hardening, not just more evals

### Layer 3 — Trajectory-level diagnostics alongside outcome scoring

Measure both the path and the destination.

- **Outcome:** Did the task complete correctly?
- **Trajectory:** Was the reasoning path efficient? Were the right tools selected? Were there unnecessary retries or loops?
- Trace every tool call, reasoning step, and handoff — not just the final output
- A trajectory that degrades will eventually produce a bad outcome; catch it before the outcome fires

### Layer 4 — Three-tier scoring strategy

Use the right judge for the property being measured.

- **Deterministic checks** for exact-matchable properties: SQL output correctness, API response format, tool argument values. Most reliable, no LLM variance.
- **LLM-as-judge** for context-dependent quality: does the response address the user's intent? Is the tone appropriate? Is the explanation coherent.
- **Human spot-check** for edge cases, high-stakes outputs, and to calibrate the LLM judge periodically

### Layer 5 — Binary scoring, not scales

Make pass/fail your default. LLM judges are inconsistent on continuous scales.

- Assign each test case a binary pass/fail criterion upfront
- A continuous score range (1–10) pushes the judgment call back to a human on every borderline case — you lose the automation benefit and the consistency
- Binary scores also make trend tracking trivial: pass rate went from 78% → 81% is actionable; "average quality score went from 7.2 → 7.4" is not

## Evidence

- **GitHub Repo:** `MrTalecky/agent-evals` — "A minimal framework for improving LLM agent prompts using real production failures as test cases. Not synthetic benchmarks — actual mistakes your agent made, with known correct answers." — [github.com/MrTalecky/agent-evals](https://github.com/MrTalecky/agent-evals)
- **GitHub Repo:** `TribeAI/claude-evals` — Production eval framework with native SDK hooks into `PreToolUse`, `PostToolUse`, and `SubagentStop` lifecycle events, 50-case golden dataset for contract review. Implements Anthropic's published eval patterns. — [github.com/TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)
- **Research Report:** Galileo State of Eval Engineering — "Enterprise AI deployments show agents can achieve 60% success on single runs. That drops to 25% across eight runs. Elite teams (top 15%) achieve 2.2× better reliability than average teams." — [galileo.ai](https://galileo.ai/blog/ai-agent-evaluation)
- **HN Discussion:** Anthropic's "Building Effective AI Agents" post, June 2025 (543 points, 88 comments) — HN practitioners consensus: eval and observability matter more than orchestration framework choice. — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Industry Analysis:** AgentMarketCap, April 2026 — "88% of AI agent projects fail before reaching production, and benchmark scores are largely useless at predicting which 12% will survive." — [agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/10/building-production-agent-evals-llm-judge-deterministic-verifiers-human-review)
- **Framework Comparison:** BigDataBoutique — LangSmith best for LangChain/LangGraph-native teams; Braintrust best for framework-agnostic eval-first workflows; DeepEval for pytest-style CI integration. — [bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **Practitioner Guide:** InfoQ, March 2026 — "Agents are systems, not models — evaluate them accordingly. AI agents plan, call tools, maintain state, and adapt across multiple turns. Single-turn accuracy metrics don't capture how agents fail in practice." — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Single-run evals give false confidence.** Run each test case 8 times minimum before reporting a pass rate. A single run can be off by ±15 percentage points.
- **Eval coverage expands but stays retrospective.** Your dataset only covers failure types you've seen. Genuinely novel inputs will always slip through — accept this and build alerting that catches them fast in production.
- **LLM-as-judge is inconsistent on continuous scales.** Always use binary pass/fail unless the property genuinely requires graded judgment. Calibrate the judge with a small human-annotated sample before trusting it at scale.
- **Golden datasets go stale without ownership.** Someone has to own adding new failure cases. Without a dedicated process, the dataset atrophies and the eval gives increasingly stale signals.
- **Trajectory failures hide inside successful outcomes.** An agent that reaches the right answer via a bad reasoning path will fail on harder inputs in the same class. Always inspect the trajectory, not just the final score.
