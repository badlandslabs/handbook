# S-2737 · The Eval-as-Production-Infrastructure Stack — When Your Agent Passes the Demo But Fails Everything Else

Your agent nails the demo. It answers the happy-path questions, follows the script, and leadership is impressed. Then production traffic hits: it hallucinates tool parameters, loops forever on ambiguous input, and your monitoring shows no idea anything went wrong because you never measured the right things. The demo tested the wrong axis of agent quality, and the gap between "works in demo" and "works in production" swallows the project.

## Forces

- **Classical metrics don't reach agents.** Accuracy, BLEU, and exact-match measure single-turn outputs. They say nothing about whether a tool was called correctly, whether the agent gave up when it should have retried, or which specific step caused a failure three turns later.
- **The trajectory is the unit of work, not the turn.** An agent's quality is in the path it takes — the sequence of tool calls, decisions, and mid-course corrections. A single good output can mask a terrible reasoning chain, and a single bad turn can corrupt everything downstream.
- **Production traffic reveals failure modes demos never show.** Ambiguous inputs, rate limits, tool timeouts, context pollution, and budget overruns don't appear in a curated demo scenario.
- **Human review doesn't scale.** You cannot have a human in the loop for every agent decision, but you also can't trust the agent to self-evaluate without external grounding.

## The Move

Treat evaluation as load-bearing production infrastructure — not a post-launch checkbox. The specific patterns that hold up across 2025–2026 primary sources:

- **Use LLM-as-judge at three runtime boundaries, not just at the end.** Place verification gates at: (1) input reception — is this request well-formed and within scope? (2) mid-work checkpoint — is the agent's current trajectory converging toward the goal? (3) output emission — does the final response satisfy the criteria? Zylos Research (2026) found 57%+ of production agent teams now use judge LLMs at runtime, up from niche adoption in 2024. A model that struggles to produce perfectly factual answers can still reliably detect when an answer contradicts a retrieved document — classifying is simpler than generating.
- **Use small distilled judges for cost efficiency.** GPT-4-class evaluation is accurate but expensive at scale. Small distilled judges (Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) deliver 97% cost reduction at 0.88–0.95 accuracy relative to GPT-4-based evaluation. Reserve large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification gates. This is a production cost story, not just a technical one.
- **Test trajectories, not units.** Mock tool results and verify the agent makes correct decisions across multi-step workflows. Zalor (Show HN, 2025) implements this by simulating real user personas against the agent and scoring the full interaction sequence — catching breakage from system prompt tweaks, framework swaps, and model updates before deployment. Traditional unit testing with fixed assertions doesn't map to probabilistic, multi-turn behavior.
- **Separate self-correction from self-grounding.** Self-correction via prompting alone ("check your work") degrades performance on reasoning tasks — the agent doubles down on errors. Self-correction only works when grounded in external feedback: retrieval, tool output, or a judge LLM. Build the feedback loop, not just the instruction.
- **Track cost per workflow and set hard budget limits.** An uncapped agent will surprise you with bills. Log every turn, tool call, and result. Without traces, you're flying blind when things go wrong. A circuit breaker on total LLM calls per session prevents runaway loops.

## Evidence

- **Research report:** Zylos Research (April 2026) — 57%+ of surveyed production agent teams use judge LLMs at runtime for quality gating and hallucination defense; small distilled judges achieve 0.88–0.95 accuracy vs GPT-4-based evaluation at 97% cost reduction; intrinsic self-correction (ungrounded prompting) degrades reasoning task performance. — [zylos.ai/research](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)

- **HN Show launch:** Zalor AI — automated testing platform for AI agents that simulates real user personas against the agent, scores interaction sequences, and integrates with GitHub Actions for per-PR reliability checks. Solves the "agents break when you tweak system prompts or swap models" problem. — [HN thread](https://news.ycombinator.com/item?id=47270208) · [zalor.ai](https://agents.zalor.ai/)

- **Engineering blog:** Wenxue Cao (April 2026) — rubric design, bias-aware judge prompts, step attribution, and automatic re-evaluation for agentic AI systems using a Claude Code skill framework. Classical metrics (accuracy, BLEU, exact-match) fail to measure tool call correctness, retry behavior, and failure attribution across trajectories. — [wenxuec.github.io](https://wenxuec.github.io/project-llm-judge.html)

- **Engineering blog:** Harsh Rastogi, AI Product Engineer (March 2026) — production failure modes: tool parameter hallucination (agent calls right tool with wrong params), loop detection via circuit breakers, cost tracking per workflow, structured logging of every turn. — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Research guide:** thinking.inc (2026) — Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation and monitoring of agent systems, not model capability gaps. — [thinking.inc](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)

## Gotchas

- **Evaluating the output hides the reasoning chain.** A single good final response can mask a terrible trajectory — wrong tool called first, wasted steps, recovered by luck. Score the path, not just the destination.
- **Golden datasets go stale fast.** Agent behavior changes with model updates, prompt changes, and upstream API changes. Eval sets need continuous refresh, not one-time construction.
- **Judge LLMs inherit model biases.** A judge trained on or evaluated by the same family of models as the agent being judged may systematically favor that model. Use cross-model judges for high-stakes evaluation.
- **Human-in-the-loop gates are frequently misplaced.** Teams either put humans too early (blocking automation) or too late (letting bad outputs reach users). The right placement depends on stakes and latency budget — not on convenience.
