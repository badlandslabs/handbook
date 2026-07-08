# S-797 · The Recovery Loop: How Agents Bounce Back from Failures

Your agent's tool call returns a 429. Then the retry returns a 500. Then the fallback model times out. Meanwhile, 58 minutes of document processing state is gone because nobody checkpointed. You've handled errors before — but agents fail in layers, and most teams only handle one. This is the recovery loop: the architecture that lets agents survive cascading failures without wasting compute, corrupting state, or escalating to humans for problems a machine should solve.

## Forces

- **Agents fail in categories traditional try-catch doesn't cover.** Hallucinations return HTTP 200. Semantically wrong JSON passes schema validation. The tool succeeds technically but produces nonsense. Your error handling has to reach past the network layer into meaning.
- **State evaporates on failure.** A long-running document pipeline that crashes at minute 58 of 60 restarts from zero — unless you checkpointed. Most agent frameworks treat every invocation as stateless by default.
- **Retry without a ceiling burns money.** The Claude Code codebase documents an incident where recovery logic with no upper bound burned 250,000 API calls in a day. The agent was executing its recovery instructions exactly as designed — it just had no ceiling.
- **Cascade effects are exponential in multi-agent systems.** One agent's failure propagates through dependencies in unpredictable combinations. Traditional circuit breakers assume stateless services; agent context state makes recovery non-deterministic.

## The move

Layer recovery in three concentric rings:

**Ring 1 — Transient fault recovery (automatic, machine-level)**
- Retry with **exponential backoff + jitter** for rate limits (429) and server errors (500/503). Cap at 3-5 attempts. Use jitter to avoid thundering herd when the API recovers.
- Distinguish **retryable vs. non-retryable** failures upfront: parse the error type before retrying. A malformed JSON schema is not a transient fault — don't retry it.
- Add **semantic validation** after every tool call: not just "did it succeed?" but "did it return something that makes sense?" Cross-check returned values against expected ranges.

**Ring 2 — Persistent failure degradation (agent-level)**
- When retries exhaust, **fall back to a different model** (e.g., primary: GPT-4o, fallback: Haiku-grade) with a stripped-down prompt. You get a degraded but correct answer instead of silence.
- Implement **state checkpointing** every N steps or every completed subtask: write the agent's working state (task progress, intermediate outputs, conversation history) to durable storage. On failure, restore from the last checkpoint instead of restarting.
- Use a **circuit breaker** per external dependency: if Tool X has failed N times in a row, stop calling it for a cooldown period and route around it. This prevents cascade failures from spreading through the agent graph.

**Ring 3 — Escalation and handoff (human-in-the-loop, when needed)**
- Route persistent failures to a **specialized recovery agent** (e.g., the ARF framework's Detective/Diagnostician/Predictive trio) that analyzes root cause and proposes a fix rather than blindly retrying.
- Surface **structured failure summaries** to human operators: what failed, why the recovery attempts failed, what the agent's current state is, what action is recommended. Don't dump raw logs.
- Define an **escalation threshold**: cost ceiling, time ceiling, or irreversible-action boundary. When crossed, freeze agent state and alert. The 250K-call incident happened because there was no cost ceiling on recovery attempts.

## Evidence

- **GitHub repo:** Vectara's `awesome-agent-failures` (186 stars, 81 commits) documents 7 distinct failure modes with specific mitigations — from Tool Hallucination (RAG returns false data, agent acts on it) to Agent Loops (agent repeats actions without making progress) to Context Overflow (context window exceeded, agent loses critical history). Each has a community-vetted mitigation strategy. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Engineering post:** A former NetApp reliability engineer built the Agentic Reliability Framework (ARF) after handling 60+ critical incidents/month for Fortune 500 clients. The framework uses three specialized agents — Detective (FAISS-based anomaly detection), Diagnostician (causal root cause analysis), Predictive (failure forecasting) — achieving 2-minute MTTR vs. 45-minute manual recovery. The builder documented $50K-$250K per incident cost for unhandled agent failures. — [HN post via paragguptaclasses.blogspot.com](https://paragguptaclasses.blogspot.com/2025/12/show-hn-agentic-reliability-framework.html) | [Original HN](https://news.ycombinator.com/item?id=)
- **Production case study:** A financial services deployment of a document analysis agent on Google Cloud Run lost 58 minutes of work when a Cloud Run timeout hit during processing of regulatory filings (thousands of pages). After implementing checkpointing, the agent resumed from the last completed section. The pattern: serialize agent state (conversation history, task progress, intermediate artifacts) to durable storage at every subtask boundary. — [brandonlincolnhendricks.com](https://brandonlincolnhendricks.com/research/implementing-agent-checkpointing-recovery-patterns-long-running-ai-tasks)
- **Research finding:** Production deployments show AI agent success rate measurably decreases after just 35 minutes of runtime, with doubling of task duration quadrupling the failure rate. This "7-Hour Problem" makes checkpointing not optional but structurally necessary for any agent task exceeding ~30 minutes. — [agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/05/agent-state-persistence-long-running-task-recovery)
- **Open-source tool:** ZAI Shell (self-healing AI CLI) implements a concrete retry pipeline: captures stderr, retries up to 5 times with automatic strategy changes (shell type, encoding), and detects missing dependencies. Demonstrates layered recovery at the CLI tool level with specific automated remediation steps. — [github.com/TaklaXBR/zai-shell](https://github.com/TaklaXBR/zai-shell)

## Gotchas

- **Hallucination isn't caught by HTTP status codes.** Your retry logic needs semantic guards — check that returned values match expected types, ranges, and relationships. A 200 OK with fabricated data is a more dangerous failure than a 429.
- **Checkpoints are only useful if you can restore from them.** Teams write state to disk but forget to test the restore path. A checkpoint you can't replay is a false promise.
- **Jitter is not optional on retries.** Without random jitter, a burst of agents retrying simultaneously will overload the recovering API and cause a second wave of failures.
- **Circuit breakers must be per-dependency, not global.** A circuit breaker on "the LLM" that trips when one tool is down will degrade unrelated workflows that share the same breaker.
