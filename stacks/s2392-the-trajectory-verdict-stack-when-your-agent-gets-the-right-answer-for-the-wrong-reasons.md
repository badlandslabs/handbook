# S-2392 · The Trajectory Verdict Stack — When Your Agent Gets the Right Answer for the Wrong Reasons

Your agent completes the task. The final output looks correct. You ship it. Three weeks later, a customer reports that the agent cited last year's inventory report to justify a pricing decision — the number was right, but the reasoning chain was broken from step two. This is the **silent failure** problem: agents that score well on output-level evaluation while executing through fundamentally flawed trajectories. Standard evaluation catches the symptom; trajectory evaluation catches the disease.

## Forces

- **Correct output ≠ correct reasoning.** An agent can reach the right answer through a hallucinated tool call, a wrong parameter, or a misread API response. Final-output evaluation has no signal on process quality.
- **Agents are probabilistic; traditional testing assumes determinism.** The same input can produce different trajectories on different runs. Hard pass/fail thresholds create false confidence.
- **LLM-as-judge creates an echo chamber.** Automated judges share the blind spots of the models they evaluate. A judge model that hallucinates will not catch hallucinations in the agent it's grading.
- **Volume kills manual review.** Production agents can execute 50+ tool calls per session. Human review of every trajectory is a scaling ceiling, not a solution.
- **Enterprise teams need auditability, not just accuracy.** Regulated industries need to reconstruct *why* an agent made a decision, not just whether the outcome was acceptable.

## The move

**Evaluate trajectories, not outputs — and do it at three levels.**

### 1. Instrument the full trace first
Before you can evaluate trajectories, you need to capture them. Use tracing infrastructure (LangSmith, Langfuse, OpenTelemetry) to log every step: tool calls, parameters, responses, and intermediate reasoning. This is non-negotiable infrastructure — without it, you are guessing.

### 2. Score at three levels
- **Trajectory-level:** Did the agent follow a sound process? Were the right tools called in the right order with valid parameters? LangChain's `agentevals` package and LangSmith trajectory evaluators support both deterministic trajectory matching and LLM-as-judge scoring at this level.
- **Tool-call-level:** Did each individual tool invocation succeed? Did it receive a valid response? Did it handle empty/error responses appropriately? This is where silent failures compound — a failed CRM lookup that gets ignored rather than retried.
- **Output-level:** Is the final answer correct, complete, and grounded in the retrieved context? This is your baseline, but treat it as necessary not sufficient.

### 3. Use hybrid evaluation — judge + human spot-checks
Automated LLM judges scale but require calibration. Calibrate against human annotations using statistical correlation (e.g., Spearman correlation between judge scores and human ratings). Run human review on a stratified sample — deliberately include cases where the judge was confident and cases where it was uncertain.

### 4. Build a versioned golden dataset from production failures
Every production incident, customer complaint, or caught regression is a test case. Add it to a curated, versioned golden dataset with metadata: task type, failure mode, severity, and expected behavior. DeepEval (Confident AI's open-source framework) is designed around this pattern — the team reports running 600K+ evaluations daily in CI/CD pipelines for enterprises including BCG, AstraZeneca, AXA, and Capgemini.

### 5. Set soft thresholds, not hard gates
For non-deterministic agents, use soft failure thresholds in CI: if a test fails 2 out of 3 runs, flag for review rather than blocking the pipeline. Hard gates on probabilistic systems produce noise that erodes trust in the evaluation system itself.

### 6. Detect silent failures systematically
IBM Research's study of silent failures in multi-agentic AI trajectories (2025) found that XGBoost (supervised) and SVDD (semi-supervised) achieved 98% and 96% accuracy respectively in detecting anomalous trajectories. Crucially, semi-supervised approaches are more practical — they require far less annotated data, which is the real bottleneck.

## Evidence

- **Survey (KDD '25):** "Evaluation and Benchmarking of LLM Agents: A Survey" — SAP Labs researchers introduced a two-dimensional taxonomy organizing agent evaluation along evaluation objectives (behavior, capabilities, reliability, safety) and evaluation process (interaction modes, benchmarks, metrics, tooling). Emphasizes that enterprise challenges — role-based data access, reliability guarantees, dynamic long-horizon interactions, and compliance — are "often overlooked in current research." — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)

- **Engineering post (Google Cloud):** Google's methodical approach to agent evaluation identifies "silent failure" as the core problem: "An agent can produce a correct output through an inefficient or incorrect process." Their framework evaluates three dimensions: trajectory (sequence of reasoning and tool calls), agentic interaction (how the agent adapted to feedback), and output quality. — [Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)

- **Engineering post (Verel Systems):** Documents a real silent failure: "A routing agent hallucinates a date parameter on step two, passes it to an internal CRM tool on step three, receives an empty array, and confidently tells the user their account does not exist." Proposes multi-level tool-call evaluation as the solution — evaluating intermediate steps, not just final output. — [Verel Systems Blog](https://verelsystems.com/en/blog/agent-evals-in-production-tracing-tool-use-and-trajectories)

- **Research paper (ACM ICPE '25 companion):** "Detecting Silent Failures in Multi-Agentic AI Trajectories" — IBM Research provided the first systematic study of silent-failure detection, with datasets of 4,275 and 894 trajectories. Key finding: semi-supervised anomaly detection (SVDD, 96% accuracy) is nearly as effective as supervised (XGBoost, 98%) while requiring far less labeled data. — [arXiv:2511.04032](https://arxiv.org/html/2511.04032v1)

- **HN Launch (YC W25):** Confident AI (DeepEval) launched on HN with real production numbers: "over 600K evaluations daily in CI/CD pipelines of enterprises like BCG, AstraZeneca, AXA, and Capgemini." Described as "Pytest for LLMs." — [Hacker News](https://news.ycombinator.com/item?id=43116633)

- **Engineering guide (Claude Implementation):** Documents the probabilistic-vs-deterministic distinction: "The same input, run twice, may produce different outputs... Agents are probabilistic. Unit tests ask: 'Does this code do what I programmed?' Agent evals ask: 'Does this agent accomplish the user's intent?'" — [claudeimplementation.com](https://claudeimplementation.com/blog/ai-agent-evaluation-testing)

- **Blog post (Label Studio):** "Automated LLM judges share the blind spots of the agents they evaluate." Proposes hybrid: calibrated LLM judges plus human-in-the-loop with visual trace inspection. — [Label Studio Blog](https://labelstud.io/blog/how-to-evaluate-ai-agents-in-production)

## Gotchas

- **Output-only evaluation misses the compounding error.** A broken CRM lookup at step 3 that goes unhandled produces a plausible-sounding wrong answer at step 10. Scoring only the final output never surfaces the root cause.
- **LLM-as-judge bias is structural, not fixable by prompting.** A judge model that is itself prone to hallucination will confidently assign high scores to hallucinated tool calls. Always calibrate judge output against human annotations — don't assume alignment.
- **Hard CI gates on non-deterministic agents produce alert fatigue.** If your agent fails a test 1 in 10 runs for legitimate probabilistic reasons, a hard gate creates 10% pipeline failure rate. Use soft thresholds with trend detection instead.
- **Golden datasets rot.** A test set that hasn't been updated since launch will never catch regressions against new failure modes discovered in production. Treat your golden dataset as a living artifact — add cases from every incident.
- **Trajectory capture overhead is real.** Verbose tracing on high-volume agents adds latency and cost. Scope detailed instrumentation to evaluation runs; use lightweight sampling in production.
