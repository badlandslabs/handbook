# S-2283 · The Eval Illusion Stack — When Your Benchmark Passes but Your Agent Still Fails in Production

Your agent scored 87% on the benchmark. You shipped it. It failed. Not because it couldn't complete tasks — it completed plenty — but because it completed them by the wrong path, wasted budget doing it, or silently returned wrong answers with high confidence. Your benchmark was never measuring the right thing. This is the Eval Illusion: high scores on contaminated or misaligned benchmarks that give false confidence about production readiness.

## Forces

- **Benchmarks measure capability, not reliability.** A model that can solve a task 70% of the time under demo conditions fails catastrophically in production where conditions are noisier and stakes are higher.
- **Agents fail silently — not with errors.** They return HTTP 200, produce fluent output, and confidently hallucinate tool parameters, wrong reasoning chains, or plausible nonsense. Traditional error tracking catches none of this.
- **Trajectory matters as much as outcome.** An agent that reaches the right answer via wrong reasoning is more dangerous than one that gives a wrong answer — the broken reasoning will surface again under shifted conditions.
- **Eval-data contamination is endemic.** UC Berkeley researchers found all eight prominent AI agent benchmarks could be gamed with trivial exploits. A single character change gamed 890 SWE-bench tasks. SWE-bench Verified itself was found to have training data leakage — OpenAI stopped reporting scores in early 2026.
- **Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation and monitoring**, not model capability gaps.

## The move

The core shift: **from static benchmark scores to continuous, trajectory-aware production eval loops.** Three interlocking layers:

- **Eval not benchmark.** A benchmark is a fixed public test (MMLU, SWE-bench) that measures a model's general capability. An eval is a structured test specific to your agent's task, data, prompts, tools, and retrieval. Benchmarks tell you if a model is capable. Evals tell you if your agent does its job. [LangChain, "LLM Evals: The Feedback Loop Behind Reliable AI Agents," March 2026](https://www.langchain.com/resources/llm-evals)

- **Score trajectories, not just outputs.** Evaluate the full sequence of reasoning, tool calls, and intermediate states — not just whether the final answer is right. Agents that reach correct answers via broken reasoning chains are ticking time bombs. Golden-case suites with known-good trajectories catch reasoning drift before it hits production. [Zylos Research, "AI Agent Evaluation and Benchmarking," May 2026](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)

- **Close the production-to-eval feedback loop.** Every production failure becomes a new eval case. Failed agent runs are logged, triaged, and added to the eval suite. LangChain calls this "a score is only useful when it changes what ships — by becoming a dataset example, an online monitor, or a context fix." [LangChain, op. cit.](https://www.langchain.com/resources/llm-evals) This transforms evaluation from a pre-launch gate into a continuous improvement engine.

- **Classify failures before retrying.** Agent errors fall into four categories, each demanding a different recovery strategy: **transient** (rate limits, timeouts — retry with backoff), **semantic** (malformed JSON, hallucinated tool params — re-prompt with corrective context), **resource** (token overflow, budget exceeded — reduce payload or switch model), and **fatal** (auth failures, policy violations — abort immediately). Retry logic that doesn't distinguish between these wastes tokens and risks cascading failures. [Neel Mishra, "Agent Error Handling: Retries and Fallbacks," MLOps Series 2026](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

- **Instrument for failure modes you can't anticipate.** At Asynq.ai, a candidate evaluation agent hallucinated tool parameters and got stuck in loops producing evaluations that contradicted its own reasoning. At Modelia.ai, an image generation agent approved obviously flawed outputs while optimizing for completing the workflow rather than quality. [Harsh Rastogi, "Agentic AI in Production: Error Recovery, Observability, and Scaling Patterns," March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns) These are not detectable from logs alone — they require trajectory traces and output quality checks.

- **Implement circuit breakers, not just retries.** For repeated tool call failures, a circuit breaker trips after N failures in a window, stops hammering the failing endpoint, and switches to a fallback (different tool, different model, human escalation). [Preporato, "Error Handling in AI Agents: Circuit Breakers, Retry & Recovery," NCP-AAI Guide, 2026](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

- **Human-in-the-loop escalation for high-stakes decisions.** Design agents to know when they're out of their depth. Financial transactions above thresholds, support tickets the agent can't classify with confidence, and compliance-critical operations should escalate to a human — not as a fallback for failures, but as a deliberate architectural boundary. [AgentReviews, "Practical AI Agent Failure Recovery Methods for Production Systems," May 2026](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)

## Evidence

- **Research paper:** UC Berkeley researchers found all eight prominent AI agent benchmarks could be gamed to near-perfect scores without solving real underlying tasks. One team gamed 890 SWE-bench tasks with a single character change. Several systems hit 100% on multiple benchmarks while solving zero real problems. — [Zylos Research, "AI Agent Evaluation and Benchmarking"](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)

- **Primary source — practitioner incident:** At Asynq.ai and Modelia.ai, production agents hallucinated tool parameters, got stuck in loops, contradicted their own reasoning, and optimized for workflow completion rather than quality. Fixed with trajectory tracing, output quality checks, and circuit breakers. — [Harsh Rastogi, AI Product Engineer, March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Industry analyst:** IDC research: for every 33 AI agent pilots launched, only 4 reach production. Gartner: 40% of enterprise AI failures by 2028 will trace to inadequate evaluation and monitoring, not model capability gaps. — [Data-Gate, "AI Agent Evaluation and Testing in 2026: A Production Guide"](https://data-gate.ch/ai-agent-evaluation-testing-2026/)

## Gotchas

- **A passing benchmark means your model is capable, not that your agent is correct.** Your eval suite must test the full agent — its prompts, tools, retrieval, and orchestration — not just the base model's capability.
- **Hallucinated tool parameters won't show up in error logs.** The call will succeed technically (valid JSON, correct HTTP status) but use wrong IDs, dates, or enum values. You need output schema validation and canary checks against live data.
- **Golden-case suites go stale.** If you only test on yesterday's failures, you won't catch regression in the reasoning paths that worked yesterday but break on tomorrow's edge case. Rotate cases and inject adversarial inputs.
