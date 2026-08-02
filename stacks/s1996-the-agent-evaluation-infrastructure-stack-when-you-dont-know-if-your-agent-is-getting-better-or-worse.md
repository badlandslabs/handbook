# S-1996 · The Agent Evaluation Infrastructure Stack — When You Don't Know If Your Agent Is Getting Better or Worse

*When your AI agent ships on Monday and by Friday you're flying blind — no idea whether task success rate is 95% or 40%, no visibility into why the agent chose wrong, no way to catch the silent regressions that happen every time someone touches a prompt. You need evaluation infrastructure that tells you whether the agent is actually working, before your users tell you.*

## Forces

- **Agents are non-deterministic.** The same input produces different outputs. Traditional exact-match tests are useless — an agent that completes the task correctly but formats the output differently scores 0% on exact match and 100% on task completion. Your CI pipeline can't assert on strings.
- **Silent failures outnumber loud ones.** Agents produce fluent, confident responses even when operating on incomplete context or wrong tool outputs. The failure is invisible — no error code, no exception, just a wrong answer that sounds right.
- **Benchmarks lie about production readiness.** AgentBench, WebArena, and GAIA scores don't predict whether your agent handles your users' actual input distribution. A model scoring near-top on WebArena can still fail at a two-step task your users hit 40% of the time.
- **Everything changes agent behavior.** Prompts, model versions, tool schemas, retrieval config, guardrails — any single line in any of these causes a silent regression with no stack trace. Traditional CI passes, production breaks.
- **Human review doesn't scale.** At 1,000 agent runs/day, manually reviewing every output is a full-time job. But releasing without any human signal means shipping blind.

## The Move

Build a layered evaluation system that runs at every stage of the agent lifecycle — pre-deploy, shadow, and production — with the right eval type at every gate.

### 1. Define behavioral success criteria first, not metrics

Start with the question: *what does a successful interaction look like from the user's perspective?* Break it into 3-5 dimensions specific to your agent. Standard generic metrics (BLEU, ROUGE, exact match) measure string overlap, not behavior. They will mislead you.

Common evaluation dimensions that actually matter:
- **Task completion** — did the agent accomplish the user's goal end-to-end?
- **Tool-use correctness** — did the agent call the right tools with valid arguments?
- **Safety/compliance** — did the agent avoid forbidden actions, hallucinations, or policy violations?
- **Cost efficiency** — did it use the minimum tokens/steps to get there?
- **Latency** — did it respond within acceptable time bounds?

