# S-1732 · The Eval Sandwich Stack — When One Layer of Checking Isn't Enough

You run the eval. It passes. You ship. Three users report confident wrong answers in the first week. The eval suite didn't catch it because it checked the final output only — the agent had already gone off-rail in step 3 of 7, produced plausible-sounding intermediate results, and the final output looked fine in isolation. One layer of checking is a single point of failure. Teams that ship reliable agents layer checks: at the input gate, at decision boundaries, and at the output.

You reach for this when you trust a single pass/fail verdict, when "we have evals" means one judge model scoring one output, when self-correction is the only recovery mechanism, or when your eval suite runs offline but production runs live.

## Forces

- **The single-judge illusion** — running one LLM-as-Judge on final output feels rigorous but is structurally blind to mid-trajectory failures that produce locally-correct but globally-wrong answers
- **Self-correction is unreliable without grounding** — research through 2024–2025 consistently shows that prompting an agent to "check your work" without external feedback does not reliably improve outcomes; it mainly adds latency
- **Cheap checks miss nuance; expensive checks miss volume** — large proprietary judges (GPT-4o, Claude 3.7 Sonnet) are accurate but cost-prohibitive at every step; small distilled judges (Luna-2, Prometheus 2, Patronus Lynx) are fast but drop accuracy on ambiguous cases
- **Eval pass ≠ production success** — a 100% offline eval pass rate does not predict 100% desired outcomes; test coverage gaps mean failure modes that never appeared in the eval set go undetected until users find them
- **The trajectory problem** — an agent can take a wrong path, reach a plausible intermediate state, and from there produce a final output that looks correct to a judge that only sees the endpoint

## The move

Layer evaluation across the agent's execution, not just at the end. The pattern is three placement points with different judge models:

**Input gate (small judge, inline)** — validate tool inputs before execution. Does the search query make sense? Are the parameters in range? Is this request asking the agent to do something it shouldn't? Catch bad actions before they happen, not after. Small distilled judges (3B–8B parameters) achieve 0.88–0.95 accuracy here at 97% cost reduction versus large models. Classifying whether something is wrong is simpler than generating — use this asymmetry.

**Decision boundaries (large judge, selective)** — at every major fork in the agent's plan (tool selection, branching logic, escalation points), run a high-stakes judgment call. Is the chosen tool appropriate? Is the sub-task actually complete? Large proprietary judges (Claude 3.7 Sonnet, GPT-4o) for this layer — the accuracy premium pays when the decision gates downstream behavior.

**Output gate (hybrid)** — automated scoring (LLM-as-Judge + trace analysis + structural checks) for regression, human review for tone, trust, and contextual appropriateness. Run the automated layer in CI on every commit. Sample live traffic for human review. The automated layer catches regressions; the human layer catches what automation cannot define.

**Bonus layer — trace retrospection** — replay failed production cases through the agent offline with instrumentation. Identify which step first diverged from expected behavior. Build that divergence case into the eval set. This is how eval sets grow from production reality rather than assumed success cases.

## Evidence

- **Research survey:** 57%+ of surveyed production agent teams now use judge LLMs at runtime (2026). Field has bifurcated into large proprietary judges for high-stakes verification and small distilled judges for high-throughput inline checking — with small models delivering 97% cost reduction at 0.88–0.95 accuracy. Intrinsic self-correction without external grounding is consistently unreliable. — [Zylos Research, "LLM-as-Judge in Production" (2026)](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

- **Industry guide:** "Hybrid evaluation is non-negotiable. Automated scoring (LLM-as-judge, trace analysis, load testing) gives repeatability and scale. Human judgment captures what automation misses: tone, trust, and contextual appropriateness." Agents must be evaluated as composite systems — planning, tool calls, state, multi-turn adaptation — not as single-turn text generators. — [InfoQ, "Evaluating AI Agents in Practice" (March 2026)](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **Eval framework:** Most mature teams use multiple tools in combination: open-source evaluation in CI (DeepEval for general agents, RAGAS for RAG) for development-time regression testing, managed platforms (LangSmith or Braintrust) for collaborative experiment management, and observability tools (Phoenix, Langfuse, Helicone) for production monitoring. The tools complement each other across the agent lifecycle. — [AutoLearningAgents, "AI Agent Evaluation Frameworks Compared"](https://www.autolearningagents.com/ai-agent-evaluation/evaluation-frameworks.php)

- **YC startup:** HUD (YC W25) — "People don't actually know if AI agents are working reliably. To make AI agents work in the real world, we need detailed evals for a huge range of tasks." Building agentic evals and RL environments specifically for Computer Use Agents that browse the web. — [Y Combinator company profile](https://www.ycombinator.com/companies/hud)

- **arXiv survey (2025):** Two-dimensional taxonomy for agent evaluation: (1) evaluation objectives — agent behavior, capabilities, reliability, safety — and (2) evaluation process — interaction modes, datasets and benchmarks, metric computation, tooling. Enterprise-specific challenges (role-based access, reliability guarantees, dynamic long-horizon interactions, compliance) are often overlooked. — [arXiv 2503.16416, "Survey on Evaluation of LLM-based Agents"](https://arxiv.org/abs/2503.16416)

## Gotchas

- **Judge drift** — an LLM-as-Judge can develop its own biases and inconsistencies over time. Use a stable golden dataset to periodically re-calibrate the judge itself, not just the agent.
- **Eval coverage lag** — new failure modes only appear in eval sets after they've appeared in production. Close the loop by turning production incidents into eval cases within days, not months.
- **Over-engineering the eval stack** — don't build custom evaluation infrastructure for weeks before proving the agent works. Start with a minimal eval (even a spreadsheet of input/output pairs), ship the agent, then layer tooling as coverage gaps become clear.
- **Confusing offline pass with production safety** — an eval that only runs in CI never touches the live distribution of user input. Sample production traffic into the eval set continuously, or the coverage gap will silently grow.
