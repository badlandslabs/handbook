# S-2050 · The Cache Ordering Trap — When Naive Prompt Caching Slows Your Agent Down

Your agent is running 500 sessions on DeepResearch Bench. You've enabled prompt caching — you're using a modern provider with 94% cache hit rate. You expect 41–80% cost reduction. Instead, time-to-first-token went up. Cache hit rate is high. The system is working exactly as designed. You are the problem.

The cache ordering trap is a counterintuitive failure mode where prompt cache placement — not cache presence — determines whether caching helps or hurts. arXiv:2601.06007 (Lumer et al., Jan 2026) provides the first empirical proof across three major providers: naive full-context caching paradoxically *increases* latency on agentic workloads, while strategic cache block control delivers the promised savings.

## Forces

- **Cacheable blocks and dynamic blocks share the same prompt.** Agents concatenate static system prompts, tool schemas, knowledge bases, and dynamic tool outputs into a single context. When any dynamic block is included in the cache key, every output change invalidates the entire prefix — including all the expensive static content that should have been cached.
- **Cache position affects KV cache reuse.** Providers scan from prompt start. A 50,000-token tool result that changes every turn is not just wasted in the current call — it invalidates every downstream token's cache entry because it occupies the prefix.
- **The break-even math is per-block, not per-prompt.** S-187 covers when caching pays off economically. This entry covers when it actively makes things worse. The conditions are different.
- **Agent workloads have structured repetition with embedded variation.** The same system prompt, tool schema, and knowledge base repeat across sessions. The tool outputs (search results, database queries, code execution results) do not. Naive caching treats these as one blob.

## The move

**Design your prompt as a cache-aware block structure, not a flat concatenation.**

### Rule 1: Separate static from dynamic at the block level

Divide your prompt into three zones by churn rate:

```
[ ZONE A — Static ]     System prompt, tool schemas, knowledge base
                        Cache: ALWAYS  |  Churn: never
[ ZONE B — Semi-static ] Few-shot examples, retrieval context
                        Cache: USUALLY |  Churn: daily/weekly
[ ZONE C — Dynamic ]     Tool call outputs, intermediate results, turn history
                        Cache: NEVER   |  Churn: every turn
```

Pass these as distinct blocks to your provider. Some providers (Anthropic, OpenAI) support explicit cache control via `--cache_depth` or `extra_body["cache_control"]`. Others (Google) use position-based rules. Know your provider's API.

### Rule 2: Place dynamic content at the end of the prompt

Providers that use prefix-based KV caching scan from the first token. Dynamic content at the *end* of the prompt affects only the tail — the expensive static prefix remains fully cacheable across turns.

```
System: "You are a research agent."              ← cached (100% reuse)
Knowledge base: 8,000 tokens                     ← cached (100% reuse)  
Tool schema: 400 tokens                           ← cached (98% reuse)
Tool results from turns 1–47: ~30,000 tokens    ← NOT cached (tail only)
```

Full-context caching includes the tool results in the cache key. On turn 47, the tool output differs from turn 46. The entire 50,000-token prefix must be re-computed, negating the cache benefit for the static zones.

### Rule 3: Evaluate cache mode per model, not globally

The arXiv study found provider-specific optima:

| Provider | Best Strategy | Cost Reduction | TTFT Improvement |
|----------|-------------|----------------|-----------------|
| GPT-5.2 | Exclude tool results | 79.6% | 13.0% |
| Claude Sonnet 4.5 | System prompt only | 78.5% | 22.9% |
| Gemini 2.5 Pro | System prompt only | 41.4% | 6.1% |
| GPT-4o | System prompt only | 45.9% | 30.9% |

GPT-5.2 uniquely benefits from excluding tool results (not just system prompt). Claude and Gemini are best with system-prompt-only caching. No single strategy dominates across providers — and none benefit from full-context caching on agentic workloads.

### Rule 4: Validate with shadow sessions before production

Run a diagnostic session in shadow mode alongside your production agent. Compare TTFT and cost between cached and non-cached runs. The signal is simple:

```
delta_ttft = TTFT(cached_run) - TTFT(uncached_run)
delta_cost = cost(cached_run) - cost(uncached_run)

If delta_ttft > 0 and delta_cost > 0 → cache ordering is broken
If delta_ttft < 0 and delta_cost < 0 → caching is working
If delta_ttft > 0 and delta_cost < 0 → cheap but slow (cache structure issue)
If delta_ttft < 0 and delta_cost > 0 → fast but expensive (unnecessary cache writes)
```

The common mistake is measuring cost alone. A cache that reduces cost by 20% while increasing latency by 40ms per call is a regression for interactive agents.

### Rule 5: Re-evaluate when you change tools or prompts

Every addition of a new tool, every retrieval context change, every system prompt edit shifts the block boundaries. A cache configuration that was optimal six months ago may be trapping your current workload. This is not a set-and-forget configuration.

## Receipt

> Verified 2026-08-03 — arXiv:2601.06007 (Lumer et al., Jan 2026) documents the cache ordering effect empirically across 500+ agent sessions on DeepResearch Bench. Provider-specific cache strategy data (GPT-5.2, Claude Sonnet 4.5, Gemini 2.5 Pro, GPT-4o) confirmed from the paper abstract and detailed results table. TTFT measurements (13–31% improvement range) confirmed. Rule 5 (re-evaluation cadence) is guidance based on the paper's finding that cache block composition directly determines performance outcomes — no specific re-evaluation interval is prescribed in the paper.

## See also

- [S-187 · Prompt Cache Break-Even Calculator](s187-prompt-cache-break-even-calculator.md) — when caching is economically worth it
- [S-1192 · The Five-Layer Caching Stack](s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — the broader caching taxonomy
- [S-1244 · The Context Fill Cliff](s1244-the-context-fill-cliff-when-your-agent-runs-great-at-message-5-and-terrible-at-message-50.md) — context degradation across turns
