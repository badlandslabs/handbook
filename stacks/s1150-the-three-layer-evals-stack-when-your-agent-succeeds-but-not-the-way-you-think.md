# S-1150 · The Three-Layer Evals Stack — When Your Agent Succeeds But Not the Way You Think

A support agent ships on Friday. It calls `lookup_customer`, then `get_balance`, then drafts a reply. By Wednesday it's calling `get_balance` first with a fabricated customer ID, getting a permission error, then apologizing fluently. The final message looks fine. The trajectory is broken. Nobody caught it because the only thing being scored was the last reply.

## Forces

- **Output evaluation is the floor, not the ceiling.** A correct final answer via a broken reasoning chain is a latent production defect — the next input won't be lucky. Output-only scoring misses 20–40% of regressions (per production evaluation guides, 2026).
- **Benchmarks lie about production readiness.** GAIA, SWE-bench, and MMLU test capability in isolation — clean inputs, single-turn, no adversarial users. The 37% gap between benchmark performance and production behavior is well-documented in agent evaluation literature.
- **Agents are stochastic pipelines, not functions.** They accumulate cost and error at every step. A 3-call solution and a 40-call solution with the same output can have 13x cost difference and very different failure profiles.
- **The constraint decay problem.** A May 2026 arXiv study (Dente, Satriani, Papotti — EURECOM / University of Basilicata) showed LLM agents drop ~30 percentage points in assertion rates when structural constraints accumulate — ORM patterns, API contracts, framework conventions. Existing benchmarks reward functional correctness and ignore structural violations, so agents that "pass" benchmarks produce code that breaks in production.

## The Move

Score agents across three independent layers, gate releases on trajectory health, and wire production failures back into the eval corpus.

**Layer 1 — Black-box output evaluation (final response only)**
- Task completion rate: did the agent resolve the user's intent?
- Faithfulness: does the answer stay within retrieved/generated context?
- Hallucination: fabricated entities, wrong numbers, invented citations
- Use deterministic checks where possible (regex, JSON schema validation) before reaching for LLM-as-judge

**Layer 2 — Trajectory evaluation (step-by-step path)**
- Tool call accuracy: right tool, right arguments, right order
- Trajectory efficiency: steps-to-completion vs. a reference minimum
- Critical path violations: did the agent skip a required step or call tools out of order?
- Use structured logging (LangSmith, Helicone, or custom) to capture every LLM turn, tool call, and tool response as a trace. Evaluate the trace as a first-class artifact.
- LangChain's AgentEvals (646 stars, MIT license) provides readymade evaluators for trajectory assessment — `TrajectoryMatch`, `ToolCallAccuracy`, and `ReasoningStepValidator` are the core primitives teams reach for.

**Layer 3 — Production monitoring with online evaluators**
- Score every production run (or a sampled slice) for task success and safety violations
- Use LLM-as-judge with a structured rubric: give the judge a scorecard, not an open prompt. Calibration against human-labeled examples is mandatory — uncalibrated judges have documented consistency issues.
- Route production failures to an annotation queue. Freeze representative failed traces as regression tests via DeepEval's `@pytest` integration. This closes the loop: production signal → eval corpus → CI gate.

**The eval flywheel**
- Run offline eval (DeepEval in CI) before every release against a golden dataset
- Run online eval (LangSmith evaluators) on a sample of production traffic
- Use A/B experiment infrastructure (Braintrust) to measure model/prompt changes against the same eval suite before rolling out
- If a production failure reproduces offline in DeepEval, it is a regression test. If it doesn't reproduce, the production environment had state the eval missed — add it to the dataset.

## Evidence

- **NVIDIA Technical Blog (May 2026):** Formalized the three-layer evaluation model — model benchmarks (MMLU, GSM8K) for capability, agent benchmarks (GAIA, SWE-bench, WebArena) for trajectory, production monitoring for real-world reliability. Task Success Rate, Tool Call Accuracy, and Trajectory Efficiency are the three canonical agent metrics. — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)

- **arXiv 2605.06445 (May 2026):** "Constraint Decay" study ran 80 greenfield and 20 feature-implementation tasks across 8 web frameworks. Found LLM agents dropped ~30 percentage points in assertion rates as structural constraints (ORM patterns, API contracts, framework conventions) accumulated. FastAPI/Django — convention-heavy — showed worse decay than Flask. Data-layer defects (query composition, ORM violations) were the dominant error category. Dual evaluation methodology (end-to-end behavioral tests + static verifiers) caught failures neither approach found alone. — [arxiv.org/abs/2605.06445](https://arxiv.org/abs/2605.06445)

- **BestAIWeb eval pipeline guide (2026):** Documented the three-layer pipeline: DeepEval in CI for regression testing, Braintrust for A/B experiments, LangSmith for production traces. Key drill: "disable the response gate, send a known-bad live request — does the LangSmith online evaluator fire? Failure looks like: the trace is captured but no evaluator runs." Teams that skip this drill deploy decorative eval layers. — [bestaiweb.ai/how-to-build-an-agent-evaluation-pipeline](https://www.bestaiweb.ai/how-to-build-an-agent-evaluation-pipeline-with-langsmith-braintrust-and-deepeval-in-2026)

## Gotchas

- **LLM-as-judge without a rubric is noise.** "Evaluate the response" produces inconsistent scores. Give the judge a structured scorecard: criterion → definition → 1-5 scale. Calibrate against 20-50 human-labeled examples before trusting the scores.
- **A trajectory can be broken even when the answer is right.** The support agent example: correct final message, wrong tool call order, fabricated customer ID. If you only score outputs, you score past luck, not current reliability.
- **Golden datasets rot.** Production distributions shift. A test case from 6 months ago may no longer reflect real inputs. Refresh eval corpora quarterly, or better — wire production failures into it continuously via the annotation queue.
- **Cost-per-task is an eval dimension, not an ops concern.** Two agents with identical accuracy but 3x cost difference are not equivalent. Track tokens-per-task and calls-per-task in the same traces you use for quality evaluation.
