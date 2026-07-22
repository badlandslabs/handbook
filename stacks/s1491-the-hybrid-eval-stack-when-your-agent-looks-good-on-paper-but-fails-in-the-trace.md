# S-1491 · The Hybrid Eval Stack — When Your Agent Looks Good on Paper but Fails in the Trace

Your eval suite returns 91%. You feel confident. Then you pull a random production trace and watch the agent call the wrong tool, succeed anyway by accident, and cost 3x the expected tokens. The final-answer score lied to you — it had no idea what happened inside the trajectory.

The core tension: agents are trajectory systems. Final-answer scoring tells you if the destination was right. It says nothing about whether the path made sense, whether the agent was looping, or whether it was one lucky break from disaster.

## Forces

- **Final-answer scoring is necessary and insufficient.** A right answer reached via the wrong tool chain is a liability — it will fail on edge cases that final-answer scores never surface.
- **Standard benchmarks don't capture production reality.** AgentBench, WebArena, SWE-bench, and ToolBench measure narrow task completion against controlled APIs. Production agents use real tools, handle noisy inputs, and face adversarial users. Benchmark scores have weak correlation with production behavior.
- **The eval pyramid has three layers, and most teams only use one.** Final-answer scoring → trajectory analysis → per-turn classification. Most teams stop at the first. The ones catching failures early use all three.
- **Human evaluation is still 74% of production practice** — and it's a bottleneck, not a signal problem. Teams want automated alternatives but can't yet trust them enough.
- **LLM-as-judge has systematic failure modes.** Length bias, position bias, self-preference, and non-determinism make it unreliable as a sole scorer, yet it remains the dominant automated approach.

## The move

Build a three-layer evaluation system that matches the three things agents produce: the final answer, the trajectory, and each individual turn.

**Layer 1 — Final-answer eval:** Score the last message against a ground-truth answer or expected outcome. This is your pass/fail gate. Keep it but don't trust it alone.

**Layer 2 — Trajectory eval:** Score the entire agent run end-to-end. Did it use the right tools in the right order? Did it recover from failures? Did it overshoot the step budget? LangSmith traces and Phoenix/OpenTelemetry spans are the standard capture layer here.

**Layer 3 — Per-turn classification:** Run a lightweight classifier on every individual turn. Labels like `tool_call_correct`, `is_looping`, `policy_violation`, `retrieval_irrelevant` catch what trajectory-level scoring misses. Anthropic's Reflexes framework uses per-turn classifiers with <90ms latency — fast enough to gate production decisions.

**Synthetic data as eval fuel:** When you don't have enough real production traces, generate synthetic eval cases using an LLM to model plausible inputs. The critical loop is generate → critique → filter → generate. LangChain's harness-engineering approach treats the eval set itself as the artifact being optimized. Target "surface more distinct failure modes per unit of generation cost."

**Golden dataset construction:** Curate a test set from four sources — 40% historical production traces, 30% expert-authored cases, 20% synthetic generation, 10% user-testing. Annotate with ground-truth answers, label relevant documents, and enforce diversity via similarity scoring. Target 100–500 cases for focused agent evals; scale to thousands for broad coverage.

**LLM-as-judge with guardrails:** Use it for offline scoring on a sample, not real-time decisions. Correct for length bias (normalize by answer length), position bias (swap order and average), and self-preference (use a different model family than the agent). Pair it with human review on disagreements.

**Observability as the eval infrastructure:** Instrument every agent with OpenTelemetry tracing. Land traces directly into a queryable store (LangSmith, Phoenix/arize, Databricks Unity Catalog). Use production traces as the primary source for eval dataset expansion — sample 5–10% of sessions for human review, and route the highest-confidence failures back into the golden set.

## Evidence

- **ICML 2026 empirical study (CAP/MAP):** Surveyed 306 practitioners across 26 domains. Found 74% of deployed agents rely primarily on human evaluation, 70% use off-the-shelf models without fine-tuning, and 68% cap execution at 10 steps before human intervention. Top challenge: reliability over time. — [arxiv.org/abs/2512.04123](https://arxiv.org/abs/2512.04123) / [IBM Research CAP](https://research.ibm.com/publications/characterizing-agents-in-production)

- **Anthropic engineering post (Jan 2026):** Distinguishes three eval layers — task (defined inputs + success criteria), trial (repeated attempts), and grader (scoring logic). Documents per-turn classifiers as a classification problem with labels like `jailbreak_attempt`, `is_agent_looping`, `policy_violation`. Notes LLM-as-judge failure modes (length/position/self-preference bias). — [Anthropic Engineering: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Survey on Evaluation Frameworks (2025):** Reviewed AgentBench, ToolBench, WebArena, SWE-bench, and others. Found benchmark-to-production correlation is weak: prior benchmarks evaluate short-horizon single-step tasks with toy APIs in controlled sandboxes, while production evaluates long-horizon multimodal workflows with real tools in open-world environments. Recommends production teams build custom eval frameworks aligned to their specific tool chains and user-facing failure modes. — [Maxim AI: Survey of Agent Evaluation Frameworks](https://www.getmaxim.ai/blog/llm-agent-evaluation-framework-comparison)

- **InfoQ article (March 2026):** Documents hybrid eval as non-negotiable for production. Operational constraints — latency, cost per task, token efficiency, tool reliability, policy compliance — are first-class eval targets, not afterthoughts. Red teaming, PII handling, and permission boundary testing are as critical as accuracy. — [InfoQ: Evaluating AI Agents in Practice](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **HN Ask: Production monitoring (2025):** Practitioners share tools: AgentShield for execution tracing + risk detection, Phoenix for OpenTelemetry-based span capture, LangSmith for trace-to-eval pipelines. Root concern: without step-by-step visibility, agents that make dangerous tool calls (database wipes, data deletions during code freezes) go undetected until the incident. — [HN Ask: How are you monitoring AI agents in production?](https://news.ycombinator.com/item?id=47301395)

## Gotchas

- **Evaluating the final answer alone is cargo-cult testing.** A high final-answer score can coexist with a catastrophic trajectory. The agent that calls `DELETE DATABASE` and then retries to success still scores well.
- **Synthetic data without critique loops amplifies your agent's biases.** Generate-only pipelines produce eval cases that look like the agent's training distribution — they won't surface the edge cases that actually fail in production.
- **LLM-as-judge as your only automated scorer is a false economy.** It catches obvious failures but misses systematic ones, and it scores differently across runs. Pair it with deterministic checks (regex, JSON schema validation, tool-call signature matching) for the cases where you know what "correct" looks like.
- **Sampling 100% of production traces for human review doesn't scale.** The practical solution is probabilistic sampling with confidence-weighted routing — high-risk traces (new tool, unusual user type, high token count) get higher sampling priority.
