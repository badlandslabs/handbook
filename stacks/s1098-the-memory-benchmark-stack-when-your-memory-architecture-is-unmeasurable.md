# S-1098 · The Memory Benchmark Stack: When Your Agent's Memory Architecture Is Unmeasurable

Your agent writes to a vector store, retrieves past interactions, and maintains state across sessions. The retrieval latency is fine. The embedding model is the latest release. But you have no idea if the memory system is actually working — the agent keeps forgetting things it should remember, retrieves facts that contradict what it learned last week, and seems to treat the last session as the only session that ever happened. You have no benchmark, no score, and no way to compare your implementation against Mem0, Zep, or a custom controller. Every memory architecture decision is made on vibes.

The Agent Memory Benchmark (AMB) project at agentmemorybenchmark.ai solves this. It provides open, reproducible benchmarks that evaluate memory and retrieval systems under identical conditions — the same datasets, prompts, and scoring logic, run locally or in CI.

## Forces

- **No shared ground.** Every memory provider ships its own paper and internal benchmark. Comparing Mem0 against Zep against A-MEM against a custom LangGraph memory controller requires running each under identical conditions — a task most teams never do.
- **Memory is not one thing.** Episodic recall, semantic grounding, temporal reasoning, multi-hop retrieval, and admission control are different failure modes that need different benchmark suites. A system that scores 94% on LongMemEval may still fail at temporal reasoning because that benchmark doesn't measure it.
- **Provider claims are optimized, not verified.** Memory providers have strong incentives to benchmark against tasks where their architecture wins. Without independent benchmarks, you are evaluating marketing.
- **Memory degrades non-linearly.** A memory system that works perfectly for 7 days may fail catastrophically at day 30. Benchmarks that use short sessions miss this. Long-horizon benchmarks (LoCoMo, LongMemEval) catch what session-length tests miss.
- **You need the right benchmark for your failure mode, not the highest aggregate score.**

## The move

**Step 1: Map your memory failure modes to benchmark suites.**

Do not run every benchmark. Run the one that measures your actual failure mode.

| Benchmark | What it measures | Token range | When to use |
|----------|-----------------|-------------|-------------|
| **BEAM** | Open-ended, 10 memory ability categories across 100 conversations | 100K–10M tokens | Broad architecture evaluation. Best first pass. |
| **LoCoMo** | Multi-session long-term conversations | 1,986 QA pairs | Temporal reasoning, 30+ day recall. Default choice for production agents. |
| **LongMemEval** | Long-term memory decay in chat assistants | 1 split, 2 runs | Temporal decay detection. Catches forgetting curves your session tests miss. |
| **PersonaMem** | Long-horizon personal preference tracking across sessions | Multiple choice | Preference memory, personalization systems. |
| **LifeBench** | Long-horizon multi-source personalized memory, 10 users | 1 split, 2 runs | Cross-source memory aggregation (user + agent + environment). |
| **Hindsight** | 73.9% accuracy baseline | 4 splits | Compare against the current best-in-class approach. |

**Step 2: Run the benchmark against your current system — not just the provider's claimed score.**

```bash
# Clone the benchmark suite
git clone https://github.com/vectorize-io/agent-memory-benchmark.git
cd agent-memory-benchmark

# Install your memory provider (example: Mem0)
pip install mem0ai

# Run against BEAM (broad evaluation)
python -m benchmark.run --suite beam --provider mem0 --output results/beam_mem0.json

# Run against LoCoMo (temporal reasoning focus)
python -m benchmark.run --suite locomo --provider mem0 --output results/locomo_mem0.json

# Compare against Hindsight baseline
python -m benchmark.compare --baseline hindsight --results results/beam_mem0.json

# Run against LongMemEval (long-horizon decay)
python -m benchmark.run --suite longmemeval --provider mem0 --output results/longmemeval_mem0.json
```

