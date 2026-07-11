# S-932 · The Continuous Eval Loop Stack — When Your Agent Changes But Your Tests Don't

Your agent passes every eval. Your production quality is degrading anyway. The model provider shipped a silent update, your eval dataset drifted from real queries, and the guardrail you added last month now fires on benign inputs. The problem isn't that you don't evaluate — it's that your eval loop doesn't close.

## Forces

- **Eval datasets rot.** Pre-launch test cases degrade 41% in relevance within one month of production deployment (Zylos Research, 2026). Real user queries change; curated datasets don't.
- **Model updates break what worked.** Provider model changes cause silent regressions in tool-calling, latency, and output quality — invisible without automated regression checks.
- **Single-point eval misses drift patterns.** Running evals only at deploy time catches only the moment-of-deploy state, not degradation between releases.
- **Human review doesn't scale.** Spot-checking 5% of production traces catches incidents, not trends. Teams need automated signals that scale to 100% of sessions.
- **Tooling fragmentation creates gaps.** Most teams run offline evals on test sets (52.4%) but fewer run online production monitoring (37.3%) — leaving a blind spot exactly where it matters most (LangChain State of AI Agents, 2026).

## The Move

Build a closed-loop eval system that runs continuously, not just at deploy time. The loop has four stages that feed each other:

**Stage 1 — CI gate (offline eval before deploy).**
Run the full eval harness against every PR. Treat it like a unit test suite: it must pass to merge. Key signals: task success rate, tool call precision, hallucination rate, cost per task, latency. Use statistical thresholds (e.g., Wilson confidence intervals) rather than point-in-time pass/fail, since agents are non-deterministic.

**Stage 2 — Shadow deployment (canary traffic).**
Route a small percentage of real production traffic through the new agent version alongside the current version. Compare outputs at each node — not just final outcomes. Catch regressions that only surface with real inputs. The HN discussion on agent monitoring (HN #47301395, 2026) cites incidents like DataTalks (Claude Code wiped a database) and Replit (agent deleted data during code freeze) — both visible in logs in hindsight, but caught by no system. Shadow mode closes that gap.

**Stage 3 — Production monitoring (continuous trace analysis).**
Instrument every session with structured logging: tool calls, retrieval chunks, token counts, intermediate outputs, final outcomes. Aggregate into session-level metrics (task success rate, error recovery rate) and node-level metrics (tool selection accuracy, context relevance per step). Arthur.ai (2026) recommends monitoring both final outputs and full execution paths — not choosing one. Set alert thresholds: for example, if the tool-call error rate exceeds 5% in a 15-minute window, page the on-call engineer.

**Stage 4 — Dataset curation loop (feedback from production).**
Harvest failing production traces as new eval cases. When a session fails, save the full transcript with labels (what went wrong, which node failed, whether it recovered). This is how your eval dataset stays current — it grows from actual failures, not guesses about what might fail. Thoughtworks (June 2026) recommends defining success criteria in probabilistic terms and continuously expanding test cases from production data.

**The critical circuit: production failures → eval cases → CI gate.**
Every production incident that wasn't caught by the CI gate means a missing test case. Add it. This is the closing of the loop — it ensures the eval suite gets smarter after every incident, not just smarter before every deploy.

## Evidence

- **HN discussion:** "Ask HN: How are you monitoring AI agents in production?" — practitioner reports that Claude Code wiping a database and Replit deleting data during a code freeze were both visible in logs in hindsight but caught by no monitoring system. Points to shadow deployment and structured trace logging as the mitigation. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **Engineering blog:** Anthropic's "Demystifying Evals for AI Agents" (Jan 2026) defines the eval taxonomy (task, trial, grader, transcript, outcome, harness, suite) and describes running evals concurrently with production traffic, using transcripts to diagnose failures, and grading by outcome rather than by agent self-report. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Industry survey:** Cleanlab's "AI Agents in Production 2025" (n=95 enterprise teams, August 2025) found 70% of regulated enterprises rebuild their agent stack every 3 months or faster — driven partly by eval relevance decay and provider model changes. Only <1 in 3 teams are satisfied with their observability solutions. — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Practitioner framework:** Maxim AI's three-layer eval framework (System Efficiency, Session-Level Outcomes, Node-Level Precision) operationalizes the four-stage loop with specific metric categories and threshold guidance for different agent types (RAG, voice, copilot). — [https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices)

## Gotchas

- **Single-point eval gives false confidence.** Running evals only at deploy time misses regressions that happen mid-cycle from provider model updates or upstream data changes. Weekly automated runs catch what manual deploy-time runs miss.
- **Monitoring without alerting is passive.** Logging every trace is table stakes; the value is in threshold-based alerts that fire before users notice. Arthur.ai recommends alerts on both trajectory anomalies and outcome rate shifts.
- **Harvesting production failures requires discipline.** Failing traces must be labeled, deduplicated, and added to the eval suite within days — not months. The curation loop breaks if it becomes a backlog item instead of a workflow step.
- **Statistical significance matters with non-deterministic agents.** A single eval run with 20 trials on a 75%-reliable agent gives wide confidence intervals. Run 100+ trials or use Wilson confidence intervals to avoid shipping changes that appear safe by luck.
