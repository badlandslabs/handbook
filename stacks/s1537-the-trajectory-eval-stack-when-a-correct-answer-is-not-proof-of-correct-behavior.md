# S-1537 · The Trajectory Eval Stack — When a Correct Answer Is Not Proof of Correct Behavior

You have an agent that ships correct answers 80% of the time — until it doesn't, and you have no idea why. A demo that works on one input, on one good day, tells you almost nothing about production reliability.

## Forces

- **The final-answer trap** — an agent can reach the right output via a wrong or fragile process (e.g., citing last year's report and getting lucky). Standard accuracy metrics miss this entirely.
- **The compounding error problem** — with 20 steps each at 95% reliability, expected success rate drops to ~36%. This is not theoretical; it describes most real agentic pipelines.
- **Non-determinism** — the same input can produce different trajectories on different runs. A single test run is a sample, not a verdict.
- **The silent failure gap** — teams with observability but no regression suite can *inspect* a bad run after it happens, but still ship the same failure twice.
- **Cost is invisible without measurement** — similar accuracy across agent designs can hide 50x cost variation ($0.10–$5.00/task). Optimizing for accuracy alone produces agents 4.4–10.8x more expensive than necessary.

## The Move

Evaluate the trajectory, not just the output. Build a three-layer eval stack and wire it into CI.

### Three-layer eval architecture

- **Outcome metrics** — did the agent achieve the user's goal? Binary or graded pass/fail on the final result. Necessary but insufficient.
- **Trajectory metrics** — *how* did it get there? Was the tool sequence right? Did it use more steps than necessary? Were arguments correct? Did it loop or retry unnecessarily? This is where silent failures surface.
- **Component metrics** — did individual parts (retrieval, tool calls, reasoning) function correctly in isolation?

### The trace → test pipeline

1. **Capture production traces** — every tool call, input, and output. This is the raw material for everything else.
2. **Label and cluster** — surface recurring failure modes. Failure patterns become test categories.
3. **Feed failures back into the regression suite** — every diagnosed production incident should produce a versioned test case. This is your golden dataset, built from scar tissue, not synthetic benchmarks.
4. **Wire into CI** — the eval suite gates deploys. If the regression suite regresses, the deploy is blocked.

### Data generation strategies

- **Synthetic via dueling LLMs** — use a second model to role-play as a user, generating diverse multi-turn conversational data at scale.
- **Anonymize production data** — use real user interactions (with PII removed) as a golden dataset that captures actual usage patterns and edge cases.
- **Human-in-the-loop curation** — save valuable interactive sessions from logs as permanent test cases, enriching the suite continuously.

### Grading approaches

- **Deterministic checks** (fast, reliable) — verify tool call order, argument shapes, absence of loops, invariant holds, and output format. These catch the most common regressions.
- **LLM-as-judge** (slow, interpretive) — use a second LLM to grade response quality, policy compliance, and reasoning coherence where interpretation matters. Calibrate against human labels before trusting scores. Shape with Schema-Guided Reasoning (SGR) to reduce variance.
- **Golden datasets** — curated inputs with verified correct outputs. Use for regression detection, benchmarking, and measuring improvements across versions. The dataset is versioned alongside the agent.

### Metrics by failure mode

| Failure mode | Metric |
|---|---|
| Wrong final answer | Task success rate |
| Flailing to the right answer | Step efficiency (optimal_steps / actual_steps) |
| Tool misuse | Tool-call precision/recall/F1 vs. reference trace |
| Excessive cost | Cost per task; token efficiency |
| Policy violations | LLM judge / deterministic policy checks |
| Brittle across runs | Success rate over N trials per task |

### Three-layer operational stack

| Layer | When it runs | What it answers | Gates deploy? |
|---|---|---|---|
| Evaluation harness | CI, before deploy | Did this change break the agent? | Yes |
| Observability | During production | What is the agent doing right now? | No |
| Audit trail | After the fact | What exactly happened on run X? | No |

## Evidence

- **Google Cloud Blog:** Silent failures — agents producing correct outputs through incorrect processes — require trajectory-level inspection to detect. Proposes a 3-pillar framework: task success, trajectory analysis, and operational constraints (cost, latency, token efficiency). Recommends dueling LLMs and anonymized production data for test generation. — [Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Anthropic Engineering:** Agents are state machines with branching, not functions. The same input produces a distribution of trajectories. They recommend building eval suites before deployment, starting with simple end-to-end success criteria and layering in trajectory and component checks. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **ArXiv (CLEAR Framework):** Current benchmarks evaluate accuracy but ignore cost and reliability. The CLEAR paper documents 50x cost variation ($0.10–$5.00/task) across agent designs with similar accuracy, and finds that accuracy-only optimization produces agents 4.4–10.8x more expensive than cost-aware alternatives. — [arXiv:2511.14136](https://arxiv.org/html/2511.14136v1)
- **Slava Dubrov / Edge of Context:** The compounding error problem (0.95^20 ≈ 36% success) makes trajectory metrics non-optional. Recommends: trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring loop. Deterministic checks for tool ordering; LLM judges only where interpretation is needed and calibrated against human labels first. — [Edge of Context Blog](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)
- **GitHub (tkarim45/agent-eval-harness):** An agent harness measuring four metrics simultaneously: task success, tool-call F1 vs. reference trace, step efficiency ratio, and cost per task. Correct answers reached by 8 flailing steps score differently from 3 efficient steps. — [GitHub](https://github.com/tkarim45/agent-eval-harness)
- **LangChain State of Agent Engineering:** 57.3% of surveyed respondents have agents in production, but only 52.4% run offline evals and 37.3% run online evals — despite 89% having some observability. The dominant blockers are quality (32%) and latency (20%). — [LangChain](https://www.langchain.com/state-of-agent-engineering)

## Gotchas

- **A passing demo is the weakest signal of production readiness.** It exercises one path, on one input, on one good day. If evaluation consists of a demo, the agent is not evaluated.
- **LLM-as-judge needs calibration.** Without human-labeled ground truth to compare against, judge scores can drift. Use Schema-Guided Reasoning to reduce variance, and validate against human labels before trusting any threshold.
- **Golden datasets go stale.** As your agent evolves, test cases drift from production behavior. Curate continuously — delete obsolete cases, add new failure patterns from live incidents.
- **Test data and monitoring data require different pipelines.** Testing uses curated, versioned inputs written by the team. Production inputs are unpredictable and cannot be pre-labeled. Mixing these pipelines produces either fragile tests or unactionable alerts.
- **Optimizing cost is not free.** Cutting tokens by using weaker models or fewer retries can hurt accuracy. The CLEAR framework's finding (4.4–10.8x cost reduction with comparable accuracy) requires deliberate measurement, not assumption.
