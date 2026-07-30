# S-1879 · The Phantom Eval Stack — When Your Agent Passes Every Eval and Still Fails in Production

Your agent "completes" 95% of tasks. Your dashboard shows green. Your team celebrates another successful quarter. Then someone actually reads the outputs and discovers that only 70% of those "completed" tasks were correct. The eval was measuring whether the agent stopped — not whether it was right. This is the phantom eval: a system that confirms your agent works by measuring something that isn't the thing you care about.

## Forces

- **Completion ≠ correctness.** Task completion rate (did the agent reach a stopping state?) is easy to measure. Correctness (did it reach the right stopping state for the right reasons?) is hard. Teams default to the easy metric and call it done.
- **Unit tests don't cascade.** Standard testing assumes determinism and linear paths. Agents are non-deterministic with branching trajectories — one bad step corrupts everything downstream, yet a later step can "recover" the output while hiding the bad reasoning that produced it.
- **Benchmarks lie.** Every major agent benchmark (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench, SWE-bench Pro) has been shown to be trivially gameable. A 10-line Python file scores 100% on SWE-bench Verified without solving a single task.
- **LLM-as-judge shares blind spots.** An LLM judge trained on similar data as the agent it evaluates will echo the agent's mistakes — the "flawed echo chamber" problem. Self-correction only works when grounded in external feedback, not intrinsic reflection.
- **Observability ≠ evaluation.** Teams conflate "I can see what the agent did" with "I know if it was right." Traces and trajectories answer different questions than quality scores.

## The move

Build an evaluation stack that measures what actually matters — not whether the agent stopped, but whether it was right, and whether it was right for the right reasons.

**1. Instrument the trajectory, not just the output.**
Every tool call, state change, and reasoning decision becomes a testable span. A trace is re-scorable against updated rubrics without re-running the agent. LangFuse calls this the Input → Reasoning → Action → Environment → Feedback → repeat loop. The trajectory IS the artifact you're evaluating.

**2. Layer four eval dimensions simultaneously.**
Braintrust's framework for production agents evaluates four things at once:
- **Task completion rate** — did the agent finish the task?
- **Tool call accuracy** — did it select and execute the right tools?
- **Output quality** — is the final answer correct and complete?
- **Failure recovery behavior** — does it detect its own errors and recover, or loop?

A single aggregate score obscures which dimension failed. Track each independently.

**3. Separate eval from observability — they answer different questions.**
"Was the agent right?" → evaluation platforms (Braintrust, DeepEval, Patronus AI). "What did the agent do?" → observability platforms (LangSmith, Phoenix, Label Studio). These are different procurement decisions solved by different tools.

**4. Ground LLM-as-judge in external signals.**
LLM judges work for output quality scoring when anchored to verifiable ground truth — retrieved documents, database state, or structured rubrics. They fail for trajectory auditing (judging the reasoning path) because they share the agent's blind spots. Use large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification; use small distilled judges (Luna-2 3B-8B, Patronus Lynx 8B) for high-throughput inline checks — these achieve 97% cost reduction at 0.88-0.95 accuracy versus proprietary.

**5. Sample production traces into golden datasets.**
When production failures occur, add the trace to an evaluation dataset. This is the highest-signal data you can get — real inputs, real failure modes, real context. Teams sampling 10% of production outputs for human review (25% for client-facing workflows) catch the silent failures that offline benchmarks miss.

**6. Test against your distribution, not a standard benchmark.**
The Berkeley RDI BenchJack research (April 2026) proved that every major benchmark can be gamed. Build evals from your production traces, user feedback, and adversarial test cases. Generic benchmarks answer "is the agent capable?" not "is this agent working for my use case?"

**7. Set soft thresholds, not hard pass/fails.**
Agents are non-deterministic. A 90% pass rate across 10 runs is normal — set CI/CD thresholds accordingly rather than expecting 100%. Track trending: if quality drops 3% week-over-week, flag for investigation regardless of absolute score.

## Evidence

- **Engineering blog (Vindler):** "Their AI agent was 'completing' tasks at a 95% success rate. When they properly evaluated the outputs, they found that only 70% of those 'completed' tasks were actually correct." — [Agent Evaluation at Scale: Lessons from 2025's Production Failures](https://vindler.solutions/blog/agent-evaluation-at-scale), December 2025

- **HN discussion (colinfly):** "I tried to evaluate an AI agent using a benchmark-style approach. It failed in ways I didn't expect. Instead of model quality issues, the failures were in my evaluation methodology — the eval itself was the problem." — [What broke when I tried to evaluate an AI agent in production](https://news.ycombinator.com/item?id=47416033), Hacker News, 4 months ago

- **Academic research (UC Berkeley RDI):** BenchJack automated exploit agent achieved 100% on SWE-bench Verified (pytest hook injection), 100% on WebArena (config file leak + file:// access), 100% on Terminal-Bench (binary wrapper trojanization), and 73-100% across all 8 major benchmarks — without a single LLM call in most cases. — [How We Broke Top AI Agent Benchmarks](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/), Wang et al., April 2026

- **Engineering guide (Label Studio):** "The eval lie causes silent failures. Correct final outputs often mask broken reasoning chains and hallucinated tool calls." — [How to evaluate AI agents in production](https://labelstud.io/blog/how-to-evaluate-ai-agents-in-production/), March 2026

- **Framework docs (Braintrust):** Agent evaluation tracks four dimensions: task completion rate, tool call accuracy, output quality, and failure recovery behaviour. Standard LLM eval scores one prompt-response pair; agent eval examines path AND outcome. — [AI Agent Evaluation: A Practical Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework), February 2026

- **Industry survey (LangChain State of AI Agents 2026):** 57% of organizations have agents in production; only 52% have proper evaluation systems. Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring rather than model capability gaps.

- **Research survey (arxiv 2507.21504):** Systematic taxonomy of agent evaluation covering interaction modes (static vs dynamic), evaluation data types, and dimension frameworks — finding the field is "fragmented" and lacks standardized approaches for real-world deployment assessment.

- **Framework guide (AgentModeAI):** The four credible eval platforms (DeepEval, Braintrust, LangSmith, Patronus) fit four distinct deployment shapes. "Picking on a generic feature matrix produces the wrong answer for most enterprises." — [Agent Eval Frameworks 2026](https://agentmodeai.com/agent-eval-frameworks-deepeval-braintrust-langsmith-patronus/), 2026

## Gotchas

- **Measuring completion rate as a proxy for correctness** — the most common mistake. If your eval only checks whether the agent stopped, you're not evaluating quality.
- **Running offline benchmarks and trusting the leaderboard** — Berkeley proved all major benchmarks are gameable. Use benchmarks to sanity-check capability, not to validate production fitness.
- **LLM-as-judge without external grounding** — judges that score trajectory reasoning share the agent's blind spots. Ground scores in verifiable artifacts (documents, database state, structured rubrics).
- **Eval drift** — when you update agent behavior without updating your eval rubrics, old evals become meaningless. Vindler: "most eval cases are added without thought and not maintained when agent behaviour updates."
- **Hard pass/fail CI gates on non-deterministic agents** — a single run doesn't represent agent quality. Aggregate across multiple runs and track trends, not binary thresholds.
