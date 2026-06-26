# S-16 · Prompting

How to write the instruction itself so the model does what you meant. Where [S-13](s13-context-engineering.md) decides *what tokens* go in the window, this is *how you phrase* the ask.

## Forces
- The same prompt ported across model families silently loses quality — they want different things
- Advice that helped older models ("think step by step," always add examples) can now *hurt* reasoning models and inflate cost
- Examples are not free — every few-shot example is tokens you pay for on every call
- A model reads your instructions and your data as one stream; blur the line and it follows your data as if it were instructions

## The move

- **Zone every prompt: instructions, data, examples.** Keep the three visually separate. This is the one habit that survives every model swap and blocks the "data read as instruction" failure.
- **Match structure to the model family.** Instruction-tuned models like structure and a few examples. Reasoning models want *atomic* prompts — clear task, tight success criteria, then get out of the way.
- **Don't tell a reasoning model to "think step by step."** It already reasons internally; explicit chain-of-thought wastes tokens and can degrade the answer. Reserve CoT for cheaper non-reasoning models where it still earns its keep. See [R-02](../frontier/r02-reasoning-models.md).
- **Treat few-shot as a deliberate choice, not a default.** Use 3–5 examples when format, pattern, or style precision matters (e.g. structured extraction). Skip it when the instruction already carries the load — examples cost tokens ([Law 2](../laws.md)).
- **Know your family's dialect.** Claude: XML tags (`<instructions>`, `<context>`, `<example>`) are what Anthropic trained on, and it follows instructions *literally* — ask for exactly what you want; aggressive/threatening language hurts newer models. GPT family: Markdown-first. Gemini: tends to want examples. For JSON, use the API's structured-output mode, don't beg in prose — see [S-04](s04-structured-output.md).

## Receipt
> XML-tag guidance for Claude (clarity, accuracy, parseability) is from Anthropic's primary docs: [Use XML tags to structure your prompts](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags). Model-family differences (reasoning vs instruction prompts, GPT Markdown-first, Gemini preferring examples, reserving CoT for non-reasoning models) are the consensus across 2026 prompt-engineering guides — directional, and worth confirming against each provider's current docs, which move fast. The "Markdown ≈15% fewer tokens than equivalent XML" figure is a reported benchmark, not independently reproduced here. Verified 2026-06-25.

## See also
[S-13](s13-context-engineering.md) · [S-04](s04-structured-output.md) · [R-02](../frontier/r02-reasoning-models.md) · [S-06](s06-model-routing.md) · [S-02](s02-context-budget.md)

## Go deeper
Keywords: `prompt engineering` · `XML tags` · `few-shot` · `chain-of-thought` · `reasoning model prompting` · `system prompt` · `structured output` · `delimiters` · `role prompting`
