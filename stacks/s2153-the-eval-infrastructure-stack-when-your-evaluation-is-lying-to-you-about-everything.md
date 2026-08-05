# S-2153 · The Eval Infrastructure Stack — When Your Evaluation Is Lying to You About Everything

You built the eval suite. It passes. You shipped. Three weeks later a production incident reveals the agent has been failing silently on 23% of requests — the same 23% it always failed on, just now with more users. The eval suite didn't catch it because the golden dataset was frozen at snapshot day, and the product has been moving underneath it ever since. This is the eval staleness trap: the most dangerous failure mode in agentic systems, because it looks like success.

## Forces

- **Golden datasets grade the product as it was, not as it runs.** Curating a labeled set is expensive, so teams reuse it. But prompts evolve, tools change, models swap. The dataset drifts from reality silently — every green eval is real confidence being laundered.
- **Outcome scoring hides trajectory failure.** An agent can reach the right answer through a catastrophically wrong path (tool calls it shouldn't have made, cost it shouldn't have incurred, a race condition it lucked into avoiding). Outcome pass/fail misses this.
- **LLM-as-judge is only as good as its calibration.** An uncalibrated judge creates false confidence: scores cluster at 4/5 with no variance, or judges have position bias toward later options. Teams ship "85% quality" and users get 60%.
- **Eval runs are cheap; dataset maintenance is expensive.** Building the harness takes a day. Keeping the dataset representative takes forever. Most teams underestimate the second part and abandon the first.

## The Move

The move is a two-track eval system: a frozen golden dataset for regression detection (pass/fail gates in CI) paired with a live trace pipeline that continuously samples production runs and surfaces behavioral drift. You never trust one track alone.

### Concrete implementation

- **Build the golden dataset from production traces, not thought experiments.** Mine actual agent runs. Find the hard cases — the ones that took 20 tool calls, the ones that failed, the ones with weird edge inputs. Label those. Diana Pfeil's playbook: write down what your users will actually ask, paired with what a great response looks like. "What would make a user say 'that was exactly right'?" This forces ground-truth clarity before writing a single line of agent code.
- **Grade at two levels: trajectory and outcome.** Trajectory metrics catch the path being wrong even when the answer is right. Key trajectory signals: tool-call sequence match (did it use the expected tools in the expected order?), step count deviation (is it taking 10x more steps than a good run?), error recovery path (did it recover from failures correctly?). Outcome metrics catch whether the final answer is correct, complete, and grounded.
- **Calibrate LLM judges before trusting them.** Hamel Husain's critique shadowing technique: have the LLM judge output its reasoning before giving a score. A domain expert reads the reasoning and corrects it. Do this for 20-50 cases before running at scale. Without this, position bias and clustering at scale points will silently corrupt your signal. The Datadog blog notes that LLM-as-judge success "hinges on the quality of the prompt, model, and complexity of the task" — not on the task being simple.
- **Use production traces as the living complement.** Per Tessary's analysis: traces carry the span graph around a failing call — the messages, tool outputs, and turns that led there. Golden datasets grade the frozen product; traces grade the running one. Route production failures back into the golden dataset: when a run fails in a way that wasn't in your eval set, add it. This is the update loop that keeps the eval system honest.
- **Run regression gates in CI, not manually.** Every code change to the agent should trigger the full golden dataset run. LangSmith, Braintrust, and custom harnesses all support this. The TribeAI Claude Evals framework implements this as a one-command CI gate with a 50-case golden dataset and model-comparison reporting.
- **Track cost-per-task in the eval, not just accuracy.** An agent that scores 95% accuracy at 3x the tool calls and 5x the cost of the baseline is not better. The AWS Bedrock eval library surfaces cost alongside quality metrics specifically for this reason.

## Evidence

- **Anthropic engineering post:** Their eval design guide establishes the task/trial/metric framework and explicitly notes that "agents are non-deterministic by design, so you can't unit test every possible action sequence" — necessitating statistical evaluation over multiple trials, not single-run pass/fail. They also document that privacy controls limiting engineer access to user interactions mean eval data must be constructed deliberately rather than sampled directly from production.
- **AWS Bedrock eval framework (Feb 2026):** Documents that traditional LLM eval methods "treat agent systems as black boxes, evaluating only final outcomes and failing to determine why agents fail, pinpoint root causes, or assess emergent behaviors across multi-step reasoning." Their framework adds trajectory-level metrics to outcome metrics, specifically tracking tool-call accuracy, step efficiency, and self-correction quality.
- **Tessary blog (Akhil Varma, Jun 2026):** Synthesizes the golden-dataset vs. production-trace distinction clearly: datasets grade "the product as it was when someone curated it," traces grade "the product as it runs now." Documents that calibration against a labeled set is required even for trace-based evaluation — without it, the system grades itself against itself.
- **Hamel Husain's LLM-as-judge guide:** Documents that teams fail at evaluation by creating too many metrics, using uncalibrated 1-5 scales, ignoring domain experts, and using metrics that don't reflect user value. Critique shadowing (having the LLM explain before scoring) is the mitigation.
- **GitHub — TribeAI/claude-evals:** A production eval framework implementing Anthropic's patterns with a 50-case golden dataset, native SDK hooks, and CI integration. Their README notes the harness is "an offline eval, not a production observability tool" — a deliberate scope distinction that maps to the frozen/live two-track model.

## Gotchas

- **A passing eval does not mean a working agent.** It means the agent passed the eval. If the eval dataset doesn't represent production, the pass is meaningless. This is not a hypothetical: the Tessary post documents an Anthropic postmortem where eval data "didn't capture the degradation" because it ran on other data than what production actually looked like.
- **Scoring variance requires multiple trials.** Agents are non-deterministic. A single trial pass/fail is noise. Run each task 3-5 times and report the distribution. If scores are bimodal (some runs 100%, some 0%), something in the agent's logic is path-dependent on initialization or model sampling.
- **LLM judges exhibit position bias.** They systematically favor responses appearing later in the context or scoring higher on superficial qualities (longer answers, more confident tone). Calibrate by checking whether your judge's preferences correlate with actual user satisfaction, not just with other judges.
- **Eval maintenance is a product problem, not an engineering problem.** Golden datasets go stale. Someone owns curating new cases from production failures, removing deprecated scenarios, and rebalancing difficulty. If no one is accountable for this, the eval system degrades within weeks and becomes actively misleading.
