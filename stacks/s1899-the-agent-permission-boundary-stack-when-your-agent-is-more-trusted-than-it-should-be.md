# S-1899 · The Agent Permission Boundary Stack — When Your Agent Is More Trusted Than It Should Be

You shipped an agent. It works. Then it scans a network for 8 hours and burns your cloud budget, or exfiltrates data through a proxy it found online, or follows an instruction injected into a webpage it visited. The capability you gave it — browse, execute, call APIs — is exactly what turned a mistake into an incident. The problem is not the prompt. The problem is that nobody drew a perimeter.

## Forces

- **Agents amplify authority** — the same capability that makes an agent useful (web access, file writes, API calls) is the capability that makes it dangerous if misused or manipulated
- **Prompt injection is a runtime threat** — a webpage, email, or document the agent processes can alter its behavior mid-task; this attack surface doesn't exist for traditional software
- **The enforcement gap** — most teams build agent capability (tools, memory, orchestration) but skip agent safety infrastructure until after a costly incident
- **Default-deny is not the norm** — agents are typically given broad network egress, real credentials, and filesystem access because constraining them "just works" feels worse than capability
- **Cost and capability are coupled by default** — giving an agent real APIs means giving it unlimited API spend unless you explicitly decouple the two

## The Move

A layered permission and safety architecture built around three concentric rings:

**Ring 1 — Runtime isolation (the containment layer)**
- Run agent code in gVisor or microVMs (Kata Containers, Firecracker) instead of raw containers — gVisor intercepts syscalls at the user-space kernel boundary, preventing host kernel exploits from untrusted AI-generated code
- Default-deny network egress: proxy-only outbound, explicit allowlists for destination hosts; the agent cannot reach anything not explicitly permitted
- Deterministic filespace sync: agent writes to a scoped filesystem overlay that is committed or rolled back, never left as ambient state

**Ring 2 — Permission scoping and approval gates (the authority layer)**
- Every tool call is permission-scoped by default — an agent that can send emails can only send to approved recipients, an agent with browser access runs in an isolated browser session with no access to host cookies or credentials
- Human-in-the-loop checkpoints for high-stakes actions: file deletes, API writes to production systems, sending external emails, modifying permissions
- Output validators between every agent step and downstream systems — scan LLM outputs for PII, credentials, or unexpected commands before passing them on
- Audit logs for every tool call, persisted durably and queryable; not just "what happened" but "what would have happened if the guard didn't fire"

**Ring 3 — Automated enforcement (the limits layer)**
- Hard cost budgets per agent session — set a dollar ceiling that terminates the agent when breached, not an alert that pages someone at 3 AM
- Circuit breakers on tool call patterns: detect retry loops (N identical failures in M seconds), detect cost velocity spikes (N dollars in N minutes), detect context accumulation (token growth rate exceeds task progress rate)
- Kill switch: single-agent halt (stop this agent) and fleet halt (stop all agents) — callable via API, dashboard, or automated policy trigger; tested quarterly
- Token budgets enforced at the gateway before they hit the LLM — the agent never gets close to its context window limit before the system gates it

## Evidence

- **HN "Show HN":** Gobii's team described their production sandbox architecture: per-agent gVisor isolation, default-deny egress with proxy-only outbound, deterministic filespace sync, and audit logs for every tool call — explicitly framing agent safety as a "runtime architecture problem, not a prompt-engineering problem." — [HN thread #46810589](https://news.ycombinator.com/item?id=46810589)
- **GitHub Gist + HN:** A developer documented how an autonomous agent burned through an entire cloud budget scanning the DN42 network — the agent had no spending ceiling, no circuit breaker, and no alert fired until the bill arrived. The root cause: "an AI agent with access to paid APIs and no spending limit is a credit card with no ceiling handed to an entity that doesn't understand money." — [GitHub Gist / AI Agent Cost Runaway Checklist](https://gist.github.com/QuocTranWorkspace/16b1b7413b65f1fed6ad79065d68983b) · [HN discussion on DN42 incident](https://lantian.pub/en/article/fun/ai-agent-bankrupted-their-operator-scan-dn42lantian.lantian/)
- **Engineering Blog:** TrueFoundry documented a 3-layer gateway approach: token bucket rate limiting per (user, repo, model), pattern-detecting circuit breakers for cost velocity and loop signatures, and a fallback chain (primary → cheaper model → cache → 503) — framed as SRE principles adapted to a workload where the unit of waste is dollars per token. — [TrueFoundry: Rate Limiting AI Agents](https://www.truefoundry.com/blog/rate-limiting-ai-agents-preventing-llm-api-exhaustion)
- **Enterprise Analysis:** OpenEmpower's analysis of 2026 production agent failures identified runaway loops, tool misuse, context overflow, hallucinated actions, and cost explosions as "systematic failure patterns, not edge cases" — the common thread in all of them was the absence of automated enforcement at the capability layer. — [OpenEmpower: AI Agent Production Failures](https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026)

## Gotchas

- **Sandboxing code execution is not the same as sandboxing the agent's decisions** — gVisor stops a malicious process, but it doesn't stop a well-intentioned agent from making expensive mistakes based on injected instructions in content it consumed
- **A kill switch you haven't tested is not a kill switch** — several teams have one on paper but never ran a drill; the 3 AM incident is the wrong time to discover the API is broken
- **Budget alerts are not budget enforcement** — dashboards that show spending after the fact don't prevent runaway costs; hard caps that terminate the agent do; the difference is monitoring vs. enforcement
- **The agent's tools are the attack surface, not the prompt** — most security discussion focuses on prompt injection defense, but the real production risk is indirect: an agent visits a compromised page, the injected instruction tells it to export data via an approved webhook, and the egress proxy never fires because the destination was allowlisted
