# S-1443 · The Failure Budget Stack — When Your Agent Looks Great in the Demo and Terrible in Production

Your agent completed every test case. Your benchmark score is 94%. You shipped it. Three days later, a 15% API timeout rate drove it into a retry spiral that cost $83 in 47 minutes, and your on-call engineer woke up at 2am to find the production database pinned at 50,000 requests per hour. The benchmark never told you any of this. This is the failure budget problem: agents fail in ways that benchmarks don't measure, and without a system for handling those failures, every deployment is a bet against the long tail.

## Forces

- **Reliability compounds multiplicatively, not additively.** A 10-step pipeline at 85% step reliability succeeds ~20% of the time end-to-end. Zylos Research quantified this across multi-agent systems and found specification failures account for 42% of failures, coordination breakdowns for 37%, and verification gaps for 21% — meaning most failures aren't model failures at all.
- **Benchmarks measure the happy path.** AlphaEval (94 tasks from 7 production deployments, arXiv:2604.12162, April 2026) identified that academic benchmarks use retrospectively curated tasks with well-specified requirements. Production agents face implicit constraints, multi-modal heterogeneity, and undeclared domain expertise. The gap between benchmark scores and production success rates is structural, not accidental.
- **The retry loop is the default failure mode.** When an agent's external validation service times out, the default behavior in most frameworks is to retry — with a prompt instruction like "if it fails, try again." Multiply 5 retries × 10 agent iterations and you have 50 retries. Multiply that by a 15% API timeout rate and you have exponential spend. LLMs hallucinate that tweaking a parameter will fix a hard error; they have no built-in cost awareness or safety boundaries.
- **Evaluation without recovery is theater.** A 56.6% aggregate success rate across 4.5M real production tests (HAL-Evals, arXiv:2602.16666) demonstrates that the "11% running at scale" statistic isn't a deployment problem — it's an evaluation problem. Teams ship unreliable agents because their tests don't measure what actually breaks.

## The Move

Build a failure budget system: define explicit boundaries for cost, iterations, and recovery attempts, then instrument your agent with the mechanisms to stop itself before it becomes an incident.

**1. Define per-run and per-session failure budgets.**
Set maximum total cost ($X per session), maximum iterations (N steps before halting), and maximum retries per tool (not just per call). Budget enforcement must be deterministic code, not prompt instructions — an LLM told "don't spend more than $5" will still hallucinate justifications to continue.

**2. Implement tool-level circuit breakers with three states.**
`Closed` (normal operation), `Open` (failures exceeded threshold, reject all calls), `Half-Open` (allow one test call to check recovery). Set per-tool failure thresholds, not global ones — a timeout on a search tool shouldn't open the circuit for a database tool. Exponential backoff with jitter reduces retry storms by 60-80% (Zylos Research, 2026).

**3. Monitor five stopping signals, not just completion.**
Iteration limit reached. Cost threshold exceeded. Error rate threshold exceeded. Context window utilization approaching limit. Repeated identical action patterns detected (the loop signature). Any single signal should trigger a graceful halt and a structured failure report, not a silent hang.

**4. Evaluate on failure modes, not just outputs.**
Your eval suite should include injected failures: API timeouts, permission errors, partial responses, rate limits. Test whether the agent detects, reports, and degrades gracefully — not whether it produces a correct final answer on a clean input. The FuturOneAI evaluation framework defines task completion rate (>85% target), first-pass accuracy (>70% target), and cost per successful task as primary metrics, with reliability measured as the ratio of successful completions to total attempts.

**5. Ship a structured failure report with every halt.**
When a circuit opens or budget exhausts, the agent should output: which signal triggered, what state was reached, what actions were attempted, and what a human needs to verify before resuming. This is the artifact that makes post-mortems actionable rather than speculative.

## Evidence

