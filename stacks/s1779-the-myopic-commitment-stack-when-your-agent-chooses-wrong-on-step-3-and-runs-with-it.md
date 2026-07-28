# S-1779 · The Myopic Commitment Stack

Your agent starts a complex task: research 20 competitors, draft a market brief, and ship a report. On step 3, it picks a suboptimal search query. On step 7, it decides to classify companies by "market cap" instead of "funding stage." On step 12, it has already written 60% of the report around a flawed taxonomy. It will not recover. The context is full, the direction is locked, and the agent keeps reasoning confidently forward. This is the myopic commitment failure: step-wise reasoning generates locally optimal choices that are systematically amplified over time and difficult to recover from once committed.

## Forces

- **Step-wise reasoning is locally greedy by default.** Chain-of-thought generates high-confidence intermediate outputs that feel authoritative but were never evaluated against downstream consequences. The agent trusts its own reasoning.
- **Context pressure compresses reflection.** As the context window fills (last 30% of session = ~50% of tokens per AgentMarketCap), the agent increasingly optimizes for closure — finish the task using what you have — rather than re-evaluating the frame.
- **Early taxonomy errors compound.** A wrong classification scheme chosen at step 3 propagates through all subsequent steps. Unlike a human who would pause and say "wait, we're organizing this wrong," the agent lacks a mechanism to trigger re-decomposition once committed.
- **Multi-agent handoffs amplify the problem.** When a planner agent locks in a work plan and hands it to executor agents, the executor agents cannot easily challenge the plan's premises — they can only work within it.
- **Compression trades reflection for tokens.** Context compression (60-80% token reduction per AgentMarketCap) aggressively removes old reasoning steps, making it harder to audit why a particular direction was chosen.

## The move

**Explicit lookahead before commitment, with enforced re-evaluation gates at horizon boundaries.**

- **Split the reasoning loop into plan-and-execute phases.** The planning phase (a separate LLM call or agent) does future-aware evaluation: for each proposed action, ask "what does success look like 5 steps from now?" before committing. The execution phase runs in a constrained context that can reference the plan but not re-derive it.
- **Introduce horizon checkpoints.** Every N tool invocations (tune to your task — 5-15 is common), force a re-evaluation call: "Given what we know now, is the current approach still the right one? If not, restart from the last checkpoint." This is the FLARE principle (Future-aware Lookahead with Reward Estimation) — enforce explicit lookahead, value propagation, and limited commitment in a single model call.
- **Decompose DAG-style, not chain-style.** Instead of sequential steps (1→2→3→4), decompose into a directed acyclic graph where multiple branches can be explored in parallel and pruned based on evaluation at intermediate nodes. LangGraph-style DAG agents (vs linear ReAct agents) make this structural distinction explicit.
- **Store the goal, not just the history.** When compressing context, preserve the original goal statement and the top-level plan structure. This lets the agent re-ground if it drifts — the "why are we doing this" survives even when "what we did in steps 1-20" is evicted.
- **Use a critic agent for taxonomy and framing decisions.** Before the agent commits to a classification scheme, organizational structure, or query strategy, route that specific decision through a second LLM call that is explicitly instructed to challenge the frame, not execute it.

## Evidence

- **Research paper (arXiv 2601.22311):** "Why Reasoning Fails to Plan" — LLM-based agents exhibit step-wise greedy policies that are adequate for short horizons but fail in long-horizon planning. "Early myopic commitments are systematically amplified over time and difficult to recover from." FLARE (Future-aware Lookahead with Reward Estimation) consistently improved task performance, with LLaMA-8B + FLARE outperforming GPT-4o with standard step-by-step reasoning on multiple benchmarks. — [arXiv:2601.22311](https://arxiv.org/abs/2601.22311v1)

- **Research survey (Presba, LLC 2026):** "Context Window Degradation in Extended AI Interactions" — 28+ studies (2024-2026) found agentic task success declining from 87.3% to 50.6% over extended interactions. 39% average multi-turn performance loss vs single-turn baselines. Behavioral consistency drops 30%+ within 8-12 turns. "Context should be treated as a precious, finite resource, not an expandable canvas." — [presba.com/research/context-degradation](https://presba.com/research/context-degradation.html)

- **Engineering blog (Comet ML, January 2026):** "Multi-Agent Systems: Architecture, Patterns, and Production Design" — "When critical information gets buried in long contexts, model performance on reasoning tasks degrades by as much as 73%." Multi-agent decomposition was adopted specifically to address this: by splitting monolithic reasoning across specialized agents, each agent operates in a shorter context window with less degradation. — [comet.com/site/blog/multi-agent-systems](https://www.comet.com/site/blog/multi-agent-systems)

- **HN Discussion (6 months ago):** "Agentic Frameworks in 2026: Less Hype, More Autonomy" — "The real differentiator in 2026: how a framework models time, memory, and failure. Agents that cannot reason over long horizons or learn from their own mistakes collapse under real workloads." LangGraph-style DAG-based agents cited as superior for long-horizon tasks because they make state flows explicit and inspectable, enabling re-planning. — [news.ycombinator.com/item?id=46509130](https://news.ycombinator.com/item?id=46509130)

- **Engineering blog (AgentMarketCap, April 2026):** "Agent Context Window Compression: The 2026 Production Guide" — "The last 30% of session = nearly 50% of total tokens." Context exhaustion identified as the #1 silent production killer. Teams implementing compression reduce token spend 60-80% vs uncompressed baseline, but aggressive compression without preserving goal-state causes re-grounding failures. — [agentmarketcap.ai/blog/2026/04/10/agent-context-window-compression-techniques-2026](https://agentmarketcap.ai/blog/2026/04/10/agent-context-window-compression-techniques-2026)

## Gotchas

- **Forcing re-evaluation too often burns tokens and creates indecision.** The right checkpoint interval depends on task length — too few checkpoints = myopic lock-in, too many = the agent never finishes. Profile on your actual task mix.
- **Checkpoint state must include the original goal.** If you checkpoint only the current work product, you lose the ability to re-evaluate whether the work product is still the right goal. Store the goal alongside the state.
- **A critic that always agrees is worse than no critic.** The critic prompt must be adversarial by design — specifically instructed to find the flaw in the current frame, not to validate it.
- **DAG decomposition increases orchestration complexity.** The benefit of explicit branches comes with the cost of needing a supervisor agent that can evaluate branch outputs and decide which path to pursue. Don't DAG if your task is truly linear.
- **Context compression is a tradeoff, not a solution.** Compression reduces the symptom (token bloat) but doesn't address the root cause (step-wise greedy policy). Use compression as a complement to lookahead gates, not a replacement.
