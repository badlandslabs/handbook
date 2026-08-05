# S-2139 · The Agent Aging Stack — When Your Agent Fails at Week Three for No Code-Change Reason

Your agent scored 85% on its evaluation suite on launch day. You deployed it Monday. By Friday it was hallucinating tool calls. By week three accuracy had dropped to 61%, and nobody could explain why. No model updates. No code changes. No configuration diffs. The system is running the same architecture it launched with — but it is no longer the same system. This is not a memory leak. It is **agent aging**: time-dependent reliability degradation in a deployed agent caused by changing effective state, not changing weights.

## Situation

You run a persistent customer-agent that maintains session memory across weeks of operation. It tracks user preferences, conversation history, and derived facts in a memory store between sessions. On day one it answers correctly 87% of the time. By day 30 it answers correctly 54% of the time. The model weights never changed. The memory layer never crashed. The agent kept running — it just became a different, worse agent without anyone noticing.

## Forces

- **Day-one benchmarks measure a frozen system.** Standard evals test the agent at initialization. They miss the fundamental systems question: how long does the agent remain reliable after deployment? (arXiv:2605.26302, Zhu et al., UT Austin, May 2026)
- **Even frozen weights don't mean frozen behavior.** An agent's effective state changes through memory operations — compression, retrieval, revision, and maintenance — even when the model layer is perfectly static.
- **Agents age in four distinct mechanisms.** Compression aging, interference aging, revision aging, and maintenance aging each have different root causes and different repair strategies. Treating them as one problem produces the wrong fix.
- **Behavioral tests can stay clean while factual precision decays silently.** The agent still sounds fluent and confident. The surface reliability gap hides the underlying degradation until the damage compounds.
- **Aging is multiplicative in multi-agent systems.** The triage agent ages, which changes what the resolution agent receives, which accelerates the resolution agent's aging. Three agents with mild aging create a system that fails catastrophically.

## The move

Organize your monitoring and repair strategy around the four aging mechanisms. Each has a distinct signature, a distinct cause, and a distinct mitigation.

### 1. Compression aging — Omission

**Mechanism:** Summarizing interaction history drops future-relevant details. The agent writes compressed summaries to save context space; the summary loses the exact value that matters.

**Signature:** The agent can reason about the session correctly but loses precise factual details — exact dates, specific quantities, particular names.

**Example from AgingBench (arXiv:2605.26302):** User said "Take 50 mg of metoprolol twice daily." The agent logged "50 mg metoprolol, 2x daily." When asked "What's my dose?" the agent says "You take a daily medication" — losing both the quantity and frequency in compression.

**Mitigation:**
- Tag critical facts with a `P0_FACT` marker in session memory. Compression should preserve these verbatim, not summarize.
- Log structured key-value facts separately from narrative history. Query the structured store, not the summary.
- Measure compression accuracy: run the compress-then-retrieve cycle on a probe set weekly and flag precision drops.

### 2. Interference aging — Confusion

**Mechanism:** Accumulated similar memories crowd out the target fact. The agent retrieves the wrong entry from memory because similar-but-different entries have accumulated.

**Signature:** The agent retrieves a correct fact from memory but the fact belongs to a different user, session, or time period. Cross-user or cross-session confusion.

**Example from AgingBench:** Two contacts named John Smith and John Smyth. Both saved with their teams. Query "Email John Smith about..." → drafts to john.smyth@.

**Mitigation:**
- Disambiguate memory entries with structured keys: `{user_id, session_id, timestamp, entity_type, distinguishing_attribute}`.
- Use deterministic retrieval (exact key match) for factual queries, not semantic similarity search. Save semantic search for exploratory reasoning, not factual grounding.
- Run interference probes: seed memory with similar-but-distinct entries, then query. Measure retrieval precision, not just recall.

### 3. Revision aging — Staleness

**Mechanism:** Changed or derived state is not updated correctly. The agent updates a fact in one place but the update doesn't propagate to derived summaries or dependent knowledge.

**Signature:** The agent gives contradictory answers across different phrasings of the same question. "Are you premium?" → "Yes, Premium until Jan 2026." "Am I on a paid plan?" → "No, you are on a Free tier."

**Example from AgingBench:** User canceled premium. Cancellation was logged. But the agent's user profile summary still shows "Premium plan until Jan 2026."

**Mitigation:**
- Use event-sourced memory: store the log of mutations, not just the current state. Derive the current state from the mutation log on each read.
- On any state update, invalidate all derived summaries that mention that state. Don't let summaries become stale copies.
- Run staleness probes weekly: mutate a known fact, then query it through three different phrasings. Any stale answer is a revision aging event.

### 4. Maintenance aging — Collapse

**Mechanism:** Lifecycle events — memory flush, recompaction, model version rotation, prompt update, context window reset — trigger regressions because the agent was not tested against these events.

**Signature:** Accuracy drops sharply after a maintenance event. The agent works fine between maintenance events but fails immediately after any structural change.

