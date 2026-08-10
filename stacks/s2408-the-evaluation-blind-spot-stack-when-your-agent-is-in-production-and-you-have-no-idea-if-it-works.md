# S-2408 · The Evaluation Blind Spot — When Your Agent Is in Production and You Have No Idea If It Works

Your customer-support agent has been live for three weeks. You merged it because it worked in staging. You have no test suite, no regression suite, no production monitoring. You know it returns responses. You do not know if it actually solves problems, loops infinitely on edge cases, or degrades in quality on Tuesday afternoons. You are flying blind.

Agents are non-deterministic by nature, multi-step in execution, and context-dependent in quality. Traditional software testing — assertEquals, unit tests, regression suites — was built for deterministic code. It does not transfer.

## Forces

- **Agent outputs are probabilistic; traditional assertions fail.** You cannot write `assert agent(input) == expected_output` because the same input produces different outputs. You must assert that the agent achieved the goal within acceptable quality bounds, not that it produced a specific string.
- **The final answer is not the whole story.** A correct-looking answer from a broken reasoning chain is dangerous — the agent got there for the wrong reasons and will fail on the next variation. Trajectory quality matters independently of outcome quality.
- **Research benchmarks do not reflect production reality.** Tasks on SWE-bench, WebArena, and OSWorld are retrospectively curated with well-specified requirements. Production has implicit constraints, undeclared domain expertise, and evolving stakeholder standards. A benchmark score of 80% does not mean 80% of your production tasks succeed.
- **The scaffold matters as much as the model.** Multiple studies show the same model performs differently across agent frameworks due to planning strategies, tool integration, and error recovery design. Optimizing the model while ignoring the scaffolding is incomplete.
- **Evaluation cost is real and often underestimated.** Running a full eval suite across 94 tasks with multiple models can cost $500–2,000/month. Teams underinvest in eval infrastructure and over-invest in capability work.

## The Move

Evaluate agents across four independent dimensions, with layered evaluation methods (the "Swiss Cheese Model" from safety engineering — no single layer catches every failure):

**1. Trajectory quality — was the path correct?**
- Measure whether the agent's reasoning chain is sound, not just the final answer
- Tool-call sequence accuracy: did it call the right tools in the right order with the right arguments?
- Step count and loop detection: excessive steps or repeated tool calls signal broken reasoning
- Use span-level tracing to inspect individual steps independently

**2. Task completion — did it achieve the goal?**
- Binary or graded outcome: did the user's original goal get met?
- For customer support: was the ticket resolved? Did satisfaction improve?
- For code agents: did the PR pass review and deploy without incidents?
- Ground in production signals where possible, not just synthetic test cases

**3. Operational metrics — did it do so acceptably?**
- Latency: did it complete within the user's expectation window?
- Cost per task: tokens consumed, API calls made
- Error rate: tool failures, API timeouts, graceful degradation

**4. Safety and guardrails — did it avoid harm?**
- Output groundedness: does the response match the retrieved evidence?
- Refusal correctness: does it appropriately refuse harmful requests?
- Hallucination detection: factual consistency with known sources

**Stack the evaluation layers:**
- Automated evals for fast iteration (CI/CD gates, pre-deploy checks)
- Production monitoring for ground truth (live metrics, user feedback)
- Periodic human review for calibration (sample transcripts, human annotation)

## Evidence

- **Research paper:** AlphaEval (Apr 2026) — a production-grounded benchmark of 94 tasks from 7 companies across 6 occupational domains. Best agent scored 64.41/100 on real production tasks. Key finding: "agent scaffolding profoundly impacts performance" and existing research benchmarks fail to capture production-specific failure modes. — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162)
- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" (Jan 2026) — outlines 4 eval paradigms (sandbox testing, diff testing, automated grading, human studies) and describes the Swiss Cheese Model: "With multiple methods combined, failures that slip through one layer are caught by another." — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering blog:** Langfuse's "AI agent evaluation" guide — 4 evaluation dimensions: trajectory, tool use, task completion, and multi-turn quality. Argues evaluating only the final answer "misses most of what can go wrong." — [Langfuse](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **HN discussion:** Thread on "Agentic evals or LLM as a judge?" (Aug 2025) — practitioners debate tradeoffs; one comment: "Did we just give up on evaluations? Over, and over again my experience building production AI tools has been that evaluations are vital for improving performance." — [Hacker News](https://news.ycombinator.com/item?id=48144995)
- **HN discussion:** "Principles for production AI agents" (Jul 2025, 128 points) — community discussion on evaluation, observability, and safe deployment practices. — [Hacker News](https://news.ycombinator.com/item?id=44712315)

## Tools

- **DeepEval** (confident-ai) — open-source, 50+ research-backed metrics, pytest-style unit testing for agents, CI/CD integration, trace-based evaluation. v4.0 (May 2025) introduced eval harness for coding agents. — [GitHub / Docs](https://deepeval.com/docs/getting-started-agents)
- **TruLens** (Snowflake, MIT) — OpenTelemetry-native tracing, LLM judges with explanations, version comparison, per-step scoring. — [GitHub](https://github.com/truera/trulens) | [trulens.org](https://www.trulens.org)
- **AgentBench** — cross-environment benchmark for agent systems (OS, DB, KG, Knowledge, etc.)
- **AlphaEval** — production-grounded benchmark with requirement-to-benchmark construction framework for translating production requirements into formal evaluation tasks. — [GitHub](https://github.com/GAIR-NLP/AlphaEval)
- **G-eval** — LLM-based evaluation using chain-of-thought to generate evaluation criteria; targets 0.80+ Spearman correlation with human judgment
- **RAGAS** — retrieval-augmented generation evaluation; synthetic test generation using knowledge graphs
- **Human-in-the-loop workflows** (Confident AI) — three core loops: metric alignment (tuning criteria to match human judgment), failure review (surfacing what automated metrics miss), and evaluation dataset curation (promoting high-value cases into durable test coverage)

## Gotchas

- **Research benchmarks ≠ production performance.** AlphaEval found production-grounded evaluation reveals capability gaps invisible to SWE-bench, WebArena, and OSWorld — not merely harder tasks, but fundamentally different task structures. Do not assume a benchmark score predicts production reliability.
- **LLM-as-judge has known failure modes.** HN practitioners report that LLMs are not good critics of their own outputs; evidence for "LLM as critic" in production is mixed. Calibrate judges against human judgment regularly and do not use the same model as both generator and judge.
- **Vague rubrics produce meaningless scores.** Every evaluation criterion must be specific enough that two human annotators would agree. "Did the agent do a good job?" is not a rubric; "Did the agent use the correct tool within 3 steps, produce a grounded response, and achieve the stated goal?" is.
- **Eval without regression is window dressing.** Running evals before launch but stopping post-launch leads to quality degradation within 30–60 days (per Deloitte's 2025 enterprise AI analysis). Evaluation must be continuous, not a pre-launch checklist.
- **Too few test cases gives false confidence.** A golden dataset of 10 cases is not a test suite — it is a spot check. Build coverage across your actual task distribution, including edge cases and failure modes surfaced by production monitoring.
