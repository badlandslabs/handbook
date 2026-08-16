# S-2734 · The Attribution Ladder — Why Your Agent Eval Is Measuring the Wrong Thing

Your agent scores 94% on your eval suite. In production it deletes a customer's database, loops 200 times on a malformed input, and silently burns through your monthly API budget. The eval suite didn't miss the agent — it never tested the failure modes that actually break in production. The attribution ladder is the practice of building evals that correctly assign failure to the right layer: the model, the tool, the pipeline, or the environment.

## Forces

- **Benchmarks measure model quality, not system reliability.** A benchmark gives a single task a single correct answer. Production agents operate across sequences of steps, call external tools, receive incomplete context, and hand off to other agents. Each transition is a point where error accumulates. Three agents at 70% accuracy each yield only 34% reliability as a chain.
- **"Works in demo" is the worst possible signal.** Demos use clean inputs, the right environment, and a human watching every step. Production throws edge cases, stale credentials, network timeouts, and adversarial inputs — none of which show up in a curated eval set.
- **Task success is harder to define than it looks.** For a support agent, "success" might mean the customer's issue was resolved, not just acknowledged. For a coding agent, it might mean the code compiles AND passes tests AND doesn't regress existing behavior. Getting the definition wrong warps every downstream metric.
- **Silent failures are invisible to traditional monitoring.** An agent receiving 401 errors from a stale API token, retrying with the same token, then proceeding with empty data as if the tool call succeeded — this passes a naive error-rate dashboard. No alert fires.

## The move

Use a **three-layer eval architecture** that matches evaluation scope to failure mode:

**Layer 1 — System efficiency (trajectory-level)**
- Task completion rate across the real input distribution (not test distribution)
- Cost per completed task, tracked continuously
- Goal drift: how far the agent's behavior strays from the defined activity schema over time
- Average trajectory length and token cost per session

**Layer 2 — Session quality (step-level)**
- Step-level success rate within a workflow — know exactly where failures cluster
- Tool call frequency and retry rate — flag when they exceed expected bounds
- Tool selection accuracy — did the agent invoke the correct tool with correct arguments?
- Whether the agent correctly utilized tool output to proceed

**Layer 3 — Component precision (node-level)**
- Retrieval quality (if the agent uses a knowledge base)
- Response groundedness — does the output stay within the knowledge base?
- Hallucination detection on intermediate reasoning steps
- Safety and tone compliance

**Layer 4 — Runtime governance (production traffic)**
- LLM-as-Judge scoring on production traces without ground truth
- Token budget alerts — flag when spend exceeds bounds on a single request or session
- Data leakage checks — detect whether the agent exposes customer context to the model provider inappropriately
- Automated regression detection: production failures auto-generate new eval cases

**Offline + Online feedback loop**: Run offline evals with known cases before every deploy. In production, sample traces and score them with LLM-as-Judge. Every caught failure becomes a new offline eval case. This compounds your coverage over time without requiring a massive initial dataset.

**The attribution ladder**: When an eval fails, work downward through the layers to find the root cause. Did the model fail? Did the tool return garbage? Did the pipeline mis-route the output? Did the environment have the wrong credentials? Most eval setups only surface Layer 1, so they can't fix what they can't see.

## Evidence

- **HN Post (Ask HN):** Developer tried benchmark-style agent evaluation; the dominant failure mode was system-level problems — broken URLs in tool calls dropped scores to 22%, agents calling localhost in cloud environments — not model quality. Key lesson: build evals that find what actually breaks before blaming the model. — [HN #47416033](https://news.ycombinator.com/item?id=47416033)
- **Engineering Blog (Prefactor Tech, July 2026):** Research found ~90% of agents showed measurable goal drift after ~30 steps. Production eval needs: task completion rate across real input distribution, step-level success rate (to locate failure clusters), cost per task tracked continuously, and tool call frequency/retry rate with bounds alerting. — [Prefactor Tech](https://prefactor.tech/blog/ai-agent-reliability-gap-benchmarks-vs-production)
- **Eval Framework (DeepEval, 17.6k GitHub stars):** Three-layer eval architecture: trajectory metrics (planning and execution quality), session-level metrics (task success, trajectory quality), node-level metrics (tool selection accuracy, step utility). Integrates with LangChain, LangGraph, OpenAI Agents, CrewAI, Google ADK, Pydantic AI. — [GitHub confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **LLM-as-Judge research (MLflow, 2025-2026):** LLM judges produce verbosity bias (~15% score inflation on longer responses regardless of quality), position bias (first and last responses rated higher), self-preference bias (models rate their own outputs higher). Mitigation: use a reference answer, randomize order, prefer a judge model different from the evaluated model. — [MLflow LLM-as-Judge](https://mlflow.org/llm-as-a-judge)

## Gotchas

- **Defining "success" is the hardest part and most teams get it wrong.** If you define task success as "agent returned a response," your support agent scores 100% while leaving every customer issue unresolved. The definition must match the actual business outcome, not the agent's ability to produce output.
- **LLM-as-Judge has systematic biases — don't trust raw scores without calibration.** Verbosity bias, position bias, and self-preference bias can make a worse agent look better. Always cross-check judge scores against a sample of human-rated cases.
- **Your eval suite only tests what you've already thought to test.** Production catches cases you didn't know to test. Without online eval (sampling production traces and scoring them), you'll never close this gap — you'll just ship confidently wrong agents.
- **Goal drift is real and fast.** Agents start drifting measurably around 30 steps into a task. For long-horizon agents, you need either a shorter max-turn limit or active drift detection against a defined activity schema.
- **Cost tracking is not optional.** Agents that loop or retry excessively can burn through budgets fast. Track cost-per-task in real time and alert on anomalies — it's the fastest signal that something is wrong.
