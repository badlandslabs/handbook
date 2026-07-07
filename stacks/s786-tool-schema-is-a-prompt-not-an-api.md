# S-786 · Tool Schema Is a Prompt, Not an API

When you expose a new capability to an agent, the instinct is to write an OpenAPI spec or a JSON function definition the way you'd design an API for a developer. That's the wrong model. The tool schema the agent reads is evaluated at inference time — it competes with your system prompt, conversation history, and context for the model's attention. Bad schema design doesn't cause a 400 error; it causes silent misbehavior and wasted tokens.

## Forces

- **Tool count vs. context budget** — giving an agent 50 tools can consume 50,000+ tokens before any real work starts (Anthropic, Nov 2025)
- **Schema ambiguity vs. hallucination** — agents guess at parameter shapes from schema alone; every ambiguous field name is a new failure mode
- **Stability vs. expressiveness** — humans read docs; agents read schemas and have no way to ask clarifying questions
- **Atomicity vs. composability** — one broad tool is easier to define but harder for the model to invoke correctly; many narrow tools create chain complexity

## The Move

Design tool schemas like prompts, not APIs.

- **Name tools with verb_noun_by_key** — `get_order_by_id` beats `get_order` with an ambiguous identifier field. Avoid overloaded verbs like `process` or `handle` that tell the model nothing about the actual effect. Destructive tools should sound destructive: `delete_project` not `remove_project_reference` — models under-weight risk on softly-named tools.
- **Keep schemas tight and self-contained** — every parameter needs a description, type, and constraint. Enums beat free-text strings. Required fields should actually be required. A field with no description is invisible to the model in all the ways that matter.
- **Prefer a few expressive tools over a catalog of thin wrappers** — a former Manus backend lead (r/LocalLLaMA, 2026) documented that a single `run(command="...")` tool exposing Unix-style shell commands outperformed a full function-calling catalog with dozens of tools. The model reasons better about a familiar interface than a custom one.
- **Expose progressively, not upfront** — instead of loading all tools at session start, use on-demand tool discovery. Anthropic's advanced tool use (Nov 2025) introduced a Tool Search Tool exactly for this: the agent searches for relevant tools when it encounters a gap, rather than carrying the full catalog in context.
- **Add tool use examples, not just schemas** — schema-only definitions fail to express usage patterns. Anthropic's advanced tool use also added Tool Use Examples: demonstrated correct invocations that show the model not just what the tool expects but how it's typically used.
- **Compose tools in code, not in context** — for multi-step tool orchestration, write programmatic tool calling (code-driven execution) rather than expecting the model to chain tools through conversation. This avoids intermediate results polluting the context window.

## Evidence

- **Engineering Blog:** Anthropic "Introducing Advanced Tool Use" — tool definitions consuming 50,000+ tokens before work begins; introduces Tool Search Tool, Programmatic Tool Calling, and Tool Use Examples as three-part solution — [URL](https://www.anthropic.com/engineering/advanced-tool-use) (Nov 2025)
- **Primary Research / Reddit:** Former Manus backend lead on r/LocalLLaMA — abandoned function calling entirely after 2 years; replaced with single `run(command)` Unix-style tool — [URL](https://www.reddit.com/r/LocalLLaMA/comments/1rrisqn/i_was_backend_lead_at_manus_after_building_agents/) (Mar 2026)
- **Engineering Guide:** TeachYou Academy "Tool Design for AI Agents" — documents naming conventions, schema descriptions, and how ambiguous field design causes model hallucination — [URL](https://www.teachyou.ai/blog/tool-design-for-ai-agents) (May 2026)

## Gotchas

- **Describing parameters in natural language is not optional** — the `description` field on every parameter is what the model uses to decide what to pass. Leave it empty and the model guesses.
- **Optional parameters that should be required are a silent failure** — the model will happily call your tool with incomplete data and get back garbage.
- **Changing a tool schema can break agents silently** — if the agent cached a pattern for calling your tool, a schema change may not invalidate it. Version your tool definitions and monitor for behavioral regressions.
- **Tool naming inconsistency across a toolset is a reliability tax** — if nine tools use `verb_noun` and one uses `noun_verb`, that one tool will be called less reliably simply because it breaks the pattern the model has learned.
