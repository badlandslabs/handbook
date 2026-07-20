# S-1421 · The Agent Evaluation Stack — When Your Success Metric Is a Lie

Your agent scores 94% on your internal benchmark. It ships. Three weeks later, customers are filing complaints about confidently wrong answers, silent failures that leave data orphaned, and a multi-step workflow that works until the 3rd step and then does nothing. The benchmark passed. The production system failed. You were evaluating the wrong thing.

## Forces

- **Classical metrics don't measure agents.** BLEU and ROUGE score static text. Agents plan, call tools, maintain state, and recover from errors across multiple turns. A task-completion rate is meaningless if the completion mode is "fails silently and reports success anyway" (InfoQ, 2026)
- **The benchmark is always cleaner than production.** Demo inputs, curated test cases, and synthetic users all have one thing in common: they don't include Unicode names, null values, concurrent requests, or a user who says "as I mentioned before" (HN Ask, "How are you testing AI agents before shipping to production?", July 2025)
- **Evaluation has to cover the system, not just the model.** Token efficiency, tool reliability, latency, and idempotency under interruption all determine enterprise viability — none of them appear in a standard agent benchmark (arXiv:2507.21504, Mohammadi et al., July 2025)
- **40%+ of AI agent projects will fail by 2027** (Gartner, cited in HN discussion on AI agent failure modes, July 2025). Most fail not because the model is wrong, but because the evaluation pipeline was incomplete

## The Move

**Evaluate the system as a system, not the model as a model.** The move has four components:

- **Five evaluation pillars, not one.** Task success (did it do the right thing?), behavioral quality (how did it handle the unexpected?), recovery behavior (how did it fail when it failed?), operational efficiency (latency, cost, token usage), and safety/compliance (prompt injection defense, PII handling, policy adherence) — all measured separately with different tools (InfoQ, 2026)
- **Hybrid evaluation: automate the repeatable, human-review the consequential.** LLM-as-a-judge for scaling fast feedback (80% agreement with human evaluators, matching human-to-human consistency per labelyourdata.com 2026). Human judgment for tone, trust signals, and contextual correctness. Neither replaces the other
- **Test the workflow as a stateful process, not a stateless function.** If you can't kill an agent mid-task and restart it without corrupting your database, it is not production-ready regardless of prompt quality. Test for idempotency, cascade failure, and orphan data — not just accuracy (HN thread, July 2025)
- **Validate your judges.** LLM-as-a-judge is easy to express but hard to get right. It needs calibration against annotated ground truth, adaptation to your domain (agreement drops 10–15% in specialized fields), and version pinning so API updates don't silently shift your scoring threshold. Position bias alone causes ~40% GPT-4 inconsistency on two-option comparisons (labelyourdata.com, 2026)

## Evidence

- **arXiv survey (July 2025):** Two-dimensional taxonomy proposed — evaluation objectives (behavior, capability, reliability, safety) and evaluation process (interaction modes, benchmarks, metrics). Key insight: "Evaluating LLM agents is more complex than evaluating LLMs in isolation. Unlike LLMs, which are primarily assessed for text generation, LLM agents operate in dynamic, interactive environments" — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)
- **HN Ask HN thread (July 2025):** 7 failure modes identified in agent testing: hallucination under unexpected inputs, edge case collapse (null/Unicode/concurrent), prompt injection, context limit surprises, tool call reliability, output validation gaps, and cascade failure. Key quote: "We test agents like they are stateless functions, when in reality they are long-running stateful processes" — [HN item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **InfoQ article (March 2026):** Five evaluation pillars documented with tooling guidance. "An agent that works perfectly in a sandbox but silently misreports a failed refund in production hasn't passed any evaluation that counts." Hybrid pipelines combining LLM-as-judge with human review are described as non-negotiable — [InfoQ Evaluating AI Agents](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **HN discussion on production AI agents (HN item?id=44712315):** Debate on LLM-as-judge credibility. Found that eval suite owners note "no empirical evidence exists that LLM as critic actually works" without foundational human evals first. DSPy and prompt optimization cited as the adaptation layer — [HN item?id=44712315](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **LLM judges exhibit systematic biases that invalidate naive scoring.** Position bias (evaluate both A-B and B-A orderings), verbosity bias (~15% score inflation favoring longer responses), self-enhancement bias (5–7% boost when judge is same model family), and authority bias (favoring rule-breaking when context feels justified). Fix these in the rubric, not in the prompt
- **Task success rate hides the failure mode.** An agent can "complete" a task by failing silently — reporting success while sending a corrupted email, writing wrong data to a database, or dropping a step in a multi-step workflow. Measure success by verifying downstream state, not by inspecting the agent's final output
- **Cascade failures are the most expensive failure mode and the least tested.** Step repetition (15.7% of failures) and unaware termination (12.4%) together represent 28.1% of agent failures. Both cause duplicate side effects (double emails, double charges) and orphaned data. Test by interrupting the agent at every step and verifying the system state is recoverable
- **Eval version pinning is not optional.** When you pin a model as a judge, pin the exact version. API updates (even minor ones) shift judge behavior and invalidate historical comparisons. Run calibration checks quarterly against your annotated ground truth set
