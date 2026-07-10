# S-919 · Evaluating Agents: The Trace Is the Truth

[Offline eval suites pass while agents still fail in production. The gap isn't a test coverage problem — it's an architectural one. The fix is evaluating trajectories, not responses, and closing the loop between production traces and the eval dataset.]

## Forces
- [Static benchmark scores (tool-call accuracy, pass rate) are single-response metrics. Agents produce 10–50+ steps per run, and a wrong answer can come from a trajectory that looked locally fine at every step.]
- [Offline eval sets are snapshots. Production is a moving distribution. The moment an eval set ships, it begins aging — new user intents, API schema changes, and prompt drift all make the curated set progressively less representative.]
- [LLM-as-judge is the dominant scoring mechanism but has known failure modes: positional bias (it prefers the first answer), verbosity bias (longer is scored higher), and self-preference bias (a model often scores its own outputs higher).]
- [Per-step success compounds multiplicatively. A 95%-accurate step over 8 steps yields ~66% end-to-end success. Teams celebrating 95% per-step accuracy are often delivering failure two-thirds of the time.]
- [Standard APM (application performance monitoring) tools were designed for deterministic software. AI agents are non-deterministic — same input can produce different outputs, making traditional latency/error-rate alerting insufficient.]

## The move
Score **trajectories**, not responses. Build a **closed loop** from production traces back into the offline eval set.

### Score six trajectory dimensions
| Dimension | Measures | Failure mode |
|---|---|---|
| **Tool Selection** | Right tool picked, or correctly called none | Wrong tool, fabricated tool, missed capability |
| **Argument Extraction** | Schema-valid, semantically correct args | Right tool, wrong date format, missing required field |
| **Result Utilization** | Agent used tool payload, not substituted model knowledge | Number flipped, entity swapped, payload ignored |
| **Error Recovery** | Retry, fallback, or escalation on tool failure | Crash, hallucinate success, infinite retry loop |
| **Trajectory Efficiency** | Steps to completion vs. minimum required | Excessive loops, redundant tool calls |
| **Output Quality** | Groundedness, refusal calibration, policy compliance | Hallucinated citations, unsafe completions |

### The five-stage closed loop
1. **Offline eval** — versioned trajectory dataset in CI. Deterministic gates (exact-match assertions for structured outputs) + rubric scores for open-ended quality.
2. **CI gate** — per-dimension assertions. A trajectory fails if any single dimension falls below threshold. No human judgment at this gate.
3. **Production trace eval** — sample production sessions, tag each with EvalTags (per-dimension scores). Score every span, not just the final output.
4. **Error Feed** — cluster production failures automatically. Score clusters by frequency and severity. The highest-scoring cluster writes a new golden example directly into the offline eval set.
5. **Promote-back** — the key architectural step. Production failure → root cause → new eval case → offline dataset update → next CI run. The loop is the differentiator.

### Detect the six drift modes
| Drift | Offline evals see | Production actually does |
|---|---|---|
| Dataset drift | All curated cases pass | New user intents never in the set |
| Tool-API drift | Mocked tool returns same shape | Vendor changed schema or rate limits |
| Prompt drift | Rubric written for v3, frozen in git | Product team updated copy, agent silently reinterprets |
| Retrieval-corpus drift | RAG evals pass | Index went stale, retrieved docs are irrelevant |
| User-distribution drift | High score on known inputs | Edge cases arriving in production never seen offline |
| Agent-step compounding | Every step scores green | Math guarantees failure — 0.95^8 = 0.66 |

## Evidence
- **Engineering blog (LangChain, 2026):** Agents fail non-deterministically — the same input can produce different outputs. Because traces document where agent behavior emerges, they power evaluation in ways that static test suites cannot. Evals do the heavy lifting in two lifecycle stages: pre-deployment comparison and post-deployment monitoring. — [LangChain: Agent observability powers agent evaluation](https://www.langchain.com/blog/agent-observability-powers-agent-evaluation)
- **Technical analysis (Future AGI, 2026):** An agent eval is a function from *trajectory* to a score, not from *response* to a score. A response that looks right can come from the wrong tool with the wrong arguments by luck. The trace is the truth. End-to-end success on a k-step agent is roughly the product of per-step success rates — two-thirds of sessions ending structurally wrong while every individual step scores green is the *default math* of compound accuracy. — [Future AGI: Agent passes evals, fails production (2026)](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)
- **Industry analysis (Swarm Signal, 2026):** Standard LLM benchmarks miss the failures that actually hurt in production. The reliability gap: benchmark performance looks clean while production behavior is brittle. Benchmark score ≠ production reliability. One 2025 analysis of agent benchmarks found validity and cost-estimation problems across widely used benchmarks. — [Swarm Signal: How to build agent evals that catch real failures](https://swarmsignal.net/agent-evals-production-failures)
- **MLOps community (Agents in Production 2025):** Conference with 27 talks on production agent infrastructure. Common theme: traditional APM tools fall short for agentic systems. Agent monitoring adoption up 30% QoQ (2025–2026). OpenTelemetry releasing semantic conventions for agents. — [MLOps Community: Agents in Production 2025](https://home.mlops.community/en/public/collections/agents-in-production-2025-2025-07-23)
- **Production guide (Data Science Duniya, Principal ML Engineer, 2025):** Standard unit tests are "pretty much useless" for agents. You can't check if function A returns value B for input C — agents are dynamic, context-dependent, and sometimes unpredictable. Define success criteria before measuring anything. — [Data Science Duniya: AI Agent Performance Evaluation](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide)

## Gotchas
- **Scoring only the final output** misses every failure that happened mid-trajectory. Always instrument at the span level.
- **LLM judges have systematic biases** — calibrate against human labels before trusting judge scores. Run inter-annotator agreement studies.
- **The eval set rots on day one.** Without a promote-back mechanism from production traces, the offline suite progressively misrepresents reality.
- **Compound accuracy is invisible** when you only track per-step metrics. Teams with 95% step accuracy are shipping 66% end-to-end success over 8 steps — and often don't know it.
- **Mocked tools in CI** hide the most common production failure mode: tool-API drift (schema changes, error code changes, rate limit changes that the mock never caught).
