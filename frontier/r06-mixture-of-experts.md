# R-06 · Mixture of Experts

The architecture that lets a model hold enormous knowledge but only run a slice of itself per token — why a 671B model can serve at the cost of a ~37B one. The reason the cheap-fast frontier exists.

## Forces
- Dense models run every parameter for every token; quality scales, but so does cost — linearly and painfully
- You want a model's *knowledge capacity* large but its *per-token compute* small — dense architectures can't separate the two
- MoE separates them, but the bill moves rather than vanishes: from compute to memory
- Routing adds its own failure mode — uneven expert load wastes the whole advantage

## The move

(This is *within-model* routing — picking experts inside one model. Don't confuse it with [S-06](../stacks/s06-model-routing.md), which routes *between* different models.)

- **Know the mechanism.** MoE splits the feed-forward layers into many "expert" sub-networks; a small router picks the top-k experts per token. Self-attention stays dense — only the FFN becomes expert-based, so only a fraction of params run per forward pass.
- **Separate active from total.** Compute tracks *active* params; capacity tracks *total*. DeepSeek-V3 is 671B total / 37B active (~5.5%) — 256 routed experts plus 1 always-on shared expert, top-8 routed per token.
- **Remember: MoE saves FLOPs, not VRAM.** Mixtral 8×7B runs at ~13B-active speed but needs all ~46.7B loaded in memory. You hold every expert even when it's idle.
- **Pair shared and routed experts.** A shared expert runs on every token (common knowledge); routed experts are specialized and selected per token. The 2026 trend is more, smaller experts plus a shared one.
- **Apply it to decisions even if you never train one.** It's why open models rival frontier quality at lower cost (see [R-04](r04-small-language-models.md)). When self-hosting, budget VRAM for the *total* size, not the active size, and plan for router load-balancing.

## Receipt
> DeepSeek-V3 figures (671B total, 37B active, 256+1 experts, top-8) are from the [DeepSeek-V3 Technical Report](https://arxiv.org/abs/2412.19437) (arXiv 2412.19437). Mechanism (router picks top-k FFN experts, attention stays dense, shared vs routed experts) from HuggingFace's [Mixture of Experts](https://huggingface.co/blog/moe) explainer. Mixtral 8×7B (46.7B total / ~13B active) is from Mistral's release. MoE being the dominant 2025–2026 frontier architecture is widely reported across these and vendor sources. Verified 2026-06-25; not independently reproduced here.

## See also
[R-04](r04-small-language-models.md) · [R-01](r01-model-landscape.md) · [S-06](../stacks/s06-model-routing.md) · [W-03](../workspace/w03-local-models-ollama.md) · [R-02](r02-reasoning-models.md)

## Go deeper
Keywords: `mixture of experts` · `MoE` · `sparse activation` · `router` · `top-k routing` · `shared expert` · `DeepSeek-V3` · `Mixtral` · `active vs total parameters` · `expert parallelism`
