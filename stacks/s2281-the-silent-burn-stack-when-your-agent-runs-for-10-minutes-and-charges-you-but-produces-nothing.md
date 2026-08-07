# S-2281 · The Silent Burn Stack — When Your Agent Runs for 10 Minutes and Charges You but Produces Nothing

Your agent just returned HTTP 200. The logs show 47 LLM calls, 23,000 input tokens, and 0 useful output tokens. Your provider dashboard shows $187 in charges. The agent looped on a malformed tool response, retried silently, and never surfaced an error. This is not a crash — it's the most expensive kind of success. The silent burn stack is how teams stop agents from hemorrhaging tokens on tasks that were already dead.

## Forces

- **Agents fail silently in ways that cost money.** A traditional service crashes with a stack trace. An agent mid-loop returns HTTP 200 with an empty string and keeps calling the API, burning tokens at full rate. Provider-level spending caps cap the *account*, not individual agents or sessions — one runaway session can wipe out a multi-tenant deployment's monthly budget.
- **Token costs compound faster than teams expect.** Unlike latency or error rates, runaway token consumption is invisible until the bill arrives. Context overflow alone can 10x effective cost: hitting max output tokens means every subsequent call costs the full input price for the same context window.
- **Retry logic amplifies the problem.** A failed tool call that triggers a retry storm can produce 50+ identical API calls with no useful output. The failure mode is multiplicative, not additive.
- **Per-agent budgeting requires instrumentation most teams skip.** Without token counters between the LLM client and the API call site, there is no enforcement point. By the time usage is visible in the provider dashboard, the damage is done.

## The Move

Budget enforcement at the instrumentation layer, not the provider layer. Every LLM call passes through a token counter before it reaches the API. Hard limits are set per-agent, per-session, and per-tenant — not just per-account.

- **Wrap the LLM client**, not the API. Intercept calls at the SDK layer (after the request is built, before it goes over the wire) so enforcement is provider-agnostic. tokencap wraps `anthropic.Anthropic()` or `openai.OpenAI()` in 2 lines and blocks calls that would exhaust the budget before they reach the provider.
- **Count tokens, not dollars.** Provider pricing changes, cached tokens have different rates, and batch APIs have separate pricing tiers. Hard limits in dollars drift; limits in token counts stay accurate across all pricing models.
- **Enforce three budget tiers.** Session-level (per user run, typically $0.50–$5.00 equivalent in tokens) catches individual loops. Tenant-level catches one bad tenant from wiping a shared pool. Pipeline-level (batch processing) has its own headroom. Stack these: session budget exhausts first, then tenant, then pipeline.
- **Set max-turn limits alongside token budgets.** A token budget alone won't stop an agent from looping on cheap-but-wrong tool calls. Hard max-turn limits (e.g., 20 tool calls per session) act as a circuit breaker independent of token economics.
- **Kill on empty completion, not on error.** The most dangerous failure mode returns HTTP 200 with an empty output. Track consecutive empty completions as a separate signal. Two consecutive empty completions should trigger a stop, not a retry.
- **Log what was rejected, not just what succeeded.** Every budget kill should record: agent ID, token count at kill, turn count, and the last tool call that triggered the reject. This turns a silent failure into a debugging signal.

## Evidence

- **Show HN:** Developer built per-tool AI budget controls after losing $200 from a single agent loop — the agent ran without error until the bill arrived. [https://news.ycombinator.com/item?id=46991656](https://news.ycombinator.com/item?id=46991656)
- **GitHub gist:** A developer let an agent loose on a network scanning task; it hit an infinite loop with no circuit breaker and burned the entire cloud budget in one session. A separate multi-tenant SaaS had one runaway session exhaust the shared monthly API budget. [https://gist.github.com/QuocTranWorkspace/16b1b7413b65f1fed6ad79065d68983b](https://gist.github.com/QuocTranWorkspace/16b1b7413b65f1fed6ad79065d68983b)
- **GitHub gist:** Four token runaway patterns identified: empty completions with 50x retry loops, hallucinated tool calls in infinite loops, context overflow that forces max-input pricing on every subsequent call, and retry storms with no exponential backoff. [https://gist.github.com/Babar-maker76/64bbdc232659572305e1bccf69eb8c7f](https://gist.github.com/Babar-maker76/64bbdc232659572305e1bccf69eb8c7f)
- **PyPI package:** `token-budget-contracts` implements priority-weighted, confidence-gated token budget governance for multi-agent systems — budgets gate which sub-agents can spawn based on remaining budget and task priority. [https://pypi.org/project/token-budget-contracts](https://pypi.org/project/token-budget-contracts)
- **Engineering post:** Per-agent token budgets via Redis middleware: track cumulative token usage per agent, check the counter before every LLM call, reject if exhausted. Demonstrates the instrumentation pattern with Python and Redis. [https://how2.sh/posts/how-to-build-agent-safety-budget-controls-for-cost-predictability-for-enterprise-agent-teams/](https://how2.sh/posts/how-to-build-agent-safety-budget-controls-for-cost-predictability-for-enterprise-agent-teams/)

## Gotchas

- **Provider dashboards show totals, not per-agent breakdowns.** By the time usage is visible in the OpenAI/Anthropic dashboard, it is already too late to act. You need instrumentation *at the call site*, not at the billing level.
- **Hard limits in dollars drift.** Model prices change. Cached tokens cost less. Batch API is different. If you set a $1 limit and the model price drops 50%, your agent suddenly gets 2x more runs for the same dollar cap. Count tokens and convert to dollars at enforcement time, not at budget time.
- **Empty completions don't trigger error handling.** Your retry logic will catch this and retry — making it worse. You need empty-completion-as-stop-signal as a separate code path, not a retry.
- **Multi-agent systems need budget inheritance.** A supervisor that spawns 5 sub-agents needs to propagate its remaining budget to each sub-agent, or one sub-agent can silently consume the parent's entire allocation.
