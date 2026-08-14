# S-2623 · The Agent Evaluation Surface Stack — When a Green Dashboard Hides Corrupted Records

Your agent's quality dashboards are green. Latency is normal. Error rates are within threshold. You have no idea that the customer-service agent has been silently selecting the wrong API tool for the past three hours — passing plausible-looking parameters that pass every check, generating confident responses, and closing tickets while corrupting account records downstream. Standard observability was never looking at the right layer.

## Forces

- **Agents fail silently in the layer that matters most.** A regular API returns an error; an agent returning a plausible wrong answer looks identical to a correct one in logs. By the time you notice, dozens of records are wrong.
- **Traditional LLM evaluation is the wrong shape.** Accuracy on a multiple-choice test tells you nothing about whether your agent picks the right tool, manages state correctly, or stops when done. The MAST study (Berkeley/Stanford, 2025) analyzed 1,642 real-world agent execution traces across seven frameworks and found failure rates ranging from 41% to 86.7%.
- **Cost compounds before you can react.** Gartner pegs the token multiplier at 5–30x; production benchmarks show 70x. A single runaway loop burned $47,000 over 11 days (LangChain, Nov 2025) and $16,000–$50,000 in 5 hours (Claude Code recursion, Jul 2025). Neither triggered a crash or error — they looked like valid work the entire time.
- **Tool responses dominate the token budget.** Agent trace spans average 50KB each (vs ~900 bytes for standard LLM calls). Tool responses account for 67.6% of all tokens in an agent trace. System prompts account for just 3.4%. Teams spend hours refining prompts when the real failure surface is tool interactions.

## The Move

Evaluate agents across four dimensions, not one. The evaluation harness around your model often matters more than the model itself.

### Dimension 1 — Tool Selection Accuracy

Evaluate whether the agent called the right tool, not just whether the tool call succeeded. Instrument tool selection decisions into your trace. A tool can return valid output for the wrong operation. Catch this in the eval layer before it reaches production.

### Dimension 2 — Multi-Step Reasoning Coherence

Assess whether the agent's reasoning chain is sound across steps, not just whether the final answer looks right. Use trace-level analysis: did the agent correctly update its belief based on tool results? Did it detect and recover from mid-loop contradictions? This is where 41–86% of failures live.

### Dimension 3 — Task Completion Rate (Grounded)

Measure task completion against a curated set of real-world scenarios with known correct outcomes. Start offline with 50–100 hand-verified task trajectories. As production patterns emerge, graduate to online evaluation on live traces. Amazon's framework recommends continuous evaluation: compare agent outputs against ground truth on recurring task types.

### Dimension 4 — Operational Metrics (Cost + Latency per Turn)

Track cost per task completion, not just aggregate spend. A task that costs $0.02 in one configuration might cost $1.20 in another — the 60x difference comes from iteration count and context growth, not model price. Alert on per-task cost spikes. LangSmith's trace analysis surfaces these ratios; Braintrust's Eval product is purpose-built for this.

### The LLM-as-Judge Pattern (Used Carefully)

LLM-as-judge — using a stronger model to score agent outputs — works for preference alignment but carries known biases: position bias (preferring the first answer), self-preference bias (favoring responses similar to the judge's own style), and length bias (preferring longer outputs). Calibrate against human judgment on a sample set first. AWS recommends using LLM-as-judge as a signal layer above grounded metrics, not as the primary evaluation signal.

### The Monitoring Layer

Instrument traces with structured events: tool call inputs, tool call outputs, state transitions, token counts per turn, and reasoning summaries. Emit these to your observability platform. LangSmith (tracing and evaluation tight integration), Braintrust (evaluation-first), and Langfuse (self-hostable, open-source) are the three dominant platforms in production use as of mid-2026. LangSmith leads on trace depth; Langfuse is preferred for data sovereignty and self-hosting requirements.

## Evidence

- **Amazon Engineering Blog (Feb 2026):** Documents a production failure where a service agent silently selected the wrong API tool across thousands of requests. Standard dashboards showed green on latency and error rates throughout. By morning, hundreds of customer account records were corrupted. Root cause: evaluation was measuring tool-call success rate, not tool-call correctness. — [AWS AI Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **MAST Study, Berkeley/Stanford (arXiv:2503.13657, March 2025):** Analyzed 1,642 agent execution traces across seven multi-agent frameworks. Found real-world task failure rates of 41–86.7%. Identified five failure modes: step repetition, tool misuse, useless action, late recognition, and hallucination. — [arXiv](https://arxiv.org/abs/2503.13657)
- **freeCodeCamp / Production-Safe Agent Loop (June 2026):** Documented $47K LangChain loop (11 days, Nov 2025) and $16–50K Claude Code recursion (5 hours, Jul 2025). Both loops executed valid-appearing steps continuously because no layer was evaluating whether the agent was making progress. — [freeCodeCamp](https://www.freecodecamp.org/news/how-to-build-a-production-safe-agent-loop-from-exit-conditions-to-audit-trails/)
- **r/sre Synthesis Post (3 months ago):** Cross-references Datadog's State of AI Engineering 2026, SoftwareSeni's production failure report, and the MAST study. Notes that 40% of agentic projects will be scrapped by 2027 due to economic failure — most preventable with proper evaluation infrastructure. — [Reddit r/sre](https://www.reddit.com/r/sre/comments/1t43agb/learnings_from_3_reports_on_agentic_ai_in/)

## Gotchas

- **LLM benchmarks ≠ agent quality.** A model scoring 95% on MMLU can still select the wrong tool 30% of the time in a real workflow. Evaluation must match the shape of actual use.
- **Aggregate metrics hide localized failures.** Your dashboard can show 99.5% success rate while a specific tool combination fails 60% of the time on 2% of requests — enough to corrupt hundreds of records overnight.
- **Evaluation drift.** As your agent changes, your eval set must evolve. Teams that build evals once and never update find that their scores improve while production quality degrades. Re-calibrate against human judgment quarterly.
- **Changing the harness matters more than changing the model.** Multiple documented cases show that reworking the tool-calling harness, context management, or evaluation triggers produced more improvement than swapping the underlying model.
