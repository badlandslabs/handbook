# S-01 · Local Model Dispatch

Run model inference on your own machine — no API key, no network, no cost per call.

## Forces
- API costs accumulate fast at scale or in tight loops
- Some data cannot leave the machine (compliance, privacy)
- Network latency adds up in agentic pipelines making many sequential calls
- Local models are smaller and weaker — quality drops from frontier

## The move

Install [Ollama](https://ollama.com). It runs a local OpenAI-compatible server on port `11434` by default, but Claude Code's `claude -p` expects the Anthropic API format — Ollama's bridge listens on `11435`.

Point `ANTHROPIC_BASE_URL` at it. Pass a dummy API key to satisfy the auth check.

```bash
# Pull a model first
ollama pull llama3.2

# Dispatch a prompt
ANTHROPIC_BASE_URL=http://localhost:11435 \
ANTHROPIC_API_KEY=ollama \
claude -p "your prompt here"
```

The `ANTHROPIC_API_KEY` value doesn't matter — local servers don't validate it. Any non-empty string works.

**`--base-url` does not exist as a CLI flag.** Use the environment variable. Verified 2026-06-25: `claude --base-url` returns `error: unknown option '--base-url'`.

## Receipt

> Verified 2026-06-25 — ran against Ollama on localhost:11435

```
$ ANTHROPIC_BASE_URL=http://localhost:11435 ANTHROPIC_API_KEY=ollama claude -p "say hello"
Hello! How can I help you today?
```

## See also
[S-06](s06-model-routing.md) · [W-03](../workspace/w03-local-models-ollama.md) · [S-02](s02-context-budget.md)

## Go deeper
Keywords: `ollama` · `vLLM` · `llama.cpp` · `SGLang` · `OpenAI-compatible API` · `self-hosted inference`
