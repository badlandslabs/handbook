# S-2111 · The Skill Bloat Stack

When every skill you installed makes your agent perform *worse*, not better.

## Forces

- **Skills promised extensibility, delivered overhead.** The agentic ecosystem treats skills as free — installable, composable, lightweight. The reality: every token of skill content injected into the context window costs money *and* dilutes the model's attention on the task.
- **More skills = worse performance, up to a point.** Injecting 82 airline-policy skills into an agent demonstrably *hurts* completion rates. Similar tools interfere; similar rules conflict. The agent's context becomes a crowded room where every voice competes.
- **Silent degradation.** A bloated skill doesn't throw an error. It just makes the agent slower, noisier, and slightly wrong — in ways that don't surface until you compare costs or output quality against a baseline you forgot to set.
- **The "good" skills are mostly bad.** Of 55,315 publicly available skills analyzed, 26.4% lack routing descriptions entirely, over 60% of body content is non-actionable background, and reference files routinely inject tens of thousands of tokens per invocation.

## The Move

### Diagnose before you optimize

A skill has three token-consuming layers:

```
skill/
├── s.d  (description)    — the routing gate; model reads this to decide relevance
├── s.b  (body)           — the instructional payload; rules, templates, examples
└── s.r  (reference files) — injected on every call; can be 10K+ tokens each
```

Bloat can live in any layer. You need to know which before cutting.

### Stage 1 — Fix the routing layer

**The problem:** 26.4% of skills have no description at all. The agent cannot filter them — it gets everything or nothing. Another 44.1% have descriptions under 20 tokens, too short to be discriminative.

**The fix:** Generate dense, discriminative descriptions for every skill. Use adversarial delta debugging — start with a verbose description, progressively strip it, keep the minimum token count that still routes correctly.

```python
# Simplified SkillReducer Stage 1: routing description optimization
def optimize_description(skill_body: str, ground_truth_examples: list[str]) -> str:
    """Compress description to minimum discriminative length."""
    # Start with a full auto-generated description
    full_desc = generate_description(skill_body)

    # Binary search for minimum viable length
    low, high = 20, len(full_desc)
    while low < high:
        mid = (low + high) // 2
        if routes_correctly(full_desc[:mid], ground_truth_examples):
            high = mid
        else:
            low = mid + 1

    return full_desc[:low]

# Corroborated by SkillReducer: 48% description compression with 0.965
# cross-model retention (Gao et al., arXiv:2603.29919v2, Jun 2026)
```

### Stage 2 — Purge non-actionable content from the body

**The problem:** Only 38.5% of skill body content is core rules. The rest is background context (40.7%), illustrative examples (12.9%), and templates (7.6%). None of these help the agent execute — they just add noise to the context.

**The fix:** Separate core rules from supporting content. Keep rules. Archive everything else as retrievable reference, not injected context.

```python
# Simplified SkillReducer Stage 2: body restructuring
def restructure_body(skill_body: str) -> tuple[str, str]:
    """
    Split into:
      - core: injected into context (compact, actionable)
      - archive: retrievable on demand (stored, not injected)
    """
    lines = skill_body.split('\n')
    core, archive = [], []

    for line in lines:
        if is_actionable_rule(line):  # imperatives, constraints, patterns
            core.append(line)
        else:
            archive.append(line)  # context, rationale, examples

    # SkillReducer achieves 39% body compression this way
    # +2.8% functional quality improvement (counterintuitively)
    return '\n'.join(core), '\n'.join(archive)
```

**The counterintuitive result:** Removing non-actionable content *improves* agent performance. The "less-is-more" effect: reducing context noise lets the model focus. 48% description compression + 39% body compression yielded +2.8% functional quality on benchmark tasks.

### Gate skill loading with a cost checklist

Before any skill enters the context, run it through three gates:

```
SKILL LOAD CHECKLIST
□ Token budget for this call: [context_remaining] tokens
□ Skill description length: [N] tokens  (threshold: <150 for routing, <500 for body)
□ Reference files total: [N] tokens  (threshold: <2K per skill, <10K total)
□ Expected action rate: skills that change tool call frequency
□ Attention overlap: does this skill conflict with an already-loaded one?
```

### Monitor the dilution signal

Track these per-session:

- **Token spend per skill** — if a skill accounts for >15% of input tokens and its tool appears <5% of calls, it's noise
- **Tool call interference** — when two skills' recommended tools overlap, the agent picks inconsistently
- **Completion rate delta** — measure task success with and without each skill over 20+ runs; cut anything that doesn't lift the rate

## Receipt

> Receipt pending — 2026-08-04. Real-world validation requires: (1) install 3 skills in a test agent, (2) run 20 tasks with and without each, (3) measure token spend and completion rate. The SkillReducer paper (Gao et al., arXiv:2603.29919v2) provides the empirical baseline — 55,315 skills analyzed, 39% body compression achieved, +2.8% quality improvement. SkillsInjector (Li et al.) demonstrates attention dispersion with 82 skills on tau2-bench. The MCP context bloat pattern (Glama, 2025) confirms the production manifestation.

## See also

- [S-02 · Context Budget](stacks/s02-context-budget.md) — context window as a finite resource; this entry is the skill-specific manifestation
- [S-342 · Autonomous Context Compression](stacks/s342-autonomous-context-compression.md) — the agent-driven approach to the same problem from the memory side
- [S-2105 · The Tool Catalogue Stack](stacks/s2105-the-tool-catalogue-stack-when-your-agent-has-100-tools-and-can-use-none-of-them-effectively.md) — the MCP server design angle; bloated tool lists and bloated skill lists share the same root cause
