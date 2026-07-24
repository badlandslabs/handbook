# Agent Failure Handling & Recovery: Primary Source Research

**Research scope:** Real-world production LLM agent failure handling, error recovery, dead-end recovery, retry logic, and graceful degradation.  
**Source types:** HN threads, blog posts, company engineering posts, GitHub READMEs, Reddit discussions.  
**Time focus:** 2025–2026.  
**Compiled:** July 2026

---

## PATTERN 1: Infinite Loops & Runaway Agents (Budget/Iteration Guards)

### Description
Agents fail to detect task completion or enter retry loops, burning tokens and money indefinitely. The agent does not crash — it quietly spends. This is the single most financially damaging failure mode in production agents.

### Real-World Examples

**Example 1 — $47,000 Multi-Agent Loop (4-agent LangChain A2A system)**
- A team deployed a 4-agent LangChain system coordinating via Agent-to-Agent (A2A) for market data research.
- Two agents entered an infinite conversation loop and ran undetected for **11 days**.
- Cost escalation: Week 1: $127 → Week 2: $891 → Week 3: $6,240 → Week 4: $18,400 → **Total: $47,000 before shutdown.**
- Root cause: No iteration cap, no budget guard, no conversation-length check.
- Source: [Towards AI — We Spent $47,000 Running AI Agents in Production (Oct 2025)](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)

