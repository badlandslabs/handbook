# W-03 · Local Models with Ollama

Run open-source LLMs on your own hardware. No API key, no data leaving the machine, no per-token cost.

## Forces
- API cost at volume adds up; local inference has no marginal cost
- Some data (PII, proprietary documents) cannot be sent to external APIs
- Local models are weaker than frontier — quality tradeoff is real
- Setup is a one-time cost; Ollama makes it manageable

## The move

**Install Ollama:** [ollama.com/download](https://ollama.com/download) — available for macOS, Windows, Linux.

```bash
ollama serve          # start the inference server (default port 11434)
```

**Pull and run models:**
```bash
ollama pull llama3.2          # Meta Llama 3.2 (3B, ~2GB) — fast, small
ollama pull llama3.3          # Meta Llama 3.3 (70B, ~40GB) — stronger
ollama pull qwen2.5-coder     # Alibaba Qwen 2.5 Coder — good for code
ollama pull nomic-embed-text  # embedding model for RAG

ollama run llama3.2           # interactive chat
ollama list                   # see installed models
```

**Use via Python (OpenAI-compatible API):**
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
response = client.chat.completions.create(
    model="llama3.2",
    messages=[{"role": "user", "content": "Explain RAG in one paragraph."}]
)
print(response.choices[0].message.content)
```

**Use via Claude Code** (Anthropic-compatible bridge on port 11435):
```bash
ANTHROPIC_BASE_URL=http://localhost:11435 ANTHROPIC_API_KEY=ollama claude -p "your prompt"
```

**Model selection guide:**

| Task | Model | Size |
|---|---|---|
| Quick Q&A, extraction | llama3.2 | 3B |
| Code generation | qwen2.5-coder | 7B |
| Complex reasoning | llama3.3 | 70B |
| Embeddings for RAG | nomic-embed-text | 137M |

**Hardware reality:** 7B models run on 8GB RAM. 70B models need 40GB+ or a quantized version. GPU acceleration (NVIDIA CUDA, Apple Metal) makes a large difference in speed.

## Receipt
> Receipt pending — 2026-06-25. Ollama install and local dispatch via port 11435 confirmed (see [S-01](../stacks/s01-local-model-dispatch.md)). Python OpenAI-compatible call not run in this session — verify before use.

## See also
[S-01](../stacks/s01-local-model-dispatch.md) · [S-07](../stacks/s07-rag.md) · [W-01](w01-ai-dev-environment.md)

## Go deeper
Keywords: `Ollama` · `llama.cpp` · `vLLM` · `LM Studio` · `GGUF` · `quantization` · `Q4_K_M` · `Apple Metal` · `CUDA`
