# [S-2211] · The Scaffold Effect Stack

You upgraded from Claude 3.7 to Opus 4.6 and gained 4 percentage points on your benchmark. Your colleague switched from the default ReAct loop to a structured planning scaffold with mid-turn verification and cut their token-per-task cost by 60% while gaining 18 points. You are now two quarters into evaluating which frontier model to buy. The scaffolding question is not on your roadmap. This is the scaffold effect: the harness wrapping your model creates larger performance and efficiency variance than the model itself — and almost nobody measures it.

## Forces

- **The model-centrism trap.** Procurement, benchmarks, and conference talks are organized around model names and API tiers. Scaffolding is treated as implementation detail, not a first-class variable. This systematically misdirects engineering attention.
- **Leaderboard noise.** Public agent leaderboards rank by model name and pass rate, but the surrounding harness (tool issuance, context management, stop conditions) varies wildly and is rarely disclosed. Two agents sharing the same model can have 0–8pp pass-rate difference and 40× token-per-task variance — invisible in the reported number.
- **The vendor reframe problem.** Model vendors benefit from attributing all performance to model quality. The scaffolding layer is where the buyer spends engineering time, but it's operationally invisible to the benchmark. Early 2026 data shows the same model through different scaffolds produces 22–36pp performance gaps — exceeding the gap between most frontier tiers.
- **Scaffold choices compound.** Tool selection strategy, context window management, stop conditions, error recovery loops, and result verification are all scaffold components. Each adds or removes capabilities the model itself doesn't have. Their interaction is non-linear and hard to predict from first principles.

## The move

**Treat harness choice as a decision variable, not a default.**

```
# Scaffolding components that drive the largest variance
# (Vats & Golev, arXiv:2607.22585, Jun 2026)

component          | variance driver               | typical gap
--------------------|-------------------------------|-----------------
tool selection     | which tools, how many, order  | 3–15pp pass rate
context mgmt       | truncation vs. summarization  | 2–8pp + 10–40× tokens
stop condition     | fixed turns vs. goal-checked | 5–12pp
error recovery     | retry policy, escalation      | 4–10pp
verification loop  | judge frequency, threshold   | 6–18pp
```

**Diagnose before swapping models.** Run your best prompt through two different scaffolds before deciding the model is the bottleneck. The 80/20 split: instrument your scaffold's per-turn token count, tool call count, and success rate. Compare against a minimal scaffold (plain ReAct, no extra loops). If the gap is under 5pp, scaffold is not your problem. If the gap is 20pp+, you have a scaffold problem, not a model problem.

**Isolate scaffold variables.** Change one component at a time: tool schema ordering, context eviction strategy, stop condition type. Log every variable. Build a scaffold scorecard over 2–4 weeks of production traffic, not just eval benchmarks. The scaffold that wins on HumanEval may lose on your domain-specific task.

**The scaffold stack that compounds:**
1. **Planner** — structured task decomposition before tool use
2. **Selector** — which tools are in scope for this turn (not all tools, the right tools)
3. **Executor** — tool call + parameter validation
4. **Checker** — result quality gate before proceeding
5. **Reporter** — when to stop and what to return

Each layer can be swapped independently. The interaction effects between layers are where the 40× token variance lives.

**Quantify the autonomy tax.** Each scaffold layer adds overhead (token cost, latency). Track scaffold overhead as a percentage of total cost per session. Four independent analyses in 2026 all converged on a 70–80% overhead ratio for agentic tasks vs. direct API calls. This is not a bug — it is the structural cost of bounded autonomy. Know your number. If your scaffold overhead exceeds 85%, the model is spending more tokens on scaffolding than on reasoning.

## Receipt
> Receipt pending — [2026-08-06]: arXiv:2607.22585 (Vats & Golev, Jun 2026) — 40× token variance across harnesses on SWE-bench; AgentMarketCap scaffolding vs. model study (Apr 2026) — 22–36pp performance gap; moltbook autonomy tax analysis — 70–80% overhead converging across four agents; AutoTool (AAAI 2026, arXiv:2511.14650) — 30% inference overhead reduction via tool selection optimization.

## See also
- [S-2202 · The Tool Flood Stack](s2202-the-tool-flood-stack-when-your-agent-has-hundreds-of-tools-and-no-attention-budget.md) — tool overload is a scaffold design problem, not a model problem
- [S-2206 · The Context Compilation Stack](s2206-the-context-compilation-stack-when-your-agent-re-reads-the-same-raw-materials-every-single-turn.md) — context management is the highest-leverage scaffold component
- [S-2203 · The Production Eval Oracle Stack](s2203-the-production-eval-oracle-stack-when-your-evaluation-metric-becomes-the-target.md) — scaffold-level eval is how you catch harness regressions before they reach production
