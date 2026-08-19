# S-2856 · The Trace-to-Eval Loop Stack — When You Don't Know If Your Agent Got Better or Worse

You shipped a prompt update, changed the model, added a retry handler. Your dashboard shows the same request volume and latency. Nobody complained. But you have no idea whether the agent actually improved, degraded, or just started failing in different ways. This is the agent evaluation gap: traditional software testing assumes deterministic outputs, but agents produce variable trajectories, and without a measurement loop you are flying blind in production.

## Forces

- **Output quality hides trajectory quality.** An agent can reach the correct answer by skipping a required step, looping 15 times, or hallucinating a tool result it got lucky on. Final-output grading misses all of this.
- **Eval sets rot.** Hand-crafted test cases drift from production reality over weeks. The moment your eval set stops reflecting real failures, you are optimizing for a ghost.
- **LLM-as-judge is a liability without calibration.** Uncalibrated judges carry position bias (preferring first/last options), verbosity bias (rewarding longer answers), self-preference (favoring outputs similar to their own style), and drift as the model version changes.
- **pass@k hides consistency.** A 70% per-trial success rate reads as ~97% on pass@3 (best-of-three) but only ~34% on pass^3 (consistency across all trials). Optimizing for best-case masks reliability.

## The move

Build a closed loop from production traces into versioned eval datasets, with two scorer types and one CI gate.

**Capture traces at every layer:**
- Session level: task completion, cost, latency, user feedback signals
- Trace level: full trajectory — tool calls, arguments, responses, retries, termination decisions
- Span level: individual step quality — did the right tool get called with the right arguments?

**Build eval datasets from production failures, not a blank page:**
- Sample failed and anomalous production traces monthly
- Label the root cause (wrong tool, hallucinated result, infinite loop, schema violation, missed step)
- Cluster failures by type, dedupe, and add to the versioned eval dataset
- Start with 20–50 real failure cases — enough to establish a baseline, not enough to drown in curation

**Use two scorer classes, deliberately:**
- Code-based (deterministic): verify tool call order, argument schemas, loop counts, invariant checks, API response parsing. Fast, reproducible, zero calibration cost.
- Model-based (LLM-as-judge): semantic quality — did the reasoning chain hold? Was the tone appropriate? Is the answer grounded in retrieved context? Requires calibration against a human gold set before trusting scores.

**Calibrate LLM judges before shipping them:**
- Run judge output against a 20–50 sample human-labeled gold set
- Measure agreement rate; reject judges below ~80% agreement until retrained
- Use Schema-Guided Reasoning (SGR) to structure judge prompts — give them a rubric, not freeform discretion
- Re-calibrate after any model version change

**Measure consistency, not just success:**
- Track pass^k (all-k consistency) alongside pass@k (best-of-k success)
- A high pass@3 with low pass^3 signals the agent is lucky, not reliable
- Set a consistency floor — if pass^3 drops below threshold, the agent is unsafe regardless of pass@3

**Gate CI on real scores, not vibes:**
- Run the full eval suite on every deploy candidate
- The gate is: all scorers above threshold AND pass^k above floor AND no regressions on known failure types
- Do not skip the gate because the sprint is behind — skipping once creates a precedent and the dataset starts rotting

**Close the loop:**
- Production traces → anomaly detection → labeled failure → added to dataset
- Eval dataset → CI gate → deploy → production monitoring
- If monitoring detects quality drift, trigger eval rerun before users notice

## Evidence

- **Anthropic engineering blog:** Agents must be evaluated on multi-turn trajectories, not single outputs. Key dimensions: task success, trajectory efficiency, tool use accuracy, safety. Recommend trajectory-level grading alongside outcome grading. — [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Amazon AWS ML blog:** After building thousands of agents since 2025, discovered traditional LLM benchmarks fail for agentic systems — they treat agents as black boxes, evaluating only final output. Amazon's framework covers tool selection accuracy, multi-step reasoning coherence, memory retrieval efficiency, and task completion success rates. — [AWS: Evaluating AI Agents: Real-World Lessons](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Braintrust eval guide:** Core eval pattern is data + task + scorers. Production traces become test cases. Offline evals run ahead of deploys. Same scorers run on live data so monitoring tracks quality alongside technical metrics. — [Braintrust: How to Eval in Production](https://www.braintrust.dev/articles/how-to-eval)
- **Independent practitioner (Edge of Context):** A refund agent can end well while the trace is wrong — skipping the required tool, looping 17 times, or following a production-forbidden path. Answer-only grading hides those failures. Recommend the loop: trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring. — [Edge of Context: AI Agent Evaluation in Production](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)
- **Digital Applied methodology guide:** pass^k (consistency across all k trials) exposes what pass@k (best-of-k) hides. An uncalibrated LLM judge carries five bias types: position, verbosity, self-preference, format, and drift. — [Digital Applied: Building an AI Agent Evaluation Pipeline](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)

## Gotchas

- **You need both offline and online evals.** Offline eval catches regressions pre-deploy. Online monitoring catches novel failure modes, quality drift, and jailbreaks that only emerge under production traffic. Neither alone is sufficient.
- **Synthetic eval sets diverge from reality.** Curation teams unconsciously select for solvable, unambiguous cases. Real production traces include ambiguity, tool failures, and edge cases that nobody thought to include. Always seed from production, not from imagination.
- **Benchmarks are prerequisites, not proof.** MMLU and HumanEval scores tell you the foundation model can reason. They say nothing about whether your agent reliably calls the right tool in the right order. Use benchmarks to rule out bad models; use your own eval loop to prove your agent works.
- **Token count and latency are first-class metrics.** Agents that work correctly but burn 10× the expected tokens or take 30 seconds per task fail in production regardless of accuracy. Cost per task and time-to-first-token belong on the eval dashboard alongside quality scores.
- **Human-in-the-loop cannot scale the whole system.** Expert review catches subtle failures but does not scale to thousands of runs per day. Use human labels to calibrate and validate, not to gate every evaluation.
