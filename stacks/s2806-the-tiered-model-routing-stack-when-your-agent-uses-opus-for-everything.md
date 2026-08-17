# S-2806 · The Tiered Model Routing Stack — When Your Agent Uses Opus for Everything

You're paying $15/M tokens for a model to decide whether to search the web or format a date. Your routing logic costs more than your actual work. The agent completes every task — but at 10x the cost of a system that knew when to scale up and when to stay cheap.

## Forces

- **Cost vs. capability is not binary** — most agent tasks fall along a complexity spectrum, and a single model choice either overpays for simple work or under-delivers on hard tasks
- **Routing decisions are themselves LLM calls** — adding a classifier or router adds latency and cost; the overhead must be less than the savings from routing away from expensive models
- **Quality floors are real** — routing too aggressively to cheap models causes failures on tasks that looked simple but weren't (Unicode edge cases, ambiguous intent, multi-step reasoning that requires depth)
- **Context switching between models has hidden costs** — different models have different context sizes, token limits, and instruction-following behaviors; routing can break downstream tool calls
- **The routing logic itself can be wrong** — a model that misclassifies task complexity routes to the wrong tier, creating a failure mode that's hard to debug

## The move

Tiered model routing: use a small, fast, cheap model as a first-pass classifier to decide which model tier handles the task.

**Step 1 — Define two or three tiers:**
- **Fast tier:** Haiku-class models for classification, routing, formatting, extraction, simple transform, and any task where correctness is less critical than speed
- **Deep tier:** Sonnet/Claude-3.5/GPT-4o for complex reasoning, multi-step tool orchestration, design decisions, and any task where failure is costly
- **Optional super-tier:** Opus/Claude-3.7/GPT-4.5 for novel problems, architectural decisions, or tasks where you need the best possible output regardless of cost

**Step 2 — Route at the task level, not the call level:**
- Route each distinct sub-task to the appropriate tier
- A single agent session may span three tiers as it moves from intent classification → research → synthesis
- The router is itself a lightweight LLM call, not a heuristic or regex

**Step 3 — Budget the tiers:**
- Set per-tier token or cost budgets per session
- Track actual spend per tier in traces; route adjustments come from data, not intuition
- Hard cap the deep tier for routine tasks (e.g., "never call Opus for a date format")

**Step 4 — Fallback cascade:**
- If fast tier fails (low confidence, error, timeout), escalate to the next tier
- Record the escalation in the trace — the failure pattern itself is useful signal for tuning thresholds

## Evidence

- **Reddit r/AI_Agents practitioner stack (2026):** The most-upvoted real-world stacks use exactly this tiered pattern — Haiku for classification/routing, Sonnet for daily work, Opus reserved for complex planning/reasoning. Commenter u/jdrolls: *"Claude (Haiku) for classification and routing decisions — fast, cheap, accurate enough. Sonnet for most tasks. Opus only when I actually need depth."* — [Reddit r/AI_Agents thread](https://www.reddit.com/r/AI_Agents/comments/1rqnv3a/)
- **AWS Strands agentic framework (2026):** AWS's Strands Evals documentation describes automatic model selection as a core capability — the framework routes between model tiers based on task complexity signals from the agent's trace. The framework defaults to letting the agent's own reasoning determine when to escalate, with configurable cost ceilings per tier. — [AWS Strands Evals blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-for-production-a-practical-guide-to-strands-evals)
- **Local Ollama practitioner community (r/LocalLLaMA):** Community discussions on local agent deployment show practitioners routing between Qwen 3 (fast, tool calling) for classification and reasoning, and larger local models (Llama 3.3 70B, Mistral) for complex tool orchestration — citing cost savings of 60-80% compared to single-tier frontier model usage. One practitioner explicitly noted: *"using qwen3 for routing saves me from burning $0.03 per classification call"* — [r/LocalLLaMA + r/ClaudeAI multi-agent discussion](https://github.com/open-multi-agent/open-multi-agent/issues/3)

## Gotchas

- **Routing adds latency for short tasks** — a 50ms router + 200ms fast model is slower than a 500ms direct Opus call; profile before optimizing
- **Task complexity is hard to predict** — a "simple" email classification can require understanding context from 20 previous emails; the router needs enough context to make an informed decision
- **Model-specific tool schemas break routing** — if your deep tier uses Claude's native tools and your fast tier uses OpenAI's function calling format, routing across tiers requires adapter logic
- **Hard caps kill graceful degradation** — if the deep tier hits a rate limit and you've hard-capped routing, the fast tier fails the complex task instead of retrying or escalating; build soft caps with escalation paths
