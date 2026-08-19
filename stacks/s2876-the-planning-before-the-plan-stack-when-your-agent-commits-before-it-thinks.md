# S-2876 · The Planning-Before-the-Plan Stack — When Your Agent Commits Before It Thinks

Agents that plan externally — maintaining a visible scratchpad, a separate evaluator, and a defined deliberation phase — consistently outperform agents that rely on the model's internal reasoning alone. This became starkly visible in 2025-2026 as Anthropic's three-agent harness research, Cognition AI's Devin rebuild, and the broader emergence of reasoning models all converged on the same lesson: the architecture surrounding the model matters as much as the model itself. The scaffolding is the product.

## Forces

- **Internal reasoning is opaque and inconsistent.** Models that "think out loud" do so in unstructured output that the harness can't parse, verify, or act on. There's no way to tell if the model reasoned correctly or confidently hallucinated a plan.
- **The reasoning model shift moved the problem, not eliminated it.** OpenAI o1/o3 and their successors moved chain-of-thought inside the API — but that reasoning stays inside. When you need to share a plan with tools, a human reviewer, or a multi-agent sibling, internal reasoning is a black box.
- **Agents conflate speed with correctness.** Without an external evaluator, agents rate their own work highly even on tasks where they're objectively wrong. This self-evaluation bias compounds across multi-step runs.
- **Context anxiety makes agents quit early.** When a model perceives it's approaching its context limit — even with thousands of tokens remaining — it prematurely wraps up work. This behavior is consistent across providers and model generations.

## The Move

**Structure the reasoning loop as a first-class component of the harness, not an emergent property of the prompt.**

- **Run a Planner agent before any generation.** Given a user goal, the Planner expands it into a task spec: what needs to be built, what constraints apply, what "done" looks like. The Planner focuses on product context and high-level structure — not granular implementation steps, which over-specification sends cascading errors downstream. Evidence: Anthropic's three-agent harness starts every session with a Planner that produces a structured artifact shared via a shared file on disk, not context.

- **Separate generation from evaluation at the agent level.** The Generator does the work. A separate Evaluator — a distinct LLM call, not the same model's self-assessment — grades the output against pre-defined criteria. Anthropic found this single separation was "a strong lever" against self-evaluation bias. For frontend design, their Evaluator uses Playwright MCP to navigate the live page and critique design quality, originality, craft, and functionality in concrete, gradable terms. For code tasks, the Evaluator runs tests and linters as structured feedback, not vibes.

- **Externalize the scratchpad as a shared artifact.** Rather than relying on the model's internal reasoning trace, write intermediate reasoning to a file or structured log that persists across turns. The scratchpad serves three functions: it lets the Planner revisit earlier reasoning, it lets the Evaluator audit the thought chain, and it gives the Generator a reference point that doesn't consume context tokens. Manus's "chain-of-thought injection" technique (YC Library, 2025) specifically updates plans dynamically via an external scratchpad.

- **Give the Evaluator four calibrated criteria, not a rating scale.** Vague evaluation ("rate this output 1-10") produces inconsistent grades. Anthropic's generator-evaluator harness uses four named criteria specific to the domain: design quality, originality, craft, and functionality for UI work; correctness, style, and test coverage for code. Each criterion has few-shot examples of what a passing answer looks like.

- **Iterate the generate-evaluate loop 5-15 times per session.** One-shot generation followed by evaluation rarely converges. Production harnesses run 5-15 generate-evaluate cycles, with each cycle producing progressively refined outputs. Some multi-hour full-stack runs take up to four hours and reach 15 iterations before the Evaluator passes the output.

- **Address context anxiety explicitly in the harness design.** Rather than relying on the model to manage its own context, treat context as a finite resource under harness control. Strategies: tell the model its exact remaining context budget rather than letting it estimate, use structured context compaction that preserves task state over raw message history, and separate "long-term" context (task spec, evaluation criteria) from "short-term" context (current turn) so that neither crowds the other. Cognition AI rebuilt Devin (September 2025) specifically to combat context anxiety — they found the model consistently underestimated its remaining tokens and took shortcuts based on that misperception.

- **Select reasoning depth as a task-level dial, not a model-level property.** Reasoning models (o1, o3, DeepSeek-R1, Gemini Flash Thinking) give you compute-as-a-knob — more reasoning steps for harder problems. Fast/Slow (System 1/System 2) is the architecture pattern: use a fast, cheap model for simple classification and routing decisions, and scale to deeper reasoning only for tasks that hit policy complexity, multi-step logic, or novel edge cases. DeepSeek-R1 on MATH-500 reaches 97.3%; the same model on simple classification is both overpowered and overpriced.

## Evidence

- **Anthropic Engineering Blog (March 2026):** Three-agent harness (Planner + Generator + Evaluator) producing rich full-stack applications over multi-hour autonomous sessions. The architecture draws from GAN-style generator-evaluator loops. Key finding: separating the agent doing work from the agent judging it produces feature-rich applications compared to broken single-agent outputs. Iterations range from 5-15 per run. — [anthropic.com/engineering/harness-design-long-running-apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)

- **Inkeep Blog / Cognition AI (October 2025):** When Cognition AI rebuilt Devin for Claude Sonnet 4.5, they discovered "context anxiety" — the model took shortcuts when it believed it was running out of space, even with thousands of tokens remaining. The model consistently underestimated its remaining context budget. This behavior was observable in production before it had a name. — [inkeep.com/blog/context-anxiety](https://inkeep.com/blog/context-anxiety)

- **GitHub Gist — Celeste Anders (community, 2026):** Best practices for building an agent harness, consolidated from Anthropic and OpenAI research. Key principles: context windows are the constraint; structured artifacts are the solution. Repository is the single source of truth. Humans steer, agents execute. Verify before building. Simplify relentlessly — stray from conventions and the error rate jumps. — [gist.github.com/celesteanders/21edad2367c8ede2ff092bd87e56a26f](https://gist.github.com/celesteanders/21edad2367c8ede2ff092bd87e56a26f)

## Gotchas

- **Over-specifying the plan at the start defeats the purpose.** The Planner's job is to define scope and success criteria — not to pre-solve implementation steps. Teams that give the Planner excessive detail find that the Generator follows those decisions slavishly, and the Evaluator never gets to exercise judgment. The harness should encode intent, not procedure.

- **Self-evaluation in the generator is invisible failure.** When the same model generates and evaluates, it rates flawed work highly because it has already committed to the output. This is not a prompt issue — better prompts don't fix it. The fix is structural: use a separate model call, or at minimum a separate reasoning pass, for evaluation.

- **Reasoning depth configured globally creates cost blow-up.** Setting a reasoning model to "maximum depth" for every task means you're paying for 10,000-token reasoning traces on tasks a 3-turn ReAct loop could solve. Route reasoning depth per task — cheap models for routing, expensive reasoning for genuinely hard problems.

- **Scratchpad content that isn't structured becomes noise.** Writing raw free-text reasoning to a scratchpad file is better than nothing, but it's not the same as structured artifacts. If the scratchpad can't be parsed by the Evaluator or used to resume an interrupted session, it's a diary, not infrastructure.