*Source: LangChain Agent Development Lifecycle — "The order is intentional: testing should start before an agent reaches production, not after" — [langchain.com](https://www.langchain.com/blog/the-agent-development-lifecycle)*

### 2. Build a golden eval dataset from real production failures

The highest-quality eval data comes from real failures, not synthetic scenarios. Route production failures into a dataset. When an agent makes a mistake in production, document the full trace — input, agent reasoning, tool calls, final output, what the correct behavior should have been. This becomes a regression test.

This closes the feedback loop: production failures → datasets → regression tests → future failures of the same type get caught pre-deploy.

*Source: Arthur — "Production failures become datasets, and those datasets become regression tests that ensure the same issue never silently reappears" — [arthur.ai](https://www.arthur.ai/column/evaluating-ai-agents-in-production)*

### 3. Use LLM-as-judge with known limitations, not blind faith

LLM-as-judge is the dominant pattern for scoring agent outputs at scale. A separate LLM (often Claude or GPT-4) evaluates whether the agent's behavior met criteria and produces a score plus written justification. It scales without human reviewers.

Know the failure modes: **position bias** (judge prefers first/last options), **length bias** (judge favors longer outputs), and **self-preference** (a judge trained on Claude outputs may favor Claude agents). Mitigate by using a different model family as judge than as agent, running with balanced prompt ordering, and spot-checking judge verdicts against human ground truth regularly.

*Source: MLflow — "Traditional metrics like BLEU and ROUGE measure token overlap but miss whether a response hallucinated or violated tone guidelines. Human reviewers catch these issues but can only evaluate a limited number of outputs per day" — [mlflow.org](https://mlflow.org/llm-as-a-judge)*

### 4. Wire evals into CI/CD as gates, not suggestions

Traditional CI passes all tests and gives you a green build. Agent CI must add a behavioral correctness layer. The pattern that works: define a minimum eval score threshold per dimension, make it a merge-blocking gate, and fail the build if the threshold drops.

A 6-stage agent-native CI pipeline works in practice:
1. Code & prompt lint (schema validation, tool definitions)
2. Unit tests (deterministic logic only)
3. **Eval dataset regression** (golden set, assert on pass rate — not pass/fail, because agents are stochastic)
4. Shadow mode evaluation (run new version in parallel, compare eval scores)
5. Canary rollout (5% traffic, monitor cost + quality metrics)
6. Full rollout + continuous eval

*Source: LangChain State of Agent Engineering 2026 — "57% of organizations now have agents in production — but quality remains the top barrier, cited by 32% of respondents" — cited in [replyant.com](https://replyant.com/lab/agent-evals-cicd)*

*Source: Zylos Research — "A single-line prompt change can pass all tests yet cause silent production breakage (e.g., agent truncating API responses mid-sentence)" — [zylos.ai](https://zylos.ai/en/research/2026-05-17-agent-native-cicd-deployment-patterns)*

### 5. Instrument full execution traces for debugging

When an eval fails, you need the full trace — not just the final output. Record step-by-step: every LLM call, every tool invocation with arguments and results, every decision point, every intermediate state. This is the difference between "the agent failed" and "the agent failed because tool X returned an unexpected schema and it proceeded anyway."

Tools like LangSmith, AgentShield, and Lucidic provide execution tracing with 2-line integration into LangChain, CrewAI, and OpenAI Agents SDK. The key is capturing the trace atomically so you can replay failure cases.

*Source: Ask HN: AgentShield founder — "No visibility into what the agent did step-by-step" and "Surprise LLM bills from untracked token usage" as top failure modes — [HN #47301395](https://news.ycombinator.com/item?id=47301395)*

*Source: Lucidic HN Launch — "We built it because debugging agents felt like debugging in the dark" — [HN #44735843](https://news.ycombinator.com/item?id=44735843)*

### 6. Handle eval failures with two patterns based on confidence

Once continuous evals run in production, what happens on failure?

- **High-confidence, low-false-positive evals** → real-time alerting. When an eval fires, notify the team immediately so they can investigate before more users are affected.
- **Earlier-stage or ambiguous evals** → queue for human-in-the-loop review. Route suspicious interactions to a human reviewer, analyze failure clusters, then fix the root cause and add to the regression set.

Both patterns close the same loop. The difference is whether you trust the eval enough to auto-act.

*Source: Arthur — "Teams with high-confidence, low-false-positive evals wire up alerts on failures. Earlier-stage teams use eval failures as a triage mechanism" — [arthur.ai](https://www.arthur.ai/column/evaluating-ai-agents-in-production)*

## Evidence

- **LangChain Blog:** The Agent Development Lifecycle describes the Build → Test → Deploy → Monitor cycle, emphasizing that testing starts before production and that learnings from monitoring inform the next build cycle. Tooling categories table covers agent frameworks, eval platforms, observability, and guardrails. — [langchain.com](https://www.langchain.com/blog/the-agent-development-lifecycle)

- **Ask HN Thread #47301395:** Practitioners describe real production failure modes: no step-by-step visibility, surprise token bills, risky outputs going undetected, no audit trail. AgentShield founder proposes execution tracing + risk detection + cost tracking + human-in-the-loop approval for high-risk actions as the minimum viable stack. — [HN](https://news.ycombinator.com/item?id=47301395)

- **Show HN: Lucidic (YC W25):** Built specifically because "debugging agents felt like debugging in the dark." One-line integration (`lai.init()`), custom metadata per step, memory snapshots, tool output capture, full execution trace replay for post-mortems. — [HN #44735843](https://news.ycombinator.com/item?id=44735843)

- **BigData Boutique Blog:** LLM evaluation in production requires a layered system — offline regression suites for known behaviors, online/shadow evaluation for real traffic, and human calibration anchors. Framework comparison: DeepEval, Ragas, Promptfoo, LangSmith, Braintrust, Phoenix, Langfuse, Opik, MLflow. Key distinction: evaluation architecture comes before framework selection. — [bigdataboutique.com](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)

- **Benchmarking Agents Review:** Agent benchmarks (WebArena, AgentBench, GAIA, SWE-bench, tau-bench, OSWorld) measure fundamentally different capabilities than LLM benchmarks. High scores on MMLU, GPQA, HumanEval do NOT predict agentic capability. Agent success requires planning, tool-use discipline, error detection, and recovery — not knowledge recall. — [benchmarkingagents.com](https://benchmarkingagents.com/agent-benchmarks/)

- **Zylos Research:** Agent-native CI/CD as a discipline: merge-blocking eval gates, shadow rollouts, prompt version rollback, progressive canary deployment patterns. "Shipping changes to an AI agent is fundamentally different from traditional software deployment. Agent behavior is shaped by prompts, model checkpoints, tool definitions, retrieval configurations, and guardrails. Any one of these can cause a silent regression with no stack trace." — [zylos.ai](https://zylos.ai/en/research/2026-05-17-agent-native-cicd-deployment-patterns)

- **Arthur:** Continuous evals → two response patterns (real-time alerting vs. human-in-the-loop triage). Production failures → eval datasets → regression tests. Production eval must cover both final outputs and full execution paths. — [arthur.ai](https://www.arthur.ai/column/evaluating-ai-agents-in-production)

- **MLflow:** LLM-as-judge implementation guide — any model can judge (OpenAI, Claude, Gemini, open-source), covers correctness, relevance, groundedness, safety, helpfulness. Failure modes documented: position bias, length bias, self-preference bias. Mitigation: cross-model judging, balanced ordering, human spot-checks. — [mlflow.org](https://mlflow.org/llm-as-a-judge)

- **Replyant:** LangChain 2026 State of Agent Engineering data: 57% orgs with agents in production, 32% cite quality as top barrier, 86% pilot failure rate from inability to measure agent effectiveness. Google's "from vibe checks to data-driven agent evaluation" codelab. — [replyant.com](https://replyant.com/lab/agent-evals-cicd)

- **Data Science Duniya (Principal ML Engineer):** "Agents are dynamic, context-dependent, and sometimes unpredictable. This means we need a completely different evaluation framework." Standard unit tests are "pretty much useless" for agents. Defines success first, tracks trajectory-level metrics, budgets for eval pipeline infra, starts with golden test cases, adds LLM-as-judge for open-ended evaluation. — [ashutoshtripathi.com](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide/)

## Gotchas

- **Don't assert on pass/fail — assert on pass rate.** Agents are stochastic. A single eval run is noisy. Run the same eval 10-20 times and assert that the pass rate exceeds your threshold (e.g., "≥ 80% of runs must score ≥ 4/5 on task completion"). A single failure proves nothing; a 30% pass rate proves everything.
- **Don't skip the full trace.** Final-output-only evaluation misses the most actionable failures: the agent got the right answer but called the wrong tool first, or the agent recovered correctly but wasted 3x the tokens getting there. Trajectory-level metrics catch these.
- **Don't use production traffic as your only eval signal.** Real user interactions are biased toward what users have tried, not what the agent should handle. Supplement with adversarial test cases, edge-case injection, and boundary-condition prompts that users haven't hit yet.
- **Don't pick an eval framework before defining your eval architecture.** DeepEval, LangSmith, Braintrust, and Phoenix are tools that slot into an architecture you design first. Teams that pick a framework first end up retrofitting their evaluation strategy around the tool's assumptions.
- **Don't deploy without a rollback trigger on eval regression.** A prompt tweak that drops your "tool-use correctness" score from 91% to 78% is a production incident waiting to happen — even if the code tests pass, even if the agent still works in demos, even if no errors are thrown.
