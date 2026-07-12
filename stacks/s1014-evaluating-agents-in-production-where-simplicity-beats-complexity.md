# S-1014 · Evaluating Agents in Production: Where Simplicity Beats Complexity

You have an agent that works in demos. You shipped it. Three weeks later, a prompt tweak you made on a Tuesday broke something in a way nobody caught until a user complained — and you still can't reproduce it cleanly.

## Forces

- **Trajectory vs. single-turn** — evaluating one prompt-response pair is meaningless for agents. The failure mode is a chain of wrong tool calls across a 12-step run, where every individual step looks fine.
- **Probabilistic vs. deterministic** — a test that passes 8 out of 10 runs is not a passing test. But most teams treat agent evaluation like unit testing and wonder why regression still ships.
- **Coverage vs. cost** — comprehensive golden datasets are ideal but expensive to build. Teams under-invest in offline eval and over-rely on user complaints as their test suite.
- **LLM-as-judge instability** — it's the most scalable scoring method, but it's also susceptible to position bias, self-preference, and "metric green, user red" failures. Calibrating it is non-obvious.
- **Offensive vs. defensive eval** — most teams only test "does it work?" They skip "can it be made to do something unintended?" Security testing for agents is its own discipline.

## The move

Evaluate agents on two levels: end-to-end task completion and per-component correctness. Then gate deployments with CI, not vibes.

**Offline (pre-deploy):**
- Build a **golden dataset** of 20-50 real agent trajectories from production logs. Each entry includes the input, the full trace, and the human-assessed outcome (pass/fail/partial). This is your regression suite.
- Use **LLM-as-judge** (G-Eval or similar) to score outputs against a rubric — but **calibrate it** against human labels on a sample of 10-15 traces first. Measure inter-rater reliability (Cohen's kappa or similar). If the judge diverges from humans, tune the rubric or switch to a stronger model for judging.
- Run **component-level checks**: did the agent call the right tools? With the right arguments? Did tool-call sequences match the expected pattern? These catch failures that look fine at the outcome level.
- Gate CI with **pass/fail thresholds**, not advisory scores. A flaky eval (passes 8/10 runs) means the threshold is wrong, not that the agent is borderline. Run eval suites 3+ times for reliability-sensitive cases.

**Online (post-deploy):**
- Capture **full traces** for every production run — not just the final output. Include tool calls, arguments, intermediate steps, latency, token cost, and step count.
- Track **operating envelopes** alongside quality: cost per run, latency per step, step budget consumed. A run that "succeeds" but burns 5x the expected tokens is a failure mode.
- Run **sampled human review** on a rotating 2-5% of traces. Use human labels to recalibrate LLM-as-judge on a monthly cadence.
- Implement **red-teaming** for safety: inject adversarial prompts and malicious data to test whether the agent can be hijacked. Per NIST, testing attacks across multiple attempts (25x) reveals realistic success rates that single-attempt tests miss.

**The eval stack that actually ships:**
- DeepEval (pytest-native, 15k+ stars, 50+ metrics) for offline unit-style evaluation with CI integration.
- LangSmith, Phoenix, or Confident AI for trace capture and online monitoring.
- AWS agent-evaluation framework (369 stars) if you need managed evaluators for Bedrock/Q Business targets.
- Golden datasets from production logs, updated quarterly.

## Evidence

- **HN Discussion (roadside_picnic, June 2025):** "Evals are vital for improving performance. Over, and over again my experience building production AI tools/systems has been that evaluations are vital for improving performance. Without evals, you really don't know if you're moving the needle at all." — [Hacker News, "Principles for production AI agents" thread, 128 points](https://news.ycombinator.com/item?id=44712315)
- **Mastra.ai / LangChain 2026 State of AI Agents report:** Only 52.4% of teams run offline evaluations on test sets, and just 37.3% run online evals — meaning nearly half of production agents ship without systematic quality gates. An agent with 75% per-trial reliability has only a 42% chance of passing all three trials under pass³. — [Mastra.ai, "AI Agent Evaluation: Build Production-Grade Agents"](https://mastra.ai/articles/ai-agent-evaluation)
- **NIST CAISI (Jan 2025):** Tested agent hijacking attacks across 25 attempts rather than single attempts. Multi-attempt testing revealed significantly higher realistic success rates than single-attempt benchmarks. >50% of malicious prompt injection attempts succeeded across all configurations tested. — [NIST Technical Blog: Strengthening AI Agent Hijacking Evaluations](https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations)
- **HN Discussion (colonCapitalDee, June 2025):** "The problem isn't that LLMs can't be critical, it's that LLMs don't have taste. It's easy to get an LLM to give praise, and it's easy to get an LLM to give criticism, but getting an LLM to praise good things and criticize bad things is currently impossible for non-trivial inputs." — [Hacker News, same thread](https://news.ycombinator.com/item?id=44712315)
- **arXiv (Xia et al., 2024):** Evaluation-driven development (EDD) for LLM agents requires both offline controlled evaluations and online operational monitoring. Offline evals establish baselines; online evals catch real-world degradation. The dual-mode approach mirrors how Cognition AI and similar shops iterate — eval outcomes feed back into architectural redesign. — [arXiv:2411.13768v2](https://arxiv.org/html/2411.13768v2)
- **Thinking Inc (March 2026):** Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps. — [Thinking Inc, "Testing and Evaluating AI Agents in Production"](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)

## Gotchas

- **Golden datasets go stale.** Build from production traces, not synthetic examples, and rotate/update them quarterly. A golden set from 6 months ago doesn't reflect the distribution your agent actually sees.
- **LLM-as-judge has known biases.** Position bias (preferring first or last options), self-preference (favoring outputs from the same model family), and verbosity bias (preferring longer outputs). Calibrate against human labels before trusting any score threshold as a gate.
- **"Task complete" ≠ "task done correctly."** An agent can reach the right final answer via the wrong tool-call chain. Evaluate trajectories, not just outcomes. A wrong path that happens to land on a right answer will break on the next similar case.
- **Flaky evals are worse than no evals.** A test that passes 8/10 times trains your team to re-run until it passes. Fix the root cause — usually a threshold set too close to the natural variance of the metric.
- **Security evals are not optional for agents with tool access.** Any agent that can call external APIs, read files, or execute code is a potential hijacking surface. If you skip red-teaming, you're shipping blind.