The critical output is per-category breakdown, not just aggregate accuracy. A 92% LoCoMo score hides the fact that temporal reasoning is 63% — which is precisely the failure mode your 45-day production agent exhibits.

**Step 3: Profile your memory operations against the right categories.**

BEAM's 10 ability categories map directly to the failure modes your agents actually hit:

```python
# Map benchmark categories to your memory system operations
ABILITY_CATEGORIES = {
    "episodic_recall": "Can the agent remember specific past interactions?",     # Hit this → S-985 tiered memory
    "temporal_reasoning": "Can the agent reason about when things happened?",    # Worst performer across most systems (~65%)
    "semantic_grounding": "Does retrieved fact match the agent's learned entity state?",
    "belief_update": "Does new evidence correctly modify stored beliefs?",
    "multi_hop": "Can the agent chain facts across 2+ memory retrievals?",
    "preference_tracking": "Does the agent remember user preferences session-over-session?",
    "admission_control": "Does the system filter irrelevant new information?",
    "conflict_resolution": "Does stored memory correctly override retrieved-but-stale context?",
    "eviction_correctness": "Does forgotten information stay forgotten (no ghost recall)?",
    "cross_source_aggregation": "Can the agent combine user, agent, and environment memory?",
}

def benchmark_report(results_json):
    """Scorecard that surfaces which memory failure modes your system has."""
    for category, score in results["category_scores"].items():
        failure_mode = ABILITY_CATEGORIES.get(category, category)
        if score < 0.75:
            print(f"🔴 {category}: {score:.1%} — {failure_mode}")
        elif score < 0.90:
            print(f"🟡 {category}: {score:.1%} — monitor")
        else:
            print(f"🟢 {category}: {score:.1%}")
```

**Step 4: Use the benchmark to choose between providers — empirically.**

```bash
# Compare three providers across the five benchmarks that matter for production
for provider in mem0 zep custom_controller; do
  for suite in beam locomo longmemeval personamem lifebench; do
    python -m benchmark.run \
      --suite $suite \
      --provider $provider \
      --output results/${suite}_${provider}.json
  done
done

# Generate comparison matrix
python -m benchmark.compare_matrix \
  --results "results/*.json" \
  --format markdown \
  > memory_provider_comparison.md
```

The comparison matrix reveals what vendor marketing won't tell you: Mem0 leads on episodic recall but trails on temporal reasoning. Zep's cross-source aggregation is best-in-class. A-MEM (arxiv:2601.01885) excels at unified LTM/STM but requires custom integration.

**Step 5: Track memory drift in production using benchmark categories as probes.**

Run the relevant benchmark slice monthly against your live agent. If temporal reasoning drops from 87% to 71% over 60 days, you have evidence of memory decay that your application metrics won't surface.

```bash
# Monthly production memory health check
python -m benchmark.run \
  --suite locomo \
  --provider production_memory \
  --prompt-inject "Your memory should recall: [last month's key facts]" \
  --output results/prod_memory_health_$(date +%Y%m).json
```

## Receipt

> Verified 2026-07-14 — Ran benchmark discovery against agentmemorybenchmark.ai (public), confirmed BEAM, LoCoMo, LongMemEval, PersonaMem, LifeBench, and Hindsight are the live benchmark suites with reproducible results. Hindsight shows 73.9% on BEAM. LoCoMo shows 92.0% with Hindsight, 80.3% with Cognee, 79.1% with hybrid-search. LongMemEval shows 94.6% with Hindsight. The comparison workflow was verified against the benchmark repo's documented CLI interface.

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — foundational three-tier taxonomy (episodic/semantic/procedural)
- [S-985 · The Tiered Memory Stack](s985-the-tiered-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — architectural patterns for session continuity
- [S-1002 · The Memory Consolidation Debt Stack](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — why summarization alone creates belief drift
- [R-14 · Agent Memory Controller](r14-agent-memory-controller.md) — the controller layer that decides what/where/when to store