**Example from AgingBench:** A medical scheduling agent works reliably for 25 days. On day 26, a routine memory compaction runs. The agent's Tuesday therapy session disappears from context. "What's my Tuesday schedule?" → "Nothing on Tuesdays."

**Mitigation:**
- Test maintenance events as part of the deployment checklist. Any flush, recompact, or model rotation should trigger an automated regression probe before the agent goes back online.
- Log a state snapshot before every maintenance event. After maintenance, verify the snapshot's key facts are still accessible.
- Implement graceful degradation: if a memory event corrupts state, the agent should fall back to asking the user to re-confirm critical facts rather than confidently wrong answers.

### Cross-cutting: The aging-aware eval loop

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

@dataclass
class AgingProbe:
    probe_type: str          # "compression" | "interference" | "revision" | "maintenance"
    critical_facts: list[dict]  # {"fact": str, "key": str, "p0": bool}
    timestamp: datetime

    def run(self, agent) -> dict:
        results = {}
        for fact in self.critical_facts:
            retrieved = agent.retrieve(fact["key"])
            results[fact["key"]] = {
                "correct": self._normalize(retrieved) == self._normalize(fact["fact"]),
                "retrieved": retrieved,
                "expected": fact["fact"],
                "p0": fact["p0"],
            }
        return results

    def score(self, results: dict) -> float:
        """Weighted score: P0 facts count 3x."""
        weighted = sum(
            (1 if r["correct"] else 0) * (3 if r["p0"] else 1)
            for r in results.values()
        )
        total = sum(3 if r["p0"] else 1 for r in results.values())
        return weighted / total if total > 0 else 0.0

    def _normalize(self, text: str) -> str:
        return text.lower().strip()


@dataclass
class AgingMonitor:
    agent_id: str
    baseline_score: float
    probe_interval_days: int = 7
    alert_threshold_drop: float = 0.10  # Alert if score drops >10% from baseline

    def check(self, agent) -> Optional[dict]:
        probe = AgingProbe(
            probe_type="weekly",
            critical_facts=self._load_critical_facts(agent),
        )
        results = probe.run(agent)
        score = probe.score(results)
        drop = self.baseline_score - score

        if drop > self.alert_threshold_drop:
            return {
                "agent_id": self.agent_id,
                "baseline": self.baseline_score,
                "current": score,
                "drop": drop,
                "threshold": self.alert_threshold_drop,
                "status": "AGING_DETECTED",
                "probe_results": results,
                "recommended_actions": self._triage(results),
            }
        return None

    def _triage(self, results: dict) -> list[str]:
        """Match failure patterns to aging mechanism."""
        actions = []
        failures = [k for k, v in results.items() if not v["correct"]]

        # Compression: P0 facts failed
        p0_fails = [k for k, v in results.items() if v["p0"] and not v["correct"]]
        if p0_fails:
            actions.append(f"COMPRESSION_AGING: {len(p0_fails)} P0 facts lost in retrieval — verify compression preserves tagged facts")

        # Interference: similar keys retrieved wrong entry
        if any("john" in k.lower() or "smith" in k.lower() for k in failures):
            actions.append("INTERFERENCE_AGING: check memory disambiguation — similar entries may be crowding target facts")

        # Revision: contradictions between phrasings
        actions.append("REVISION_AGING: verify event propagation — derived summaries may be stale after mutations")

        # Maintenance: check last maintenance timestamp
        actions.append("MAINTENANCE_AGING: audit last maintenance event — compaction/flush/rotation may have corrupted state")

        return actions

    def _load_critical_facts(self, agent) -> list[dict]:
        """Load the agent's tagged P0 facts from memory."""
        return agent.memory.query_tags(["P0_FACT"])
```

## Receipt

> Verified 2026-08-04 — Research synthesis from arXiv:2605.26302 (Zhu et al., UT Austin, May 2026), AgingBench benchmark (AgingBench.github.io), AgentMarketCap agent longevity field reports (April 2026), and Agnost AI production degradation studies (June 2026). The four aging mechanisms (compression, interference, revision, maintenance) are documented in the academic paper with specific examples. The Python monitoring scaffold is a realistic implementation of the aging-probe pattern described in AgingBench. No live run performed — this is a pattern entry with a structural code scaffold.

## See also

- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — multi-agent pipeline drift from external factors (user distribution shift, tool API changes, upstream model updates); complements aging, which is internal state drift
- [S-1005 · AI SRE: Behavioral SLOs, Error Budgets, and Incident Taxonomy](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the behavioral SLO framework for tracking agent health over time
- [S-246 · The Production Eval Pipeline: The Four-Stage Loop](s246-production-eval-pipeline-the-four-stage-loop.md) — continuous evaluation as the quality feedback mechanism; aging probes belong in stage 3 (shadow production)
- [S-1000 · The Context Exhaustion Stack](stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — the memory-pressure degradation that precedes and accelerates aging
