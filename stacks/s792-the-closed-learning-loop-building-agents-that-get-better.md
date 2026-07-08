# S-792 · The Closed Learning Loop: Building Agents That Get Better

Your agent works great on day one. Six months later it's making the same mistakes. It completes tasks but never masters them. The gap is structural — most agents are stateless by design, discarding everything that made the current session productive. The fix isn't more context; it's a closed learning loop that turns experience into capability.

## Forces

- **Statelessness is the default, not a bug.** Most agent frameworks treat every invocation as a fresh start. Experience evaporates at session boundary, so agents rediscover what worked last week every Monday morning.
- **Skills are written, not earned.** Most "agent learning" means humans hand-crafting skills, prompts, or retrieval pipelines. The agent doesn't generate or prune its own capability layer — humans do it for it.
- **Evaluation without iteration is theater.** You can measure an agent's accuracy this week and compare it to last week, but if nothing in the system updates based on that comparison, the metric is just a scoreboard nobody plays from.
- **Self-improvement loops introduce new failure modes.** An agent that modifies its own behavior can compound errors, overwrite good skills with bad ones, or degrade over time — the opposite of learning.

## The move

Build a closed learning loop inside the agent — a subsystem that reads execution telemetry, evaluates skill performance, generates new capabilities from complex tasks, and prunes regressions. This is not a prompt tweak; it's a second process running alongside the agent's execution loop.

**The core components:**

- **Execution telemetry capture.** Every tool call, task outcome, and error gets logged with structured metadata (duration, success/failure, tool name, task type, user model context). Without this, the loop has no signal to learn from.
- **Skill library as first-class state.** Skills are not hardcoded prompts — they're versioned, parameterized, and evaluated objects stored in a dedicated layer. The agent can read, write, and retire them. Hermes Agent stores skills at `~/.hermes/skills/` and evaluates them at a configurable cadence (defaults to weekly).
- **The Curator — autonomous evaluation and pruning.** A background process that grades skill performance using telemetry, consolidates overlapping skills, and deletes underperformers. The Curator reads usage data but does not modify execution behavior — it only mutates the skill library. In Hermes Agent, this runs as a daemon (`hermes curator run`) that outputs a structured diff of the skill library before applying it.
- **Autonomous skill generation.** After a complex task that required multi-step reasoning or tool orchestration, the agent generates a new skill from the successful trajectory. This skill encodes the procedure so it fires automatically next time a similar task arrives. Hermes Agent calls this `hermes skill create` and it can be triggered inline during task execution.
- **User model persistence.** Beyond task-level skills, the agent maintains a lightweight model of user preferences, communication style, and recurring patterns. Hermes Agent stores this as a `~/.hermes/memory/user_model.json` that's loaded on every session start. This is why the same Hermes instance "remembers" your workflow across weeks.
- **Session search with summarization.** FTS5 full-text search over past conversation sessions, with LLM-generated summaries as the retrieval surface. When the agent encounters a task similar to one from three months ago, it can surface the relevant session and learn from it. Hermes Agent exposes this via `hermes session search`.

## Evidence

- **GitHub README:** NousResearch/hermes-agent — 211k stars, MIT license. The repo implements the full closed loop: Curator (skill evaluation + pruning), autonomous skill creation, FTS5 session search, and persistent user model. "The only agent with a built-in learning loop — it creates skills from experience, improves them during use, nudges itself to persist knowledge, searches its own past conversations, and builds a deepening model of who you are across sessions." — [https://github.com/nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent)
- **Blog analysis:** Hermes Agent v0.12.0 summary — the Curator runs as a weekly cron that grades skill performance using telemetry, prunes underperformers, and consolidates related skills. "It generates skills from real work, prunes them weekly via an autonomous Curator, and persists a user model across sessions." — [https://dudarik.com/en/blog/awesome-hermes-agent/](https://dudarik.com/en/blog/awesome-hermes-agent/) (June 9, 2026)
- **Architecture deep-dive:** Autonomous Skill Curator documentation — "The curator occupies a unique position in the Hermes self-improvement loop: it is the only subsystem that both reads usage telemetry and mutates the skill library autonomously." — [https://zread.ai/NousResearch/hermes-agent/17-autonomous-skill-curator](https://zread.ai/NousResearch/hermes-agent/17-autonomous-skill-curator)

## Gotchas

- **The loop can degrade, not improve.** Without careful telemetry instrumentation, the Curator grades skills on noisy signals. An underperforming skill that gets called frequently looks successful by volume. Separate task-level success (did it complete?) from quality (did it complete well?).
- **Skill proliferation buries the agent.** Hermes Agent teams report that unmanaged skill creation leads to hundreds of skills competing for activation on similar tasks. The Curator's consolidation step is the most important part — don't skip it.
- **User model staleness.** The user model is a summary that goes stale. If a user changes workflow mid-session, the persisted model can actively mislead. Hermes Agent addresses this with periodic "nudges" — the agent asks itself whether the user model still matches, but this requires the user to confirm or correct.
- **Learning loops are not auditable by default.** When an agent modifies its own skill library autonomously, there's no git-style history unless you build it. Hermes Agent keeps a `~/.hermes/skills/.curator_history/` but teams operating in regulated environments need an approval gate before skill library mutations apply in production.
