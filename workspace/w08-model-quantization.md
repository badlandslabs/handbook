# W-08 · Model Quantization

When you pull `ollama run llama3.2`, you are running a quantized model. The weights have been compressed from their original 16-bit floats to 4-bit integers. You gave up a small amount of accuracy; you gained the ability to run a 3B model on a laptop with 4 GB of VRAM. Every practitioner using local models is already making this trade — most don't know the details of what they chose.

## Forces

- A 70B model at FP16 requires ~140 GB of VRAM — more than any consumer card and most single-server deployments; quantization is what makes large models runnable
- Every bit removed is information permanently lost from the weight; quality degradation is real but varies non-linearly across precision levels
- Different tasks degrade at different rates: factual recall holds up well at Q4; long-chain arithmetic and nuanced reasoning degrade faster
- Format fragmentation: GGUF (llama.cpp/Ollama), AWQ (GPU-accelerated), GPTQ, and FP8 serve different deployment targets and are not interchangeable
- Production GPU clusters (H100/H200) use FP8; developer laptops use GGUF Q4; edge hardware uses INT4 or below — picking the wrong format for your target adds a conversion step

## The move

**The precision ladder (FP16 baseline → lower):**

| Format | VRAM vs FP16 | Quality loss (MMLU-Pro) | Best for |
|---|---|---|---|
| FP8 | −50% | ~0.4 pts | H100/H200 production |
| INT8 | −50% | ~0.7 pts | Cost-efficient server |
| AWQ / INT4 | −75% | ~1.6 pts | GPU cost-constrained |
| GGUF Q5_K_M | −60% | minimal | Developer hardware |
| GGUF Q4_K_M | −65% | 3–5% | Consumer default |
| GGUF Q2_K | −80%+ | noticeable | Avoid unless forced |

**GGUF is the developer format.** A single `.gguf` file bundles weights, tokenizer, metadata, and quantization parameters. No separate config. Runs on Windows/Linux/macOS with CUDA, Metal, ROCm, or CPU. Ollama uses GGUF natively; `llama3.2` pulls the Q4_K_M variant by default.

**The safe floor is Q4.** Quality degradation is roughly linear from FP16 down through INT8 and Q4. Below 3-bit, degradation becomes nonlinear — avoid Q2 unless VRAM is the only constraint.

**FP8 is the 2026 production standard on datacenter GPUs.** On H100, FP8 delivers ~33% faster output throughput versus FP16 with near-zero quality loss. vLLM, SGLang, and TensorRT-LLM all support FP8 natively.

**Choosing a quantization:**
- Developer machine, VRAM < 8 GB: GGUF Q4_K_M
- Developer machine, VRAM 8–16 GB: GGUF Q5_K_M or Q6_K
- Production serving, H100/H200: FP8 via vLLM or SGLang
- Production serving, cost-constrained: AWQ INT4 with Marlin kernel

## Receipt

> Receipt pending — 2026-06-26. Local model bridge (localhost:11435) unavailable at time of writing (connection refused). Quality benchmark figures above are from published hardware vendor benchmarks across six 70B-class models (Llama 4 70B, Qwen 3 72B, DeepSeek V4-Flash, Mistral Large 2, Command-R+, Yi 2) — not locally reproduced. GGUF Q4_K_M as Ollama's default for llama3.2 is verifiable via `ollama show llama3.2` when the service is running.

## See also

[W-03](w03-local-models-ollama.md) · [R-10](../frontier/r10-speculative-decoding.md) · [R-04](../frontier/r04-small-language-models.md) · [S-06](../stacks/s06-model-routing.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper

Keywords: `GGUF` · `Q4_K_M` · `AWQ` · `GPTQ` · `FP8` · `llama.cpp` · `bitsandbytes` · `quantization artifacts` · `VRAM budget` · `Marlin kernel`