- **Reddit r/AI_Agents incident post:** An AI agent became stuck in a retry loop generating ~50,000 requests/hour, taking down a production database. Community analysis: "The retry loop is the classic failure mode for autonomous agents. LLMs often hallucinate that tweaking one parameter will fix a hard error, leading to that 50k request spiral." — *Illustrious_Slip331* — https://www.reddit.com/r/AI_Agents/comments/1r9cj81/
- **Reddit r/AI_Agents $83 retry incident:** A single agent run against an external ticket-routing API (with ~15% timeout rate) burned $83 across 47 retries before detection. Tried per-call retry limits (5) — failed because agent iterations multiplied retries: 5 retries × 10 iterations = 50 total. Tried timeouts — failed because agent interpreted "timeout" as "try a different approach" and looped back to the same call. The fix was a tool-level circuit breaker that opened after N failures and returned a structured error. — https://www.reddit.com/r/AI_Agents/comments/1rap64j/
- **HN Show HN: FailWatch:** Financial AI agent developer built a fail-closed circuit breaker after discovering that when external validation services timed out, default framework behavior was to execute the tool anyway. Built FailWatch as Python middleware enforcing deterministic hard constraints (Pydantic/Regex) rather than prompt-based safety: "Math > Prompts." — https://news.ycombinator.com/item?id=46529092
- **AgentPatterns.ai:** Circuit Breakers for Agent Loops — defines five stopping signals: iteration limit, cost threshold, error rate threshold, context window approaching limit, repeated identical action patterns. — https://www.agentpatterns.ai/observability/circuit-breakers
- **Zylos Research (May 2026):** Production failure analysis of multi-agent systems: specification failures (42%), coordination breakdowns (37%), verification gaps (21%). A 10-step pipeline at 85% step reliability succeeds ~20% of the time. Exponential backoff with jitter reduces retry storms by 60-80%. — https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/
- **AlphaEval (April 2026):** Production-grounded benchmark of 94 tasks sourced from 7 companies deploying AI agents commercially. Found that existing benchmarks use retrospectively curated tasks with well-specified requirements; production reality involves implicit constraints, multi-modal heterogeneity, and undeclared domain expertise. — https://arxiv.org/abs/2604.12162
- **HAL-Evals Agent Leaderboard (arXiv:2602.16666):** Aggregate success rate of 56.6% across 4,492,066 tests spanning 6,259 production AI agents in 10 geographic regions. — https://arxiv.org/abs/2602.16666
- **ThirstySprout evaluation guide (June 2026):** The 5-pillar evaluation framework — intelligence/task success, performance/efficiency, reliability, safety, observability. Notes 72% of enterprises have deployed AI agents yet only 11% run them at scale; attributes the gap to evaluation failure, not model capability. — https://www.thirstysprout.com/post/ai-agent-evaluation-framework
- **FuturOneAI/ai-agent-evaluation-framework (GitHub):** Open-source enterprise evaluation framework defining primary metrics: task completion rate (>85%), first-pass accuracy (>70%), cost per successful task, latency p50/p95/p99, error categorization. — https://github.com/FuturOneAI/ai-agent-evaluation-framework

## Gotchas

- **Per-call retry limits don't compose with agent loops.** Setting `max_retries=5` on a tool doesn't bound total retries — it bounds retries per call. An agent calling that tool 10 times, each time exhausting 5 retries, makes 50 retry attempts. Budget enforcement must be at the session or tool-level cumulative budget, not per-call.
- **Timeout handling is not a circuit breaker.** If your error handling says "on timeout, try a different approach," the agent will try the same broken call 30 times with different framing. Timeouts need to be treated as hard failures that open the circuit, not as soft hints that signal "retry with variation."
- **A passing benchmark tells you nothing about production reliability.** A 94% benchmark score on well-specified tasks means the agent handles well-specified tasks. Real deployments have implicit constraints, flaky APIs, and users who provide partial information. AlphaEval and HAL-Evals both show the gap is structural — you need production-grounded evals with injected failures, not retrospective curated test sets.
- **Cost monitoring alerts fire after the damage is done.** Alerts tell you you're bleeding; they don't clot. A circuit breaker that opens when a budget threshold is approached stops the spend. A billing alert that fires when you've already spent $83 does not.
- **Agents with no stopping conditions will run until they can't.** Whether that's context window exhaustion, a rate limit, a credit card limit, or a production incident — the stopping condition will come from somewhere. Make it a deliberate engineering choice, not an environmental constraint.
