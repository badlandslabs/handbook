# S-2670 · The Silent Failure Stack — When Your Agent Succeeds Perfectly and Wrecks Everything

The agent completed every step without error. No exceptions, no timeouts, no HTTP 500s. It returned a 200 response and destroyed the production database in nine seconds. This is the silent failure pattern: the failure mode that conventional error handling cannot detect, because it isn't a failure at all — it is a correct action applied in the wrong context.

## Forces

- **Error codes lie about correctness.** Traditional software signals failure through HTTP status codes, exceptions, and return values. AI agents that receive database credentials and execute a `DELETE` statement return 200 — because the delete succeeded. The technical execution was flawless; the outcome was catastrophic.
- **Non-binary failure requires non-binary detection.** An agent that loops forever fails obviously. An agent that produces wrong-but-plausible answers at scale fails silently. Standard APM dashboards cannot surface either — one doesn't trigger alerts, the other doesn't look like an error.
- **Context is not in the system.** Agents don't inherently know they are in production versus staging. They don't know which environment `DATABASE_URL` points to. They don't know that a `$47,000 weekly bill from a cost-tracking loop is abnormal. The prompt that told the agent "clean up old data" never said "never touch production."
- **Latency masks cost.** A runaway loop that burns $4,800 over a weekend looks like normal traffic if you're not tracking cost per-session. It also doesn't trigger latency alerts — the model is still producing tokens at expected speeds.

## The move

Design for silent failures first. Treat every agent action as potentially wrong until validated. Stack these layers:

- **Output validators on every tool result.** After every tool call, run a schema check and a semantic check: does this output make sense in context? A `DELETE FROM` returning 0 rows when there should be rows is as noteworthy as an exception.
- **Permission boundaries as code, not prompts.** Use least-privilege at the infrastructure level: read-only credentials for agents that don't need write access, environment-specific IAM roles, no `DELETE` permissions for agents unless explicitly required. The DataTalks incident executed `terraform destroy` because Railway's token had full destroy permissions — not because the prompt said "you can destroy anything."
- **Circuit breakers on cost and steps.** Per-run token ceilings, per-session step limits (typically 50–200 depending on task complexity), per-user daily spend caps. A misconfigured retriever combined with a permissive max-step count can produce $1,200–$4,800 in LLM spend over a weekend from a single mid-traffic app. Fail closed when projected completion exceeds the remaining budget.
- **Human-in-the-loop gates for destructive actions.** Any tool call that deletes, modifies, deploys, or sends external communications should require explicit confirmation for the first N executions per user, or for any execution targeting production environments. Log the gate decisions.
- **Statistical output monitoring.** Track distributions of outputs over time. A pricing agent setting margins 2% below floor across 10,000 transactions erodes $200K annually without triggering a single error. Alert when output distributions shift beyond calibrated thresholds — even if every individual output looks reasonable.
- **Loop detection in multi-agent systems.** Multi-agent architectures introduce coordination loops: Agent A asks Agent B for clarification; Agent B asks Agent A for help interpreting the response. Neither has logic to break the cycle. Detect this by tracking (agent_id, action, target_agent) triples across the session — if the same directed handoff repeats 3+ times, escalate or terminate.

## Evidence

- **Incident report:** Claude Code agent wiped DataTalks.Club's production PostgreSQL database and Railway volume-level backups in a single API call — 1,943,200 rows representing 2.5 years of student submissions. The agent received Railway credentials with full destroy permissions, correctly interpreted the `terraform destroy` instruction, and executed it against production with zero errors. The environment was never explicitly identified as production in the task prompt. — [GitHub: ai-agent-incidents/INC-006](https://github.com/LaureanoPacheco/ai-agent-incidents/blob/main/incidents/2026/INC-006-datatalks-terraform-destroy.md)
- **Incident report:** A fintech startup's multi-agent cost-tracking system ran in a mutual clarification loop for eleven days undetected. Agent A and Agent B repeatedly asked each other for help without exit logic. The weekly cost bill of $127 became $47,000 before a human noticed. No errors were thrown; no alarms fired. — [Tian Pan: Production AI Incident Response Runbook (2026)](https://tianpan.co/blog/production-ai-incident-response-runbook)
- **Research paper:** IBM Research found that XGBoost-based anomaly detection on agent trajectories achieves 98% accuracy in detecting silent failures (drift, cycles, missing details) — a class of failures that produce no error codes and are invisible to conventional APM. Semi-supervised SVDD achieves 89–96% accuracy. — [arXiv:2511.04032v1 — Detecting Silent Failures in Multi-Agentic AI Trajectories (Nov 2025)](https://arxiv.org/html/2511.04032v1)

## Gotchas

- **Alerting on errors misses the worst failures.** The incidents that cause real damage — database wipes, wrong financial advice, silent data corruption — almost always return 200. Your error-rate alert threshold of 5% will never fire on a system that is confidently wrong on 30% of its outputs.
- **Prompts as guardrails are not guardrails.** Telling the agent "be careful in production" in the system prompt does not prevent production access when credentials grant it. Permission boundaries must be enforced at the infrastructure and credential level, not the instruction level.
- **Single-layer defense fails.** A schema validator on tool outputs is useless if the credentials allow the call in the first place. A permission boundary is bypassed if a human-in-the-loop gate can be trivially approved. Layer these — each layer should be independently useful when all others fail.
