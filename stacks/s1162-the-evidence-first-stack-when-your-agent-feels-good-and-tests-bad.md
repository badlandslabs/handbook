# S-1162 · The Evidence-First Stack — When Your Agent Feels Good and Tests Bad

[You ran the agent. It looked right. You shipped it. Three weeks later, a customer screenshot surfaces a class of wrong answers your team never thought to test for. Your eval suite is full of unit-test-style checks on internal logic, but the agent's actual failure mode — confidently plausible胡说 — was never instrumented. The fix isn't a bigger prompt. It's evidence: a systematic eval layer that tells you, before you ship, whether the agent reliably does what it claims to do.]

## Forces

- **"Looks right" is not evidence.** A prompt tweak that passes a vibe check can clearly perform worse against the full eval suite. Multiple HN practitioners report a prompt change "felt" like an improvement but scored worse on actual task completion. — [HN: Principles for production AI agents, 128pts](https://news.ycombinator.com/item?id=44712315)
- **Agents fail silently in domain-specific ways.** "200 OK" responses can be subtly, fundamentally wrong. Financial agents misinterpreting stock tickers. Logistics agents shipping to the wrong address. No error logged; no crash reported. Only the customer notices. — [AgentReviews: AI Agent Failure Recovery, May 2026](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)
- **Agent output has no natural oracle.** Traditional software has expected outputs you can assert against. Agent output is natural language in, natural language / tool calls out. Defining "correct" requires judgment calls that live outside the code.
- **Eval quality matters more than eval quantity.** Teams starting their eval journey often build hundreds of broad evals. The mature pattern is fewer, behavior-specific evals tightly coupled to user-facing outcomes. — [aunhumano: On Evaluating Agents, Sep 2025](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)
- **Production traces are the highest-signal dataset.** The gap between "what we thought would go wrong" and "what actually goes wrong" is almost always large. Real production traces — clustered by failure similarity — reveal failure modes no pre-deployment test could anticipate.

## The Move

Build a three-layer eval system: define success criteria, instrument traces, and close the loop.

**1. Define end-to-end success criteria first, not internal checks.**
Start with a binary: did the agent meet the user's goal? This beats granular internal checks (did it call tool X? did it parse Y?) because it tracks what actually matters. Refine from there. — [aunhumano](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)

**2. Instrument step-level traces from day one.**
Capture every tool call, its arguments, its result, and the subsequent reasoning step. Without traces, debugging a production failure is guesswork. Agents without traces can't replay failure scenarios. — [Preporato: Error Handling in AI Agents, NCP-AAI, 2026](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

**3. Choose an observability stack matched to your team's constraints.**

| Tool | License | Hosting | Best for |
|---|---|---|---|
| Langfuse | Open-source | Both | Framework-agnostic OTel tracing with full data ownership |
| Arize Phoenix | Elastic License 2.0 | Both | ML-grade eval primitives, OTel-native, no event caps |
| Comet Opik | Apache 2.0 | Both | ClickHouse-backed high-volume traces, open-source |
| Braintrust | Proprietary | Managed | Eval-first workflow: datasets, prompt iteration, scoring |
| DeepEval | Open-source (LGPL) | Both | Pytest-style LLM evals as regression tests in CI |
| LangSmith | Proprietary | Both | Native LangChain/LangGraph integration with replay |

— [Codeables: Best LLM observability tools, Apr 2026](https://codeables.dev/article/best-llm-observability-tools-for-production-agents-langfuse-arize)

**4. Use cost-per-task as a first-class metric.**
Every eval run costs money and latency. Track cost alongside accuracy. An agent that achieves 94% accuracy at 3x the cost of a 91% version may not be the right production choice. — [HN: Evaluating Agents discussion](https://news.ycombinator.com/item?id=45121547)

**5. Feed failure traces into the eval loop.**
Cluster production failures by trajectory similarity. High rates of redundant tool calls indicate scope problems. Frequent invalid tool arguments indicate tool descriptions need clarification or examples. Build evals specifically from these clusters. — [Preporato](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

**6. Sample human review for edge cases.**
No eval framework captures the full range of agent behavior. Pick a random sample of production traces for human annotation. Flag anything the reviewer would not have done. Use those flags to generate new evals. — [aunhumano](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)

## Evidence

- **HN thread (128pts):** A practitioner managing a coding agent eval suite reports starting with hundreds of evals but converging to fewer, behavior-specific ones tied to actual user outcomes. A prompt tweak that "passed a vibe check" scored clearly worse on the full eval suite. — [HN: Principles for production AI agents](https://news.ycombinator.com/item?id=44712315)
- **HN thread (42pts):** Multiple practitioners confirm end-to-end success rate (yes/no: did the agent meet the goal?) as the most actionable starting metric. Manual trace inspection remains irreplaceable — "no amount of evals will replace the need to look at the data." Feed failure traces into DSPy to optimize failing tools and prompts. — [HN: Evaluating Agents](https://news.ycombinator.com/item?id=45121547) + [aunhumano: On Evaluating Agents](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)
- **Enterprise guide:** Pre-production evaluation teams reduce incident rates, control costs, and accelerate iteration cycles. The key insight: trace data from a single production deployment is worth more than any synthetic benchmark. Online evals (runtime scoring) and offline evals (regression testing against traces) complement each other. — [Maxim.ai: How to Evaluate AI Agents Before Production, 2025](https://www.getmaxim.ai/articles/how-to-evaluate-ai-agents-before-production-a-practical-end-to-end-framework)

## Gotchas

- **Vibe-checking instead of evaluating.** "The agent looks good" is not an eval. Run the suite. If you don't have an eval suite, the first one is binary: did it solve the user's task? Everything else follows.
- **LLM-as-judge lacks empirical grounding.** Multiple practitioners note that using an LLM to critique agent outputs has not been shown to correlate with actual task performance. Prefer deterministic checks or human-in-the-loop validation for critical paths. — [HN: Principles for production AI agents](https://news.ycombinator.com/item?id=44712315)
- **Eval suites drift from production behavior.** An eval suite built from synthetic test cases will miss the distribution of real user queries. Continuously mine production traces for new failure cases and add them to the suite.
- **No observability before shipping.** Adding tracing post-incident means you've been flying blind. Instrument traces before the first production deployment. Without them, you can't replay failures or measure regression.
- **Treating eval as a one-time gate.** Eval is a continuous loop: instrument → observe → evaluate → improve → re-instrument. The moment you stop running evals against new changes, regressions accumulate silently.
