# S2182 · The Eval Blind Spot Stack

When your agent's eval suite is green but users are filing bugs — and you can't explain the gap.

## Forces

- Public benchmarks (MMLU, HumanEval, GSM8K) measure base model capability in isolation, not your agent's actual workflow with retrieval, tools, and user context layered on top. A model that tops every leaderboard can still fail the task your agent was built for.
- Golden datasets are correct by construction but stale by definition — the moment you build one, production traffic diverges from it. A super-majority of YC agent builders report evals under-deliver because keeping them current is nearly impossible.
- Agents produce multi-step trajectories. Evaluating only the final text answer misses the most dangerous failure modes: wrong tool called, correct tool with wrong arguments, or a loop that never terminates.
- Every major eval framework runs offline batch tests. None of the seven leading frameworks (DeepEval, Braintrust, LangSmith, Arize Phoenix, Galileo, OpenAI Evals, RAGAS) evaluate individual turns live in production — creating a structural gap between "eval passes" and "production works."

## The move

Build a four-layer evaluation system: trajectory + tool call + task completion + multi-turn. Run offline on pinned golden datasets before every deploy. Run online on sampled production traces continuously. Use deterministic checks where ground truth exists; use LLM-as-judge where it doesn't.

### Trajectory evaluation
- Inspect the full execution trace, not just the final output. Ask: did the agent take a reasonable path to the answer?
- Score each reasoning step independently — a good final answer from a broken trajectory will break on the next input.
- LLM-as-judge works here but requires calibration. Human annotators on a sample of traces establish the baseline; use that to validate judge quality before scaling.

### Tool call evaluation
- Check two things separately: correct tool selected, correct arguments passed.
- A malformed API call is a different failure mode than a wrong tool. These need separate assertions.
- Log every tool call with its arguments as structured data — this is the minimum surface needed to write deterministic checks.

### Task completion evaluation
- Define pass/fail criteria upfront. Where ground truth exists (structured output, database state, API response), use deterministic equality checks.
- Where ground truth doesn't exist, LLM-as-judge with explicit rubrics scores correctness, relevance, and safety.
- Run multiple trials per task — agents are stochastic. A single pass/fail on a critical path misleads more than it informs.

### Production sampling
- Sample a representative slice of live traffic for offline eval. 1-5% is enough to catch distribution shifts.
- Run the sampled traces against current and candidate versions; compare score distributions, not just averages.
- Feed failures back into the golden dataset. Every production incident is a new test case — curate it, review it, add it.

### Version everything in the eval pipeline
- Pin the dataset version, the model version, the prompt version, and the eval logic version together.
- Every experiment compares against a baseline run under identical conditions. Score deltas then mean something.
- Store all eval results with full metadata in a queryable store — historical analysis is how you catch slow regressions.

## Evidence

- **Anthropic Engineering Blog:** Agents are harder to evaluate than single calls because "the capabilities that make agents useful — autonomy, intelligence, and flexibility — also make them harder to evaluate." They formalize four distinct evaluation layers: capability benchmarks (pre-deployment), task completion (does it finish?), trajectory quality (did it get there reasonably?), and behavioral/safety checks. — [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Langfuse Engineering:** "Evaluating only the final answer misses most failure modes." They recommend evaluating tool-argument correctness on tool-call observations (not final text), scoring task completion on the trace root, and recognizing that sessions — not individual traces — are the unit users experience for conversational agents. — [AI agent evaluation: trajectory, tool calls, and task completion](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **LangChain Blog:** "A model can top every benchmark and still fail the task your agent was built to do." Leaderboard scores answer one question: how did the base model perform under controlled conditions? Once a retrieval layer, tool calls, and user-specific context are added, public benchmarks say nothing about real-world performance. — [LLM Evaluation Benchmarks: What They Measure & Miss](https://www.langchain.com/resources/llm-evaluation-benchmarks)
- **MorphLLM / YC State of AI Agents 2026:** "A super-majority of respondents said evals often under-deliver because keeping them up to date becomes an impossible task." All seven major eval frameworks are offline-first; none run per-turn evaluation in production. — [AI Agent Evaluation Frameworks (2026): 7 Compared](https://www.morphllm.com/ai-agent-evaluation-frameworks)
- **Galileo Labs:** Production agents face failure modes traditional monitoring can't detect — wrong API calls made hundreds of times, invisible trajectory divergence, data corrupted silently. Gartner predicts 40% of agentic AI projects will be canceled by 2027, citing evaluation infrastructure gaps as a primary cause. — [7 Best Agent Evaluation Frameworks](https://galileo.ai/blog/best-agent-evaluation-frameworks)
- **Langfuse Engineering:** Golden datasets are "a curated collection of inputs with reviewed reference outputs." The hard part isn't building one — it's keeping it representative for six months while prompts, models, and user traffic all drift. Maintenance requires schema validation, deduplication, and item versioning. — [Golden dataset evaluation: build and maintain LLM test sets](https://langfuse.com/resources/engineering/golden-dataset-evaluation)
- **Confident AI / DeepEval:** "Track operating envelopes (cost, latency, step/token budgets) in the same traces used for quality — not only pass/fail scores." Human rubrics on a sample of traces calibrate LLM-as-judge and surface the "metric green, user red" failure mode that pure automation misses. — [AI Agent Evaluation: Metrics, Traces, Human Review](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)
- **GrowthEngineer.ai (May 2026):** Practical framework comparison: solo teams start with DeepEval or Arize Phoenix (Apache 2.0, local); five-person teams use Braintrust ($249/mo flat) or LangSmith ($39/seat/mo); regulated enterprises need Galileo, Confident AI self-hosted, or Inspect AI. — [8 AI Agent Evaluation Frameworks: A Hands-On Comparison](https://growthengineer.ai/blog/ai-agent-evaluation-frameworks-compared)

## Gotchas

- **Eval suite green, users red.** This is the canonical failure. It means your metrics are measuring the wrong things. Run human annotation on a sample of production traces and compare against your automated scores — calibrate until they agree.
- **Golden dataset drift.** If you haven't added a test case from a production incident in the last 30 days, your dataset is already stale. Set a recurring calendar item to review recent failures and promote representative ones to the gold set.
- **Stochastic masking.** A single trial on a critical path can pass by luck. Always run three to five trials for pass/fail decisions on stochastic tasks; track variance, not just averages.
- **Tool call surface ignored.** Most eval suites check final output quality but never assert that the right tool was called with the right arguments. Without structured logging of tool calls, you can't write these checks — and without these checks, you can't catch the most common production failure mode.
- **Offline-first gap.** If your entire eval pipeline is batch-and-schedule, you will miss production regressions until the next scheduled run. Even a lightweight 1% production sampling loop with automatic alerting catches what quarterly offline suites cannot.
