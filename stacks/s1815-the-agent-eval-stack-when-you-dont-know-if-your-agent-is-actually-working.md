# S-1815 · The Agent-Eval Stack — When You Don't Know if Your Agent Is Actually Working

Your agent answers correctly in the demo. Your hand-picked test cases pass. Then production users hit it with real inputs and something breaks — the wrong tool, a hallucinated intermediate step, a completion that looks right but isn't. The eval you didn't build is the gap between confidence and reality.

## Forces

- **Agents fail compoundly.** A k-step agent's end-to-end success rate is the product of its per-step success rates. At 95% per-step accuracy, an 8-step agent succeeds only ~66% of the time. At 20 steps, it's ~36%. Every individual step can score green while the session ends wrong — and standard unit tests miss this entirely.
- **Trajectories are not responses.** Evaluating an agent's final output tells you nothing about *how* it got there. The path matters: wrong tool selection early can produce a plausible wrong answer late, and output-only evals miss this.
- **Production inputs are unbounded.** Handwritten test suites cover happy paths. Real users surface distribution shifts, adversarial inputs, and edge cases no one anticipated. Pre-deployment eval cannot substitute for continuous production monitoring.
- **The field has no gold standard.** Approaches range from "vibes" to sophisticated CI/CD pipelines. Teams that do build evals often disagree on what to measure, how to score it, and whether LLMs can reliably judge other LLMs.

## The Move

Build a **trajectory-first evaluation system** with three layers: per-step diagnostics, trajectory-level scoring, and continuous production sampling.

**Per-step diagnostics — gate each decision point:**
- **Tool selection accuracy** — Did the agent pick the right tool, or none when it should have picked none? Wrong tool choice is the single highest-impact failure mode per Shopify Sidekick's engineering blog.
- **Tool argument correctness** — Were the arguments valid and within bounds? Shopify found that switching from relative to absolute file paths eliminated a recurring error class — structural correctness, not prompt refinement.
- **Retrieval quality** — Did the agent receive context relevant to the current step? Score RAG/doc retrieval precision at each injection point.

**Trajectory-level scoring — the truth unit:**
- Score the full step sequence (system prompt → user input → reasoning → each tool call + return value → final response → outcome) as a single unit.
- Use `TaskCompletion` (did the agent achieve the stated goal?), `TrajectoryScore` (was the path efficient and correct?), and `GoalProgress` (partial credit for multi-step tasks).
- Apply this to sampled production traces, not just test suites.

**The pass@k model — your reliability estimate is wrong without it:**
- `pass@k` — probability of at least one success in k trials — is the correct reliability metric, not single-trial pass rate.
- An agent with 75% single-trial reliability has only 42% chance of passing 3 consecutive trials (0.75³). Your "reliable" agent is actually failing intermittently and you don't know it.
- Run sufficient trials per test case to estimate `pass@k` before shipping.

**Grader selection — know the tradeoffs:**
- **Deterministic matching** — fast, reliable for code execution, JSON schema validation, string equality. Use where ground truth exists.
- **LLM-as-judge** — scalable for subjective quality, natural language outputs, trajectory coherence. But: "in our internal experiment we found that LLMs were not good critics" (HN commenter, citing personal research). Validate judge accuracy against human ground truth before trusting scores.
- **Human review** — gold standard for qualitative judgments, but does not scale. Reserve for sampling production traces and calibrating automated graders.

**Production sampling loop:**
- Route a percentage of live traces to an eval queue automatically.
- Break down failures by type: tool timeout, wrong selection, hallucinated tool, retrieval miss, LLM parse failure. Each failure type points to a different fix.
- The gap Shopify discovered: their agent was "completing" tasks at 95% but only 70% of those completions were actually correct. Without measuring completion vs. correctness separately, the 25-point gap was invisible.

## Evidence

- **Engineering blog:** Shopify Sidekick — An agent "can reason about tool responses and generate responses back to the merchant." They deliberately chose not to implement heavily defined workflows, finding well-defined tools with agentic loops better balanced quality and error recovery. Their eval framework evolved to gate tool selection accuracy and measure trajectory-level completion vs. correctness separately. — [shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **HN Ask HN thread (43 comments, 30 pts):** Practitioners describe the eval landscape as "very, very heterogeneous and fast moving... an afterthought for most teams." Most companies still evaluate by "vibes." The hardest problems are non-binary outputs (chatbots, coding agents) where "you can say 'hmm well that's a good response, but there is a better response.'" Benchmarking is expensive and existing public benchmarks are considered inadequate for domain-specific agents. — [news.ycombinator.com/item?id=47319587](https://news.ycombinator.com/item?id=47319587)
- **Primary source / guide:** FutureAGI's evaluation framework identifies six dimensions of agent quality: Tool Selection, Tool Argument, Retrieval Quality, Trajectory Coherence, Final Output Quality, and Task Completion. Emphasizes that "an agent is not a model" — evaluating one as if it were is the most common reason production agents fail. — [futureagi.com/blog/definitive-guide-ai-agent-evaluation-2026](https://futureagi.com/blog/definitive-guide-ai-agent-evaluation-2026)
- **Mastra.ai:** Pass@k vs single-trial pass rate is the critical distinction. "An agent with 75% per-trial reliability has only a 42% chance of passing all three trials under pass^3." CI gates based on single-trial metrics systematically overstate reliability. — [mastra.ai/articles/ai-agent-evaluation](https://mastra.ai/articles/ai-agent-evaluation)
- **AWS / Amazon:** Their holistic evaluation framework distinguishes LLM-driven applications (single-turn, prompt-response) from agentic AI systems (multi-turn, autonomous, tool-orchestrating). Agentic eval must evaluate system behavior — tool selection, reasoning chains, memory, task completion — not just final text output. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

## Gotchas

- **Output-only evals miss the compound error problem.** If you only score the final response, you cannot see where in the trajectory the agent went wrong. A plausible wrong answer can pass output eval while the path was completely wrong.
- **Single-trial pass rate overstates reliability.** Running each test once and calling it "passing" ignores the non-deterministic nature of LLM agents. Calculate pass@k with sufficient trials before any reliability claim.
- **LLM-as-judge accuracy is not guaranteed.** A judge LLM can be wrong in systematic ways — biased toward verbosity, unable to detect subtle errors, susceptible to position effects. Calibrate against human ground truth before trusting judge scores at scale.
- **Production distribution shift will break your eval suite.** Test cases written at development time cover a narrow slice of the input distribution. Continuous production sampling is not optional — it is the only mechanism that surfaces what your static test suite missed.
- **Completion rate and correctness rate are different metrics.** An agent can achieve high completion (it produced an answer) with low correctness (the answer was wrong). Tracking them separately, as Shopify did, reveals the hidden gap.
