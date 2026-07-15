# S-1121 · The Trajectory Evaluation Stack — When Your Benchmark Says 87% and Your Users Say It Is Broken

When your agent passes every test in the lab but fails every user in production — the problem is not the model. It is that you were measuring the wrong thing. Endpoint accuracy on curated benchmarks does not predict real-world reliability. The teams shipping production agents have moved to trajectory-first evaluation: scoring not just the destination, but every step taken to get there.

## Forces

- **Per-step accuracy compounds against you.** At 85% per-step accuracy, a 10-step workflow succeeds only ~20% of the time. At 95% per-step accuracy, a 10-step workflow still only reaches ~60% success. Endpoint scoring hides this compounding failure mode.
- **Benchmarks are gamed.** UC Berkeley researchers examined eight prominent AI agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be exploited to achieve near-perfect scores without solving the actual task. A single-number score tells you nothing about how the agent got there.
- **Cost and quality are inseparable.** Two agents with identical accuracy can have 50x cost difference depending on trajectory efficiency — number of tool calls, context window usage, and unnecessary retries. Lab benchmarks ignore cost; production budgets do not.
- **Proxy metrics lie.** Unit test pass rates, presence of bug fixes, and task completion scores are proxy measurements. An agent can reach the right answer by hallucinating a tool call that happened to return useful data, or retrying a failed step 12 times. Proxy metrics reward the outcome, not the behavior.
- **Production is messier than benchmarks by 37%.** Benchmarks use clean, unambiguous inputs. Production faces ambiguous instructions, flaky APIs, adversarial inputs, and cascading failures — conditions that standard benchmarks do not simulate.

## The Move

The trajectory evaluation stack treats agent quality as a multi-dimensional, continuous measurement problem. The core shift: evaluate *how* the agent works, not just *what* it produces.

### Core patterns

- **Step-level scoring over endpoint scoring.** Score every decision point in the agent's execution — not just whether it reached the correct answer. A trajectory rubric assigns partial credit for correct intermediate steps, flags unnecessary tool calls, and penalizes loops or redundant actions. This catches the 20–40% of cases where agents reach correct answers via terrible paths.
- **Multi-dimensional metrics.** Track four dimensions simultaneously: (1) task success rate, (2) trajectory efficiency (tool calls, token spend, steps), (3) cost per task, and (4) safety/harmlessness. A fifth dimension — reliability — measures consistency across repeated runs with the same input.
- **Replay harnesses.** Store production traces and replay them against new agent versions in sandboxed environments. This is the fastest feedback loop for regression testing: if a new model or prompt change causes the agent to take a different path on 30 known-good traces, catch it before shipping.
- **Harness interception.** Route every agent action through an evaluation hook that can score, approve, block, or modify the action in real time. One e-commerce team used harness interception to reduce hallucinated refund offers by 94.2%, saving thousands per week. The harness acts as a policy layer between the agent and the world.
- **The 5-bucket failure triage.** Classify every production failure into one of five buckets before changing anything: (1) tool selection error, (2) argument generation error, (3) tool execution error, (4) state handling error, (5) retry policy error. Most failures originate in one layer and get amplified by weak handling in another.
- **LLM-as-judge for trajectory quality.** Use a second LLM to score the quality of the agent's reasoning chain, not just the output. The judge evaluates whether the agent's plan was sound given what it knew at each step, whether it acknowledged uncertainty, and whether it recovered appropriately from errors.

## Evidence

- **HN: "Principles for production AI agents" (app.build, 128 points, 2025):** Surveyed 30+ startup founders and 40+ enterprise practitioners deploying agents across financial services, healthcare, cybersecurity, and developer tooling. Key finding: the teams with highest production success rates all used multi-dimensional eval pipelines, not single-benchmark scores. — [HN Discussion](https://news.ycombinator.com/item?id=44712315)
- **Zylos Research: "AI Agent Evaluation and Benchmarking" (2026):** UC Berkeley research found all 8 prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) were exploitable — near-perfect scores achievable without genuine task completion. Production eval now requires adversarial testing, trajectory scoring, and continuous monitoring. — [Zylos Research](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Vercel Blog: "AGENTS.md outperforms skills in our agent evals" (Jan 2026, 524 HN points):** Vercel's coding agent eval found a compressed 8KB `AGENTS.md` docs index achieved 100% pass rate on Next.js 16 API tasks, while explicit skills instruction only reached 79%. Embedding task-specific context directly in the agent's execution context outperforms standalone prompt engineering — the eval harness was the key to measuring this. — [Vercel Blog](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
- **Jobsbyculture: "AI Agent Evaluation Guide 2026" (May 2026):** Documented the 37% lab-production gap, the 50x cost variance across agents with identical accuracy, and the 20–40% of cases where endpoint scoring misses terrible trajectories. Practical eval pipeline: trajectory scoring → replay harness → regression suite → production monitoring. — [Jobsbyculture](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)

## Gotchas

- **Changing prompts after eval is a moving target.** If you iterate on the prompt after seeing eval results, the eval is measuring the post-hoc optimized version, not the generalizable agent. Fix the eval before optimizing — not after.
- **Idempotency is a prerequisite for meaningful retry eval.** A retried step without an idempotency key duplicates the side effect it was trying to fix. Retry evaluation is meaningless if steps are not idempotent by design.
- **Trajectory scoring requires ground-truth step annotations.** Scoring intermediate steps requires knowing what the correct sequence was — which is harder than knowing the correct answer. Invest in annotating representative task traces before trying to score every new task.
- **Cost-per-task eval requires production traffic or realistic synthetic workloads.** Lab-only eval underestimates real cost because production inputs are more diverse and adversarial. Budget for shadow-mode eval in production (agent runs in parallel, no action taken, cost tracked) before full deployment.
- **LLM-as-judge for trajectories is gamed by capable agents.** A sophisticated agent can produce plausible reasoning chains that look sound but hide a bad decision. Pair LLM judges with structural checks: tool call counts, context window usage, error recovery rates.
