# S-1595 · The Benchmark Gap Stack — When Your Agents Say 90% but Your Users Say It Broke

Your agent scored 91% on SWE-bench. Your users are filing bugs. The benchmark tests whether the agent can resolve GitHub issues. The production system resolves GitHub issues, sends emails, updates databases, and talks to customers — and the benchmark tells you nothing about whether any of that chain works reliably, cheaply, or safely. This is the benchmark gap: the metric that is easy to measure (task completion in a sandbox) diverges from the quality that matters (reliable behavior in the real world).

## Forces

- **Benchmarks are gameable.** UC Berkeley researchers found that all eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench, and one unnamed) could be exploited to achieve near-perfect scores using shortcut strategies that don't reflect genuine agent competence. A model can "pass" without doing the work the benchmark name implies.
- **Research eval ≠ production eval.** Standard benchmarks measure single-session, lab-scale execution with guaranteed tool availability, no temporal component, and no tool failure injection. Production has rate limits, API downtime, state drift, and adversarial inputs. The gap is structural.
- **Outcome metrics miss reasoning quality.** An agent that completes 9/10 tasks but hallucinates 3 database writes along the way looks better than one that completes 7/10 tasks correctly. Trajectory-level visibility — step-by-step reasoning traces — is what separates "it worked" from "it worked correctly."
- **The field is still human-reliant.** Despite all the automation in agent stacks, 74% of production agents still use human-in-the-loop as their primary evaluation method (MAP Study, n=86 production deployments). Automated eval is aspirational; human oversight is real.

## The Move

Measure agent quality across three layers, not one:

**1. Outcome metrics (did it work?)**
- Task completion rate
- Error rate per tool
- End-to-end success rate across multi-step workflows

**2. Trajectory metrics (how did it reason?)**
- Tool call precision (did it call the right tool?)
- Step efficiency (how many steps vs. the minimum needed?)
- Recovery behavior (did it correct itself after errors?)
- Token cost per task (hidden from most benchmarks)

**3. Safety/reliability metrics (would you trust it unattended?)**
- Hallucination rate on structured outputs
- Policy violation rate (actions that technically completed but violated a rule)
- Silent failure rate (tasks that reported success but produced wrong output)

Build a **3-tier rubric** across 7 dimensions → 25 sub-dimensions → 130+ test cases, with human judgment at the top tier and LLM-as-judge (Spearman ≥ 0.80 correlation target) for the middle.

Use domain-matched benchmarks selectively: SWE-bench Verified for code agents, WebArena for browser agents, GAIA for general assistants. Treat them as sanity checks, not contracts. The real signal comes from production tracing.

Integrate evaluation into CI/CD: commit-triggered eval for code-change risk, scheduled eval for regression, event-triggered eval for policy changes. Lemma (YC F25) and AgentShield emerged specifically to catch semantic failures — cases where the agent "worked" but produced wrong output — that traditional observability misses entirely.

## Evidence

- **MAP Study (arXiv 2512.04123):** First large-scale study of AI agents in production (306 respondents, 86 deployed, 20 in-depth interviews, 26 domains, Jul–Oct 2025). Found 70% use off-the-shelf models with no fine-tuning, 68% cap at ≤10 steps before human intervention, 85% build custom (no third-party frameworks), and 74% primary eval method is human-in-the-loop. — [arxiv.org/html/2512.04123v1](https://arxiv.org/html/2512.04123v1)
- **Zylos Research: AI Agent Evaluation (2026-05-13):** Documents the benchmark crisis — all eight prominent benchmarks gameable. Argues that "good eval engineering is now as important as good prompt engineering." Introduces the distinction between trajectory metrics (how the agent reasoned) and outcome metrics (what the agent produced). — [zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **NVIDIA Technical Blog: Agent Evaluation (May 2026):** Provides the core model-vs-agent-eval distinction: model eval asks "is this engine powerful enough?"; agent eval asks "can this system reliably execute a multi-step workflow?" — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)

## Gotchas

- **Benchmark leaderboards are lagging, not leading.** Agent benchmark scores move weekly; official leaderboards are JavaScript-rendered and lag the current frontier. Even the benchmarks themselves warn against treating scores as stable ground truth.
- **Gartner predicts 40%+ of agentic AI projects will be canceled by end of 2027.** Poor evaluation infrastructure is a leading indicator — teams ship agents they can't measure, and can't measure means can't improve, and can't improve means can't justify the investment.
- **LLM-as-judge has its own failure modes.** The judging model can be biased, inconsistent across dimensions, and vulnerable to prompt injection. Target correlation thresholds (≥ 0.80 Spearman) but don't treat automated judging as ground truth — use it to triage, not to decide.
- **Cost-per-task is a fourth axis most teams ignore.** Token spend grows 30–40% month-over-month in unmanaged agent deployments. An agent that scores 95% but costs 3x a 90% agent may not be the better choice. Trajectory efficiency (steps per task, context usage) should be tracked alongside accuracy.