**Example 2 — $30K+ Coding Agent Loop (Reddit r/AI_Agents)**
- A coding agent looped while implementing financial logic, resulting in over $30K in charges.
- The Reddit thread titled "$30K agent loop" became a reference case cited by multiple agent reliability tools.
- Source: Cited in [AgentFuse GitHub README (2026)](https://github.com/ddaekeu3-cyber/agent-fuse) and [SynapseAI Loop Guide (2026)](https://ddaekeu3-cyber.github.io/synapse-ai/guide/loop-stuck-errors)

**Example 3 — Iteration Cap as Standard Practice (CrewAI Production)**
- AgileSoftLabs CrewAI post-mortem (June 2026) identified max_iter (default 25) as the primary cost driver.
- Recommendation: Set max_iter to 5–8 per agent; anything higher risks runaway loops.
- output_pydantic identified as a top reliability fix — forces valid JSON output, prevents agents from entering invalid state loops.
- Source: [AgileSoftLabs — CrewAI in Production 2026: Real Lessons (June 2026)](https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons)

### Practical Pattern: AgentBudget — ulimit for AI
- Open-source Python SDK (Apache-2.0) that enforces per-session dollar limits on AI agents.
- Wraps LLM calls and tracks cumulative spend; triggers HardLimitExceeded when budget is hit.
- Supports LangChain/LangGraph via LangChainBudgetCallback. 166 commits, active as of 2026.
- Source: [AgentBudget GitHub (2026)](https://github.com/AgentBudget/agentbudget)

---

## PATTERN 2: Dead-End State Traps & Semantic Loops

### Description
Agents reach terminal non-final states — they successfully call tools and take actions, but the system has no outbound transition from that state. Unlike infinite loops, dead-ends are silent: no error raised, no tokens burned, the agent simply disappears into an unrecoverable state.

### Real-World Examples

**Example 1 — Per-Object Reasoning Traces (Mohamed Moustafa, Nov 2025)**
- Documents the "unstable bug wall" pattern in coding agents: fixing one bug produces a second, fixing the second regresses the first.
- Ilya Sutskever cited this as the canonical example of LLMs failing at simple human tasks.
- Proposed solution: Chesterton's Fence for agents — do not modify an object until you understand how it ended up in its current state.
- Implementation: Per-object reasoning traces that track state history before making changes.
- Source: [Mohamed Moustafa — Preventing agent doom loops with per-object reasoning traces (Nov 27, 2025)](https://blog.0xmmo.co/2025/11/27/preventing-agent-doom-loops)

**Example 2 — Dead-End State Trap in Copilot/LLM Patch Systems (DEV Community, 2025)**
- AI coding tools patch state machines to prevent loops by adding safety states (UPDATE_NEEDED, NEEDS_HUMAN_REVIEW) but frequently fail to add outbound transitions from those states.
- Creates "terminal non-final states" — the agent enters them and can never leave.
- Key insight: LLMs do not naturally check global invariants unless explicitly forced.
- Comparison: Infinite loops are predictable and costly but detectable. Dead-end states are silent, invisible, and produce no error.
- Source: [DEV Community — Preventing Infinite Loops in LLM Agent Pipelines: The Dead-End State Trap (2025)](https://dev.to/youngones/preventing-infinite-loops-in-llm-agent-pipelines-the-dead-end-state-trap-pl4)

**Example 3 — MASFT Multi-Agent Failure Taxonomy (Berkeley, 2025)**
- MASFT catalogs 14 specific failure modes across 3 categories for multi-agent systems.
- Identifies cascading errors, scope creep, context loss, and tool misuse as recurring production patterns.
- Cited in VS Code multi-agent development blog as the authoritative taxonomy.
- Source: [VS Code Blog — Your Home for Multi-Agent Development (Feb 5, 2026), citing MASFT (Berkeley, 2025)](https://code.visualstudio.com/blogs/2026/02/05/multi-agent-development)

---

## PATTERN 3: Graceful Degradation & Fallback Chains

### Description
When a tool fails, model is unavailable, or context overflows, the agent degrades to a simpler strategy rather than crashing. This spans per-tool fallbacks (try a different search API), to model failover (switch to backup model), to context reduction (summarize, drop old messages), to human escalation.

### Real-World Examples

**Example 1 — LiteLLM Automatic Provider Failover**
- LiteLLM (widely used in production agent frameworks) implements automatic model failover.
- Syntax: fallbacks = [{"gpt-4o": ["gpt-4-turbo", "gpt-3.5-turbo"]}]
- When the primary model fails after num_retries, LiteLLM automatically routes to the next in the chain.
- Covers: rate limits (429), server errors (500/503), context length errors, timeout errors.
- Source: [LiteLLM Docs — Fallbacks (Provider Failover)](https://docs.litellm.ai/docs/proxy/reliability)

**Example 2 — Tool Call Validation + Zod Schema Validation at Boundary**
- LLMs generate malformed JSON, missing fields, wrong types, out-of-range values in tool calls.
- Runtime schema validation (Zod/Pydantic) at the tool-call boundary converts untrusted LLM output to typed, safe data before execution.
- Google ADK docs recommend defensive JSON parsing with null-safety: safeParseToolCallInput() that returns raw string on parse failure rather than crashing the workflow step.
- Source: [Understanding Data — Tool Call Validation: JSON Schema Validation for Tool Outputs (2026)](https://understandingdata.com/posts/tool-call-validation) and [Medium — Malformed Function Call Errors in Multi-Agentic Systems (Google ADK, 2026)](https://medium.com/@mukrimenurgumus/malformed-function-call-errors-in-multi-agentic-systems-d7462a33b91b)

**Example 3 — Multi-Level Degradation Ladder (Preporato, May 2026)**
- Concrete 6-level degradation sequence:
  1. Full context, all tools, primary model
  2. Retry with exponential backoff (transient errors)
  3. Switch to backup model (LiteLLM fallback)
  4. Reduce context (summarize conversation, drop oldest messages)
  5. Fall back to simpler tool set (disable complex tools)
  6. Human escalation with full context preserved
- Analogy: The agent "keeps moving — just with less convenience at each level."
- Source: [Preporato — Error Handling in AI Agents: Circuit Breakers, Retry & Recovery (May 20, 2026)](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

---

## KEY TENSIONS THAT MAKE FAILURE HANDLING NON-OBVIOUS

### Tension 1: Observability is a prerequisite, not an add-on
Every primary source emphasizes that you cannot recover from failures you cannot see. Yet the most common production failure is silent: dead-end states produce no error, infinite loops produce no crash log, and soft failures (wrong format, right HTTP 200) leave no trace.

Empirical anchor: L4 Study (FSE 2025, arXiv:2503.20263), analyzing 428 real LLM training failures on Platform-X from May 2023–April 2024:
- 89.9% of failures require manual log analysis
- Average 34.7 hours to diagnose each failure
- 16.92 GB of logs on average per failure

### Tension 2: Aggressive vs. Conservative Retry Strategy
Retrying blindly amplifies load (triggering more 429s), burns tokens on permanent failures, and can create loops. The right strategy requires classifying the error type first:

| Error Type | Correct Strategy |
|---|---|
| Transient (429, timeout, 503) | Retry with exponential backoff |
| Semantic (malformed JSON, wrong tool) | Re-prompt with corrective context |
| Resource (token budget, spending cap) | Degrade context or escalate |
| Fatal (auth failure, policy violation) | Abort, alert, log |

Source: Neel Mishra — Agent Error Handling: Retries and Fallbacks (2026) https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

### Tension 3: Context Preservation vs. Cost/Latency
Agents need full context to recover intelligently. But larger context windows mean higher API costs and more failure surface area. The $47K incident happened partly because 4 agents each accumulated full conversation history with no summarization. Teams must decide: truncate (lose recovery information), summarize (lose detail), or pay full price (lose margin).

### Tension 4: Iteration Caps vs. Legitimate Long Tasks
max_iter is a blunt instrument. A hard cap of 5–8 prevents loops but also kills long legitimate tasks. Semantic loop detection (comparing recent states, checking for convergence) works better but adds latency and compute cost. The tension between safety and capability is unresolved in production tooling.

### Tension 5: Agentic Autonomy vs. Guardrail Overhead
Agents are deployed because they handle multi-step tasks autonomously. But production reliability requires checkpoints, timeouts, budget limits, escalation paths, and observability — each adding overhead that competes with the autonomy value. The gap between a working demo and a production agent is estimated at 2 months of engineering. (AgentWorks, May 2026)

---

## BIBLIOGRAPHY OF SOURCES (20 primary sources)

1. Towards AI — "We Spent $47,000 Running AI Agents in Production" (Oct 16, 2025)  
   https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33

2. Mohamed Moustafa — "Preventing agent doom loops with per-object reasoning traces" (Nov 27, 2025)  
   https://blog.0xmmo.co/2025/11/27/preventing-agent-doom-loops

3. DEV Community — "Preventing Infinite Loops in LLM Agent Pipelines: The Dead-End State Trap" (2025)  
   https://dev.to/youngones/preventing-infinite-loops-in-llm-agent-pipelines-the-dead-end-state-trap-pl4

4. AgileSoftLabs — "CrewAI in Production 2026: Real Lessons from Deploying Multi-Agent Systems" (June 2026)  
   https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons

5. AgentBudget GitHub (2026)  
   https://github.com/AgentBudget/agentbudget

6. AgentFuse GitHub (2026)  
   https://github.com/ddaekeu3-cyber/agent-fuse

7. SynapseAI — "AI Agent Infinite Loop and Stuck Errors Guide" (2026)  
   https://ddaekeu3-cyber.github.io/synapse-ai/guide/loop-stuck-errors

8. Preporato — "Error Handling in AI Agents: Circuit Breakers, Retry & Recovery" (May 20, 2026)  
   https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems

9. AI Agents Blog — "Agent Error Recovery: 5 Patterns for Production Reliability" (Mar 5, 2026)  
   https://aiagentsblog.com/blog/agent-error-recovery-patterns

10. AgentWorks — "Agent Error Handling and Recovery Patterns: Production-Ready Resilience" (May 26, 2026)  
    https://agent-works.ai/insights/agent-error-handling-and-recovery-patterns-production-ready-resilience

11. Neel Mishra — "Agent Error Handling: Retries and Fallbacks" (MLOps Series, 2026)  
    https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

12. Muthu.co — "Error Recovery and Graceful Degradation in AI Agents" (Feb 16, 2026)  
    https://notes.muthu.co/2026/02/error-recovery-and-graceful-degradation-in-ai-agents/

13. Understanding Data — "Tool Call Validation: JSON Schema Validation for Tool Outputs" (2026)  
    https://understandingdata.com/posts/tool-call-validation

14. Medium — "Malformed Function Call Errors in Multi-Agentic Systems" (Google ADK, 2026)  
    https://medium.com/@mukrimenurgumus/malformed-function-call-errors-in-multi-agentic-systems-d7462a33b91b

15. L4 Study — "Diagnosing Large-scale LLM Training Failures via Automated Log Analysis" (FSE 2025, arXiv:2503.20263)  
    https://arxiv.org/abs/2503.20263

16. Yun1976/ai-agent-incidents GitHub — "Real AI agent incident post-mortems" (2026)  
    https://github.com/Yun1976/ai-agent-incidents

17. NassimRahimi/agent-failure-recovery GitHub (2026)  
    https://github.com/NassimRahimi/agent-failure-recovery

18. LiteLLM Docs — "Fallbacks (Provider Failover)"  
    https://docs.litellm.ai/docs/proxy/reliability

19. VS Code Blog — "Your Home for Multi-Agent Development" (Feb 5, 2026), citing MASFT (Berkeley, 2025)  
    https://code.visualstudio.com/blogs/2026/02/05/multi-agent-development

20. Hacker News — "Show HN: Agent-triage – diagnosis of agent failures from production traces" (Jun 2026)  
    https://news.ycombinator.com/item?id=47334775

---

## ADDITIONAL PRIMARY SOURCES (July 2026 research run)

### SDK-Level Error Handling

**Anthropic Python SDK** - Retry Configuration
Source: GitHub Discussion #1341
URL: https://github.com/anthropics/anthropic-sdk-python/discussions/1341
miaoquai.com practitioners: retry with exponential backoff, fallback models, tool failure handling,
state consistency cleanup. SDK: max_retries=3 (default 2), timeout=60.0.

**Cloudflare Agents SDK** - Built-in Retries
URL: https://developers.cloudflare.com/agents/runtime/execution/retries/
Default: 3 retries with jittered exponential backoff. NOTE: No circuit breaker.
Each task exhausts its own retry budget independently.

**Strands Agents SDK** - Retry Strategies
URL: https://strandsagents.com/docs/user-guide/concepts/agents/retry-strategies
Rate limits, service unavailability, timeouts: auto-retried with exponential backoff.
Configurable via Agent.retryStrategy parameter.

### HTTP Status Code Taxonomy

URL: https://claudeimplementation.com/blog/claude-error-handling-retry-patterns
Retryable: 429 (Rate Limited), 500 (Server Error), 529 (API Overloaded)
NOT retryable: 400, 401, 403, 404

### Circuit Breaker Libraries

**agentguard-llm** (PyPI: agentguard) - Production-grade fault tolerance
URL: https://github.com/maheshmakvana/agentguard-llm
"AI agents fail at 91%+ rates in production. agentguard stops that."
Zero hard deps. Works with LangChain, AutoGen, CrewAI, or custom pipelines.

**agentguard (rigvedrs)** - Circuit Breaker Guide
URL: https://rigvedrs.github.io/agentguard/guides/circuit-breaker
Trip threshold: 5 consecutive failures -> breaker opens for 30s.
Alternative: gt 30% error rate in 10min -> stop agent.
Policy modes: CLOSED (requeues) vs OPEN (allow with bypass signals).

**Medium** - Resilience Circuit Breakers for Agentic AI
URL: https://medium.com/40michael.hannecke/resilience-circuit-breakers-for-agentic-ai-cc7075101486
Safety Alignment CBs (inference safety) vs Operational Resilience CBs (component failures).
State machine: CLOSED - OPEN - HALF_OPEN.

### Browser Agent Loop Guards

**browser-use/views.py** - Production loop guard configuration
URL: https://github.com/browser-use/browser-use/blob/main/browser_use/agent/views.py
- planning_replan_on_stall: 3 consecutive failures before replan nudge
- planning_exploration_limit: 5 steps without plan before nudge
- step_timeout: 180s, llm_timeout: 60s
- final_response_after_failure: attempt final recovery before giving up

**oh-bug.com** - Computer-Use Agent Browser Automation
URL: https://www.oh-bug.com/posts/computer-use-agent-browser-automation-production/
"Model decides next step. Human-written executor constrains actions, validates state,
and leaves evidence." Four layers: Observation, Decision, Execution, Validation.

### Loop Detection Libraries

**LoopBuster** (93 stars, MIT, 2026-05-30)
URL: https://github.com/liuchunwei732-cmyk/loopbuster
4 strategies: ExactRepeat, FuzzyRepeat (Jaccard + Levenshtein + noise denoising),
CycleDetection, OutputStagnation. Zero hard deps, framework-agnostic.
Also: StateStasisGuard for meaningful-state-change detection.

### Checkpoint and Resume

**LangGraph Checkpointing** (GA v1.0, October 2025)
URL: https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/README.md
MemorySaver (dev) and PostgresSaver (prod with connection pooling).
interrupt() pauses graph, saves state. Resume via Command(resume=...).
Source: https://dev.to/focused_dot_io/langgraph-error-handling-patterns-for-production-ai-agents-33p7

**Neel Mishra Blog**
URL: https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html
"Store checkpoints in Redis or a database, not in-memory. Agent processes can crash
or be restarted by container orchestrators. External state stores ensure recovery."

**agent-persist** - Checkpoint across restarts
URL: https://github.com/dabit3/agent-persist

**OneUptime** - Dapr Checkpointing
URL: https://oneuptime.com/blog/post/2026-03-31-dapr-agents-checkpoint-resume/view
Dapr state management for distributed agent checkpoint/resume.

### Multi-Agent Failure Distribution

**zylos.ai Research**
URL: https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery
Galileo 2025: Specification failures ~42%, Coordination breakdowns ~37%,
Resource exhaustion ~12%, Security violations ~9%.

**CrewAI vs LangGraph** (bswen.com)
URL: https://docs.bswen.com/blog/2026-04-17-agent-timeout-failure-recovery/
LangGraph checkpointing more mature than CrewAI. CrewAI: max_iterations only, no native checkpoint.

### Timeout Fixes

**markaicode.com** - Fix LangChain Agent Timeout Errors
URL: https://markaicode.com/errors/ai-automation-timeout-fix
"82% of agent failures in LangChain 0.3.x were caused by DEFAULT TIMEOUTS."
LangChain issue: https://github.com/langchain-ai/langchain/issues/12452
Recommended: max_execution_time=120 for tool-heavy agents.

**bswen.com** - Agent Timeout and Failure Recovery
URL: https://docs.bswen.com/blog/2026-04-17-agent-timeout-failure-recovery/
"Timeout and failure recovery are not optional features - they are survival requirements."
Cascade problem: Agent A timeout -> B blocked -> C blocked.
Solutions: per-agent timeout walls, checkpoint on timeout, cascade notification.

### Community Discussions

**Reddit r/AI_Agents**
URL: https://www.reddit.com/r/AI_Agents/comments/1qnavt9/the_infinite_loop_fear_is_real_how_are_you/
"Most agent frameworks give you great tools for acting, but very few tools for restraint."
Practitioners: max step budgets, token budget walls, cost alerts, structured output validation.

**Hacker News** threads:
- Why agents fail in prod: news.ycombinator.com/item?id=46450307
- What broke evaluating agent: news.ycombinator.com/item?id=47416033

### OpenHelm - Error Handling Quantified

URL: https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents
"Proper error handling increased agent reliability from 87% to 99.2% (14x fewer failures)."
Retry: 1s, 2s, 4s, 8s (max 3-5), 30% jitter, 60s cap.
"Do not fail closed on everything. Model API down: try fallback. Auth failure: escalate."

---

*Sources from July 2026 research run. All quotes from primary source content.*

---

## NEWLY RESEARCHED SOURCES (July 2026 supplementary)

### Hacker News Threads

**1. "Show HN: LoopGain – Stop agent loops with control theory, not max_iterations"**
- Author: `fitz2882`
- Date: July 2026 (1 day ago at time of search)
- URL: https://news.ycombinator.com/item?id=48919562
- Points: 30 | Comments: 12
- Summary: Open-source library replacing fixed `max_iterations` caps with control-theoretic termination policy using loop-gain (Aβ) bands + best-so-far rollback. 92.8% less API spend vs. `max_iter=20`, ~15× faster, quality preserved. Adapters for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents, Claude Agent SDK.
- Repo: https://github.com/loopgain-ai/loopgain (Apache-2.0, ~101 stars)

**2. "Ask HN: How do you prevent retry cascades in LLM systems?"**
- Author: `amabito`
- Date: ~5 months ago (Feb 2026)
- URL: https://news.ycombinator.com/item?id=47087398
- Summary: Author ran into retry amplification issue: provider returned 429s, per-call retry limits were in place but no containment mechanism, leading to cascading failures. Asks about chain-level retry budgets, shared circuit breaker state, per-minute cost ceilings, cost-based limits (tokens/$) vs. retry count.
- Discussion focus: Preventing retry amplification across multi-call agent chains.

**3. "Show HN: AgentCircuit – Circuit breaker for AI agent functions"**
- Author: `simranmultani`
- Date: ~5 months ago (Feb 2026)
- URL: https://news.ycombinator.com/item?id=46899775
- Points: 1 | Comments: 1
- Summary: One decorator to make any AI agent reliable. Loop detection, auto-repair, output validation, budget control. Zero config, no server, no database. Supported: LangGraph, LangChain, CrewAI, AutoGen.
- Repo: https://github.com/simranmultani197/AgentCircuit (MIT, ~5 stars)

**4. "Ask HN: How do you prevent MCP agents from looping in production?"**
- Author: (unknown — thread content summarized in search results)
- Date: ~4 months ago (Mar 2026)
- URL: https://news.ycombinator.com/item?id=47331249
- Summary: Author building with MCP, starting to run agents with more autonomy (multiple tools, longer sessions, less human oversight). Currently using hard iteration limits which feels like a blunt instrument. Asking what others do for production MCP agents.

**5. "Show HN: AgentFuse – A local circuit breaker to prevent $500 OpenAI bills"**
- Author: `abdulbasitali`
- Date: ~6 months ago (Jan 2026)
- URL: https://news.ycombinator.com/item?id=46404312
- Points: 3 | Comments: 3
- Summary: Author fell asleep while a script was running, agent got stuck in a loop, woke up to drained OpenAI credit balance. Built a lightweight local circuit breaker as alternative to heavy enterprise proxies or cloud dashboards.
- Repo: https://github.com/AbdulBasitA/agent-fuse (MIT, pip install `agent-fuse`)

**6. "Show HN: AgentGuard – Auto-kill AI agents before they burn through your budget"**
- Author: (HN user, npm package `agent-guard`)
- Date: ~10 months ago (Sep 2025)
- URL: https://news.ycombinator.com/item?id=44742710
- Summary: npm package that monitors AI API costs in real-time and auto-terminates processes when budget limit is reached. Monkey-patches HTTP libraries to detect AI API calls and calculates costs. Only supports OpenAI and Anthropic APIs. Noted limitation: cost calculations are estimates.

**7. "Ask HN: How are you testing AI agents before shipping to production?"** (contains cascade failure discussion)
- Author: `rolifromhermes`
- Date: ~4 months ago (Mar 2026)
- URL: https://news.ycombinator.com/item?id=47325105
- Summary: Lists failure modes including: "Cascade failures — tool call #1 fails, agent keeps going, by the time a human sees the result 3 calls have compounded the error." Also: data integration drift (deprecated endpoints), authorization confusion (cached context bleeds between users). 50+ test cases across categories.

**8. "The unreasonable effectiveness of an LLM agent loop with tool use"** (HN discussion)
- URL: https://news.ycombinator.com/item?id=43998472
- Notable comment by `CuriouslyC`: "The main problem with agents is that they aren't reflecting on their own performance and pausing their own execution to ask a human for help aggressively enough. Agents can run on for 20+ iterations in many cases successfully, but also will need hand holding after every iteration in some cases. They're a lot like a human in that regard, but we haven't been building that reflection and self awareness into them so far, so it's like a junior that doesn't realize when they're over their depth and should get help."

**9. "Show HN: Agent framework that generates its own topology and evolves at runtime"**
- Author: `vincentjiang`
- Date: ~5 months ago (Feb 2026)
- URL: https://news.ycombinator.com/item?id=46979781
- Points: 107 | Comments: 35
- Summary: Agent framework that generates/changes its own topology at runtime. HN discussion touched on failure modes of dynamic topology — harder to reason about where loops can form.

**10. "Show HN: Optio – Orchestrate AI coding agents in K8s to go from ticket to PR"**
- Author: `jawiggins`
- Date: ~3 months ago (Apr 2026)
- URL: https://news.ycombinator.com/item?id=47520220
- Points: 88 | Comments: 60
- Summary: K8s orchestration for AI coding agents. Discussion touched on agent reliability, failure handling, and human-in-the-loop checkpoints.

---

### GitHub Repositories

**1. hamley241/circuit-breaker-agents**
- URL: https://github.com/hamley241/circuit-breaker-agents
- License: Apache-2.0 | Created: 2026-03-30
- Stars: 0 | Forks: 0
- **Summary:** Monte Carlo validation (100,000+ trials) of circuit breaker patterns for multi-agent LLM systems. Results:
  - SIMPLE_CB: ~7% cascading failure reduction
  - AI_CB (4-state reasoning-aware): ~48% reduction
  - ADAPTIVE_CB (dynamic thresholds + chain-length optimization): **~75% reduction**
- Key finding: Adaptive circuit breakers outperform simple ones significantly in multi-agent chains.

**2. hailports/self-healing-agent**
- URL: https://github.com/hailports/self-healing-agent
- License: MIT | Created: 2026-06-28
- Stars: 0 | Forks: 0 | **Python 3.9+ | Zero dependencies (stdlib only)**
- **Summary:** Tiny reference loop for autonomous AI agents with: retries, circuit breakers, watchdogs, checkpoint/resume, budget governor. Provider-agnostic via single `generate(system, messages) -> str` method. Runs offline with no API keys. All reliability components independently testable.
- Failure patterns addressed: rate limits, flaky APIs, hung requests, processes dying.

**3. T4n17/CrewAI-Retry-After-Failure-Patch**
- URL: https://github.com/T4n17/CrewAI-Retry-After-Failure-Patch
- License: MIT | Created: 2025-07-30
- Stars: 1 | Forks: 0
- **Summary:** Community patch for CrewAI Task class implementing retry-on-failure. In standard CrewAI, task failure due to exception (e.g., API rate limit) leaves crew in broken state. This patch adds configurable retry attempts before giving up.

**4. vectara/awesome-agent-failures**
- URL: https://github.com/vectara/awesome-agent-failures
- License: Apache-2.0 | Created: 2025-08-20
- Stars: **190** | Forks: 17
- **Summary:** Community-curated collection of AI agent failure modes and battle-tested solutions. Top failure modes documented:
  - Tool Hallucination: tool output incorrect → agent makes decisions on false info
  - Response Hallucination: agent combines tool outputs into factually inconsistent response
  - Infinite Loops: agent keeps repeating actions (26+ reports in dataset)
  - State Confusion: agent operates on wrong target or leaves workflow in incorrect state
  - Premature Submission: agent submits incomplete artifact before workflow is done
  - Retry/No-Progress Loop: repeated retries with no adaptation (26 reports)
- Also documents [Agent0 Issue #1011](https://github.com/agent0ai/agent-zero/issues/1011): agent stuck in repeat loop after tool hangs, with 9 comments and linked PR #1781.

**5. huggingface/smolagents — Timeout Fix PR #2003**
- URL: https://github.com/huggingface/smolagents/pull/2003
- Title: "fix: add timeout to web search tools to prevent indefinite hangs"
- Author: `giulio-leone`
- **Summary:** PR adding timeouts to web search tools in smolagents. Prevents indefinite hangs — a concrete example of the timeout-gap problem in agent tool execution.

**6. microsoft/autogen — Discussion #6200 (Retry Mechanism)**
- URL: https://github.com/microsoft/autogen/discussions/6200
- Author: `Yuva-raj-18`
- Date: 2025-04-04
- Category: feature-suggestions
- **Summary:** Request for automatic retry when agent returns empty response. Discussion of retry design for AutoGen .NET. Root concern: agent returning empty response randomly with SemanticKernelAgentAdapter — why does it happen + how to handle it.

**7. langchain-ai/langgraph — Issue #6170 (Robust Node Error Handling)**
- URL: https://github.com/langchain-ai/langgraph/issues/6170
- Author: `sydney-runkle` (LangGraph maintainer)
- Created: 2025-09-19 | State: open | Comments: 8
- **Summary:** LangGraph maintainer-labeled issue for scoping "more robust error handling for nodes" — described as needing "some sort of hooks or middleware" and "awesome docs." Tagged as enhancement, internal. Frequently requested feature.

**8. langchain-ai/langgraph — Fault Tolerance Documentation**
- Source: https://www.langchain.com/blog/fault-tolerance-in-langgraph
- Authors: Quanzheng Long, Sydney Runkle
- Published: June 4, 2026
- **Summary:** LangGraph's three fault tolerance primitives:
  1. **RetryPolicy**: Automatic retries with backoff/jitter for transient errors. Attached directly to nodes via `add_node`.
  2. **TimeoutPolicy**: Wall-clock or progress-based cap on node attempts.
  3. **error_handler**: Runs after retries exhausted, with failure context.
- Key insight: LangGraph models agents as discrete graph steps → unified place to handle all failure types.
- Also: DeepWiki docs at https://deepwiki.com/langchain-ai/langgraph/3.8-error-handling-and-retry-policies

---

### Notable Blog/Article Sources

**1. "How to Handle Agent Timeout and Failure Recovery in Multi-Agent Systems"**
- Source: docs.bswen.com
- URL: https://docs.bswen.com/blog/2026-04-17-agent-timeout-failure-recovery/
- **Summary:** Practical comparison of CrewAI vs LangGraph approaches to circuit breakers, retry logic, and error handling. LangGraph checkpointing more mature. CrewAI: `max_iterations` only, no native checkpoint. Key quote: "Timeout and failure recovery are not optional features — they are survival requirements." Cascade problem: Agent A timeout → B blocked → C blocked. Solutions: per-agent timeout walls, checkpoint on timeout, cascade notification.

**2. "Graceful Degradation — How AI Agents Handle Failing Services"**
- URL: https://kangclaw.github.io/posts/graceful-degradation-ai-agents
- Published: February 20, 2026
- **Summary:** Philosophy: "Degrade, don't die." Multiple live examples:
  - Search: primary API fails → backup search provider
  - Notifications: push fails → queue for retry → fallback to email
  - Memory: vector search times out → keyword fallback
  - Voice: primary TTS fails → alternative TTS
- Key principle: silent fallback preferred over error messages when possible.

**3. "Infinite Loop / Stuck Agent" Failure Mode Reference**
- URL: https://reputagent.com/failures/infinite-loop
- **Summary:** Structured failure mode catalog entry:
  - Detection: repeated identical/near-identical actions, increasing resource consumption, no task progress, circular reasoning in logs
  - Root causes: missing termination conditions, inadequate error handling, poor state tracking, lack of progress metrics
  - Mitigation: explicit termination criteria, progress tracking, watchdog timers, budget caps

**4. "500 AI Agent Repos: Infinite Loops the Most Common Bug"**
- URL: https://aiproductivity.ai/news/ai-agent-repos-infinite-loop-bugs-research/
- **Summary:** Security audit of 500 open-source AI agent codebases. Key finding: one consistent flaw across nearly all — no exit conditions. "Developers build the loop; they skip the stop."

**5. "The expensive part of an AI agent failure is usually the retry loop"**
- URL: https://dev.to/keesan/the-expensive-part-of-an-ai-agent-failure-is-usually-the-retry-loop-245b
- **Summary:** Author experienced three errors that took down staging cluster. Key insight: retry loops are where the real cost accumulates — both in API spend and in cascading downstream failures.

---

### ArXiv Papers Referenced in HN/Community Discussions

**"Operational Hallucination and Safety Drift in AI Agents"**
- URL: https://arxiv.org/abs/2607.18367
- **Summary:** Empirically characterizes two observed failure modes across state-of-the-art LLMs:
  - **Safety Drift**: gradual erosion of declared safety intent → constraint-violating actions
  - **Operational Hallucination**: persistent repetitive tool calls

**"Hallucination as Context Drift: Synchronization Protocols for Multi-Agent LLM Systems"**
- URL: https://arxiv.org/abs/2606.21666
- **Summary:** Multi-agent LLM systems produce hallucinated outputs not explained by model deficiencies alone — significant class of failures arises from **context drift**: divergence of internal knowledge states between concurrent agents. Proposes synchronization protocols.

---

*All URLs verified via web search and extraction. Dates approximated from relative search results. Stars/forks as of July 2026 search time.*
