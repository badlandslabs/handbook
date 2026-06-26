# R-04 · Small Language Models for Agents

The argument that the right default model inside an agent is a small one — frontier reach reserved for the calls that actually need it. This is [Law 1](../laws.md) (cheapest sufficient intelligence) as a research thesis.

## Forces
- Most agent subtasks (tool-calling, routing, extraction, classification, structured output) are narrow and repetitive — not the open-ended reasoning frontier models are built for
- Frontier calls cost 10–30× more and add latency; at agent loop volumes that compounds fast
- Small models trail on broad world knowledge and multi-step reasoning — push them past their range and they fail confidently
- Some deployments (mobile, robotics, edge, on-prem compliance) can't call a cloud frontier model at all

## The move

- **Default to the smallest model that can finish the call.** The narrow, repetitive subtasks that dominate agent work rarely need a frontier model. Reach up only when the job proves it must.
- **Run a heterogeneous stack: SLM-first, LLM-on-demand.** A cheap router handles the common case with a small model and escalates only hard or long-context calls to a frontier model — caching tiers, not a single tier. See [S-06](../stacks/s06-model-routing.md).
- **Migrate empirically.** Start with a frontier model to map the task, then fine-tune small models onto the hot, repetitive steps and monitor. Don't pick sizes in the abstract.
- **Score on cost-per-completed-task, not per-token sticker price.** A small model that occasionally falls back to a frontier model still wins the bill — compute the *blended* number for your real task mix.
- **Know the limits.** Where the task needs broad knowledge or deep reasoning, keep the frontier model. Data quality and orchestration matter more than parameter count.

## Receipt
> Thesis from ["Small Language Models are the Future of Agentic AI"](https://arxiv.org/abs/2506.02153) (Belcak et al., NVIDIA Research, arXiv 2506.02153, June 2025) — a **position paper**, not a benchmark study. Its three pillars: SLMs (working definition ~<10B params) are sufficiently powerful, inherently more suitable, and more economical for many agent invocations. The "10–30× cheaper to serve" figure is NVIDIA's own estimate; downstream parity claims (e.g. a fine-tuned 3.8B model beating a frontier model on a narrow domain) are vendor/blog-reported — directional, benchmark your own task. Verified 2026-06-25; not independently reproduced here.

## See also
[S-06](../stacks/s06-model-routing.md) · [S-01](../stacks/s01-local-model-dispatch.md) · [W-03](../workspace/w03-local-models-ollama.md) · [R-01](r01-model-landscape.md) · [R-03](r03-fine-tuning-vs-prompting.md)

## Go deeper
Keywords: `small language models` · `SLM` · `agentic AI` · `NVIDIA 2506.02153` · `heterogeneous model stack` · `on-device LLM` · `model routing` · `fine-tuning` · `blended cost`
