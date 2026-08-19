# S-2848 · The Golden Trace Stack — When Your Agent Always Works in Your Terminal and Always Fails in Production

An agentic system that has no evaluation is a system you are flying blind. It works on your examples, fails on theirs, and you find out when users complain. The **Golden Trace** problem: teams build sophisticated agents but ship them without a systematic way to know if they're getting better or worse across code changes, model swaps, and production traffic.

## Forces

- **Agents are non-deterministic** — the same input can produce different trajectories, making "did it work?" genuinely hard to answer. Unlike traditional software where same input = same output, agent outputs are probabilistic and path-dependent.
- **You can only catch what you measure** — but knowing *what* to measure for agents is itself a discipline most teams haven't built. Task success, tool selection, recovery behavior, cost, latency, and user trust all pull in different directions.
- **Evals go stale fast** — prompt iteration contamination is the most common failure mode. You read a failing eval case, fix the prompt, and now you've overfit to those exact examples. The eval passes but the real capability hasn't improved.
- **The eval ecosystem is fragmented** — Braintrust, Promptfoo, DeepEval, Langfuse, Arize Phoenix, OpenAI Evals, custom scripts — no gold standard exists. One HN thread summed it up: "very, very heterogeneous and fast moving space."
- **Most teams evaluate on vibes** — the vast majority of AI companies assess model and agent quality mostly by feel, not systematic measurement. This works until production users expose edge cases that "vibes" never caught.

## The move

Build a layered evaluation system with three tiers that catch what each other misses:

- **Offline evals on a golden dataset** — a curated set of test cases drawn from real production traces, held static and never touched during development. Run this before every meaningful code or prompt change as a CI gate. Rotate cases in from production logs, never the other way around. Separate "development eval" (iteration fuel) from "golden eval" (shipping gate) — same principle as train/test split in ML.
- **LLM-as-judge for subjective quality** — for responses where correctness isn't binary (tone, coherence, helpfulness), use a separate LLM grader with a rubric that defines what "good enough" looks like. The judge model should be different from the model being evaluated, and should receive the full trajectory — not just the final output. Combine with deterministic rule assertions for measurable behaviors (did it call the right tool? did it respect the output format?).
- **Production trace monitoring** — instrument your agent with structured logging of every trajectory: tool calls, intermediate outputs, reasoning steps, cost, and latency. Ingest into an observability platform (OpenLLMetry + Clickhouse/Postgres, or tools like Langfuse/Arize Phoenix/Laminar) to surface failure patterns in aggregate. The goal: catch failures before users report them.
- **Human review queue for ambiguous cases** — route low-confidence outputs or edge cases to human annotators. Use these to grow the golden dataset. Each human-reviewed case is a new test case for the CI gate.

## Evidence

- **Research paper:** MAP Study (Measuring Agents in Production) — first large-scale systematic study of production agents (306 practitioners, 20 case studies, 26 domains). Key finding: 70% of teams use off-the-shelf models with no fine-tuning, yet only 20% report applying formal reliability metrics. The majority evaluate success by whether the agent "produced correct, high-quality responses" — not by structured metrics. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)
- **Engineering post:** Anthropic's "Demystifying Evals for AI Agents" (Jan 2026) — defines the core vocabulary: tasks, trials, graders, transcripts (trajectories), and outcome/step-level scoring. Recommends combining deterministic graders for measurable behaviors with LLM-as-judge for subjective quality, and emphasizes that evals must cover the *trajectory*, not just the final output. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Community discussion:** HN "Ask: How are people doing AI evals these days?" (30 points, 43 comments, ~5 months ago) — practitioners reported using Braintrust, Promptfoo, DeepEval, Langfuse, and "duct-taped scripts." Consensus: existing benchmarks are considered inadequate ("cheap knockoffs"). The thread's most-upvoted insight: "What I've noticed is that it's hard to measure outputs that aren't binary right or wrong." — [news.ycombinator.com/item?id=47319587](https://news.ycombinator.com/item?id=47319587)

## Gotchas

- **Don't let your golden dataset become a training set.** Every time you read a failing eval case and modify your prompt to pass it, you've contaminated the dataset. Treat the golden set as a read-only artifact. Growth comes from adding new production-captured cases, not from editing existing ones.
- **LLM-as-judge has a reliability problem.** The judge model can be biased in favor of the model being judged (same family), or overly harsh on creative outputs that are actually useful. Calibrate your grader against human-labeled examples and use multiple judges with a rubric, not a single open-ended judgment call.
- **Offline evals and production reality diverge.** An agent that scores 94% on your eval set can still fail catastrophically on production traffic if your eval set under-represents the distribution of real user inputs. Cross-reference offline eval trends with production trace monitoring — both are necessary, neither is sufficient.
- **Cost and latency are part of quality.** Teams often optimize for task success while ignoring that a "successful" agent call costs $2.50 and takes 45 seconds. A practical quality metric should include cost-per-task and p95 latency alongside success rate.
