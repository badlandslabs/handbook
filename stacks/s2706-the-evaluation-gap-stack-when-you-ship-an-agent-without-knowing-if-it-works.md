# S-2706 · The Evaluation Gap Stack — When You Ship an Agent Without Knowing If It Works

You have traces. You have cost dashboards. You have LangSmith or AgentShield hooked up. But you don't actually know if your agent is working — because observability and evaluation are different things, and 37% of production teams have the first without the second.

## Forces

- **Observability ≠ evaluation.** Tracing shows you what happened; it doesn't tell you whether it was right. Most teams conflate the two and end up with beautiful dashboards over a quality blind spot.
- **The eval gap is massive and known.** 89% of production agent teams run observability but only 52% run evals — a 37-point gap where quality silently decays (LangChain State of Agent Engineering Survey, 2026).
- **Single-turn accuracy metrics don't transfer.** BLEU and ROUGE scores were designed for deterministic translation tasks. Agents produce multi-step trajectories where the failure mode is a sensible intermediate step that leads to the wrong final answer.
- **Task completion and answer quality are different signals.** An agent can produce a well-written, confident, completely wrong response. Scoring the text misses the actual failure: wrong tool called, right tool with wrong arguments, or a loop that never converged.
- **Human review doesn't scale.** Sampling 100% of agent runs for human review is economically impossible at production scale, but sampling nothing means you have no ground truth for quality drift.

## The Move

Build a layered evaluation system that combines offline benchmarking, LLM-as-judge scoring, trajectory analysis, and targeted human review — with evaluation gates baked into your CI/CD pipeline, not bolted on as an afterthought.

**The four evaluation dimensions (per Langfuse's production guide):**

- **Trajectory** — Did the agent take a sensible path? Track step count, unnecessary tool calls, loops/retries, required steps present, correct ordering. Score at the trace root, not per step.
- **Tool use** — Did it call the right tools correctly? Check argument validity, tool error rate, recovery after failures. This lives on tool-call observations, not on the final output.
- **Task completion** — Did the user get what they asked for? End-to-end goal achievement, resolution rate. This is the only dimension that maps to user value.
- **Multi-turn / session quality** — Does quality hold across conversation turns? A chatbot that produces five individually reasonable turns that collectively fail to resolve the issue has a 0% task completion rate even if each turn scores high.

**The CI/CD tiered evaluation pattern (per RockB's agent CI/CD guide):**

- **Tier 1 — PR tier:** Fast checks (minutes, sub-$1) on every pull request. Prompt changes, tool definition changes. Must pass before merge. Covers regressions on critical paths.
- **Tier 2 — Nightly tier:** Broader scenario coverage, runs hourly or nightly against the full golden dataset. Moderate cost. Catches quality drift before it reaches users.
- **Tier 3 — Production tier:** Sampled live traffic scored automatically. Triggers alerts when quality drops below threshold. Human review on a curated sample.

**LLM-as-judge with calibration:**

- Use a separate, capable model (e.g., GPT-4o or Claude Sonnet) to score agent outputs against a rubric. This scales beyond human review but requires calibration — judges are biased toward length and confidence.
- Score at three critical boundaries: before user-facing output, before irreversible tool execution, and on writes to persistent memory. Don't judge every intermediate reasoning step — cost compounds fast.
- Self-correction only reliably helps when grounded in external feedback (unit test results, retrieval verification, tool-output comparison). Groundless self-correction loops add cost without improving outcomes.

**Production sampling rates (per ztabs and thinking.inc guides):**

- Automated quality scoring on 5–10% of live interactions daily
- Weekly human review of 50–100 sampled conversations with a structured rubric (8 quality dimensions, 1–5 scale)
- Daily review of all escalated or negatively-rated interactions
- Flag any agent showing >3% quality decline week-over-week for investigation

## Evidence

- **ICML 2026 MAP study (first systematic study of production agents, 20 case studies + 86 deployed systems):** 74% of deployed agent systems rely primarily on human evaluation — meaning only 26% have moved beyond manual review to automated evaluation. This aligns with the 52% eval figure but suggests the subset doing rigorous automated eval is much smaller.
- **LangChain State of Agent Engineering Survey 2026:** 89% of production agent teams run observability; only 52% run evals. The 37-point gap is where quality silently decays between deploys.
- **RockB Agent CI/CD Guide 2026:** A prompt change that passes every conventional test can tank agent task completion by 20 points in production because the model re-ranked tool priorities or changed how it interprets ambiguous instructions — failures invisible to static checks.
- **Langfuse engineering guide (langfuse.com/resources/engineering/ai-agent-evaluation):** Tool-argument checks belong on tool-call observations; task completion belongs on the trace root. Scoring intermediate steps independently misses the trajectory-level failure modes that matter most.
- **Confident AI blog (April 2026):** Agents fail in four characteristic ways: wrong tools or arguments, retry/planning loops that never converge, false task completion (agent reports success without doing the work), and hallucinated tool results. Each requires different evaluation logic.
- **AgentShield HN discussion (HN Ask HN "monitoring agents in production", 5 months ago):** DataTalks agent wiped a database; Replit agent deleted data during a code freeze. Both had execution tracing — neither had evaluation gates that would have caught the dangerous action before it ran.

## Gotchas

- **Don't confuse traces with evals.** A trace showing "tool X called at step 3" is observability. A score of 0.85 for "correct tool selected" is an eval. You need both, but they answer different questions.
- **Golden datasets go stale.** Your initial test cases reflect your understanding of the task when you built the agent. As real users encounter edge cases, those cases need to become test cases. If your golden dataset is 6 months old, you're testing yesterday's agent against today's traffic.
- **LLM-as-judge has position bias.** Judges favor responses listed first in a comparison. Use pairwise comparison with position randomization, or use absolute scoring against a rubric rather than relative ranking.
- **Step limits without evaluation are theater.** The MAP study found 68% of production agents execute at most 10 steps before human intervention — a useful safety bound, but it says nothing about whether the first 10 steps were correct. Combine step limits with trajectory scoring.
- **Cost-per-task tracking is an eval signal, not just a finance metric.** If cost-per-task spikes 40% without a corresponding increase in task complexity, something is wrong — likely a retry loop, a converging planning cycle, or a tool that's repeatedly failing and being retried.
