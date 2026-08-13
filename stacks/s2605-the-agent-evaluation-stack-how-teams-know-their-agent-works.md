# S-2605 · The Agent Evaluation Stack — How Teams Know Their Agent Works

You shipped the agent. It looks great in the demo. Now you need to change the prompt, swap the model, or add a tool — and you have no idea if you broke it. Without a standing evaluation harness, every change is a bet against production, not a decision backed by evidence.

## Forces

- **Agents are state machines, not functions** — the same input can produce different trajectories depending on tool responses, context, and model sampling. Single-turn output grading misses most failure modes.
- **Eval quality compounds** — the harness you build in week one shapes every decision you make for the next two years. Teams that skip evals early spend months retrofitting them into systems already in production.
- **Offline and online evaluation serve different purposes** — offline datasets catch regressions before deploy; production traffic reveals what the test set never imagined. Neither alone is sufficient.
- **LLM-as-judge is powerful but leaky** — judge models introduce their own biases and can be gamed, yet human annotation at scale is too expensive to use on every trial.

## The move

Build a multi-layer evaluation harness that gates every deploy. The stack has four dimensions, each addressed by a distinct technique:

- **Trajectory evaluation** — grade the entire execution path, not just the final output. Score goal completion, tool-call sequence correctness, and whether the agent recovered from errors. Langfuse calls this the "conversation flow" dimension. The reaatech/agent-eval-harness uses heuristic multi-turn quality assessment with coherence and goal-completion scoring.
- **Golden trajectories as regression baseline** — record known-good agent runs as reference trajectories. New agent versions are compared against them in CI. This is the strongest offline check for decidable tasks where correct behavior is defined. The HN practitioner `roadside_picnic` recommends starting with hundreds of evals and consolidating to the most signal-bearing ones over time.
- **LLM-as-judge with calibration** — use a separate model (often GPT-4o or Claude Sonnet for high-stakes, or a distilled judge like Prometheus 2 for throughput) to score semantic quality. Zylos Research (2026) found 57% of production agent teams now gate quality with judge LLMs at runtime. Calibrate judges against human annotation to catch systematic bias.
- **Multi-layer grading** — separate assertions into decidable checks (code runs without errors, API returns expected shape) and semantic checks (response is helpful, tone is appropriate). The first layer can be fast and deterministic; the second layer requires a judge. Anthropic's eval terminology maps this as: Task → Trial → Grader → Assertion.
- **Online canary with trace analysis** — route a fraction of production traffic through the new agent version and compare traces. Lucidic (YC W25) built time-travel trajectory debugging specifically for this: cluster production failures, replay exact trajectories, and surface where tool calls or LLM decisions diverged from expected behavior.
- **Four operational constraints as first-class metrics** — latency, cost per task, token efficiency, and tool reliability are evaluation targets, not just infrastructure concerns. InfoQ's practitioner survey found that teams that only track accuracy miss where agents are expensive or slow in ways that undermine business value.

## Evidence

- **Anthropic Engineering Blog:** "Demystifying evals for AI agents" — defines core eval terminology (Task, Trial, Grader, Assertion) and recommends CI-gated eval pipelines tied to model/prompt changes. Published January 9, 2026. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **arXiv KDD 2025 Survey (Mohammadi et al.):** Two-dimensional taxonomy of agent evaluation — evaluation objectives (behavior, capabilities, reliability, safety) × evaluation process (interaction modes, datasets, metric computation, tooling). Highlights that enterprise-specific challenges (role-based data access, dynamic long-horizon interactions, compliance) are systematically overlooked by current benchmarks. — https://arxiv.org/abs/2507.21504
- **Zylos Research (April 2026):** Field survey found 57%+ of production agent teams use LLM-as-judge at runtime for quality gating. Field has bifurcated into large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes and small distilled judges (Prometheus 2 7B, Patronus Lynx 8B) for high-throughput inline checks. — https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026
- **Hacker News Discussion (July 2025):** Practitioner `roadside_picnic` on eval strategy for a coding agent: start with hundreds of evals, consolidate to high-signal subset over time. "Evaluations are *vital* for improving performance" — emphasized as a differentiator between teams that ship confidently and teams that ship and hope. — https://news.ycombinator.com/item?id=44712315
- **Langfuse Engineering:** Four dimensions of agent quality — trajectory, tool use, task completion, multi-turn quality. Recommends code checks for decidable assertions, LLM-as-judge for semantic judgments, and human annotation to calibrate the judge. — https://langfuse.com/resources/engineering/ai-agent-evaluation
- **GitHub reaatech/agent-eval-harness:** TypeScript production harness with trajectory evaluation, 13+ tool-use issue types, cost/latency tracking, golden trajectory comparison, and CI regression gates. — https://github.com/reaatech/agent-eval-harness
- **YC W25 Launch — Lucidic:** Agent observability platform for production debugging — time-travel trajectory replay, trajectory clustering, and step-level event capture. — https://news.ycombinator.com/item?id=44735843
- **InfoQ (March 2026):** "Evaluating AI Agents in Practice" — task success rates, graceful recovery, and consistency under variability matter more than curated benchmark scores. Hybrid evaluation (automated + human) is non-negotiable for production agents. — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned

## Gotchas

- **Benchmark scores don't predict production behavior** — the KDD survey and Springer's review both found that high benchmark scores (AgentBench, WebArena, SWE-bench) frequently fail to transfer to real deployments. Private evals on your actual tool stack are worth more than leaderboard rankings.
- **Non-determinism requires multiple trials** — run each task 3–5 times and track variance, not just pass rate. An agent that works 1/5 times is not a working agent.
- **Judge model bias is real** — judges prefer verbose, confident-sounding outputs even when conciseness is a goal. Calibrate against human ground truth and track judge accuracy over time.
- **Golden trajectories go stale** — tools, APIs, and user expectations change. Re-record reference trajectories regularly or your regression suite becomes a false sense of security.
- **Evaluating the final output misses tool-call drift** — an agent can reach the right answer via a flawed reasoning chain, then fail when the next step depends on that reasoning. Score the trajectory, not just the destination.
