# S-2916 · The Completion Rate Illusion Stack: When Your Agent Says "Done" But Isn't

Your agent reports 95% task completion. Customer support tickets say 30% of those completions were wrong. The agent confidently declared success, produced a result, and moved on — and nobody caught it until users complained. This is the completion rate illusion: measuring whether an agent did something, not whether it did something correctly. It's the single most expensive gap in agentic systems today.

## Forces

- **Completion ≠ correctness.** Agents self-report. An agent can declare "task complete" while producing wrong outputs, wrong database writes, or wrong API calls. The completion metric rewards activity, not accuracy.
- **Single-run evaluation is a lie.** Agents achieving 60% success on a single run drop to 25% across eight consecutive runs. A one-shot eval tells you nothing about reliability under variance.
- **Trajectory and outcome are different properties.** The final output can look fine while the reasoning chain took six wrong turns. Measuring only the destination misses the most actionable failure signal.
- **Labeling is expensive, skipping it is more expensive.** Manual evaluation of agent traces is slow. Teams skip it. The $47K prompt injection incident in January 2026 happened at a company whose agent had never been adversarially tested.

## The move

Build a three-layer evaluation harness: automated regression suite, trajectory inspection, and human spot-check gate. Run every agent change through all three before shipping.

- **Run ≥5 trials per task.** Model output variance is real. A single run is one sample from a distribution. Claude Code's own engineering team runs the [Agent SDK](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) against multiple trials precisely because one run tells you about one draw. Five is a minimum for reliability signal; eight gives you confidence intervals.
- **Distinguish trajectory metrics from outcome metrics.** Trajectory metrics score intermediate steps — was the right tool called, in the right order, with the right inputs? Outcome metrics score the final result. Both are required. Outcome alone hides process failures that compound into wrong answers.
- **Grade intermediate steps with typed assertions.** Instead of evaluating the whole trace as a black box, write assertions on individual steps: `assert tool_name == "sql_query"`, `assert sql_query.contains("WHERE")`, `assert result.row_count > 0`. These catch failures that only surface as downstream errors hours later.
- **Use LLM-as-judge with correlation validation, not trust.** LLM-as-judge works for subjective quality (is the response helpful?). Multi-agent evaluators can reach near-human reliability (~0.3% deviation in code tasks vs 31% for single LLM judges). But you must validate: run your judge against 20 human-graded samples, measure Spearman correlation, and require ≥0.80 before trusting it automatically.
- **Test failure modes explicitly, not just happy paths.** The HN community's 50+ test case framework from 2025 identifies seven recurring failure modes: hallucination under unexpected inputs, edge case collapse (null values, unicode names like O'Brien or 北京), prompt injection, context limit surprises, tool call loops, wrong tool selection, and overconfidence after partial success. Each needs its own test cases.
- **Gate CI/CD on eval pass rate.** Every framework in production use (DeepEval, Confident AI with 600K+ daily evals across BCG, AstraZeneca, AXA; Lucidic; Langfuse) treats evals as a CI gate, not a one-time audit. The eval suite runs on every commit. A regression in pass rate blocks the deploy.

## Evidence

- **Company engineering post (Anthropic):** Agents achieving 60% success on a single run drop to 25% across eight consecutive runs — a 58% reliability collapse. Anthropic's own eval framework for Claude Code and the Agent SDK runs multi-trial evaluation as a first-class requirement. — [Demystifying Evals for AI Agents — Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Consulting firm case study (Vindler Solutions):** An agent reporting 95% task completion was found to produce incorrect results 30% of the time under proper evaluation. The gap was invisible without trajectory-level inspection. The cost was weeks of degraded data quality and customer complaints. — [Agent Evaluation at Scale: Lessons from 2025's Production Failures](https://vindler.solutions/blog/agent-evaluation-at-scale)
- **Academic survey (arXiv 2508.02994):** Multi-agent evaluators for code tasks differ from human majority votes by ~0.3%, compared to 31% disagreement for single LLM judges. The agent-as-judge paradigm (extending LLM-as-judge into multi-step reasoning) is most effective when the journey matters as much as the destination. — [When AIs Judge AIs: The Rise of Agent-as-a-Judge Evaluation for LLMs](https://arxiv.org/html/2508.02994v1)
- **Startup launch (YC W25, HN):** Confident AI's DeepEval runs 600K+ evaluations daily for enterprise customers including BCG, AstraZeneca, AXA, and Capgemini. Founded Feb 2025 on the thesis that LLM evaluation belongs in CI/CD, not in notebooks. — [Launch HN: Confident AI (YC W25)](https://news.ycombinator.com/item?id=43116633)
- **Community HN thread:** A practitioner who ran reliability audits on production agents shared 50+ test cases across 7 identified failure categories (hallucination, edge case collapse, prompt injection, context limits, tool loops, wrong tool selection, overconfidence). Garnered 100+ responses from teams sharing their own eval stacks. — [Ask HN: How are you testing AI agents before shipping to production?](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Believing the agent's self-report.** Never use the agent's own completion signal as ground truth. Build an independent grader that evaluates output correctness outside the agent's reasoning loop.
- **Evaluating only the final output.** A wrong answer arrived at through six correct steps is rarer than a wrong answer arrived at through one wrong step. Trajectory scoring catches the more common and more fixable failure mode.
- **Running evals once and calling it done.** Eval suites drift as agents change, as underlying models update, and as production data shifts. Treat eval results as a time series, not a checkpoint. A pass rate that was 94% six months ago and is now 87% is a regression — even if no user has complained yet.
