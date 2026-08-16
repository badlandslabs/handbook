# [S-2717] · The Tool Description Augmentation Paradox — When Better Descriptions Produce Worse Agents

You spent two weeks auditing your MCP tool descriptions. You found 97.1% had smells — missing limitations, unclear purpose, opaque parameters. You fixed them. Success rate went up 5.85 percentage points. Then your monitoring dashboard lit up: execution steps were up 67.46%, and 16.67% of task categories were regressing. Better descriptions made your agent slower, more expensive, and worse on a significant slice of tasks. The fix was partially right. You just applied it without understanding the trade-off.

## Forces

- **Better descriptions change what the agent does, not just how well it does it.** A richer description — purpose statement, limitations, examples, return shape — gives the model more to reason about. It uses that reasoning to try harder on hard tasks and explore more on all tasks. More exploration costs more steps, even when accuracy on the marginal cases improves.
- **Augmentation benefits are asymmetric across task types.** The median task that improves from augmentation is different from the median task that regresses. Aggregate success rate goes up while per-task reliability goes down. Teams optimize for the headline number and miss the regression tail.
- **Component combinations matter more than individual component quality.** The ablation results from arXiv:2602.14878 (Queen's University, 2026) show that no single component — not Examples, not Limitations, not ReturnType — is universally beneficial. Compact variants of different component combinations consistently preserve behavioral reliability while reducing token overhead. The "more is better" heuristic is empirically wrong.
- **Execution context determines whether augmentation helps or hurts.** The same augmented description that improves a complex multi-step task degrades a simple retrieval task. The model reads the extra context, decides it needs to be more thorough, and takes more steps on something that didn't need them.

## The move

The empirical data from 856 tools across 103 MCP servers (arXiv:2602.14878v2) gives you a precise answer: augmentation is not a binary decision. It is a three-dimensional trade-off between accuracy, cost, and task type.

**The triage framework:**

```
IF task_complexity == simple AND tool_count > 10:
    → Use compact description (purpose + return type only)
    → Skip: examples, limitations, parameter constraints

IF task_complexity == multi_step AND domain == well-defined:
    → Use full augmentation (all 6 components)
    → Accept: +67% step overhead as cost of accuracy

IF task_complexity == exploratory AND model == small:
    → Use purpose + constraints only
    → Skip: examples (they anchor the model to the example's assumptions)
```

**The compact augmentation recipe that preserves reliability:**

From component ablation results, the minimal effective description for most production tools is:

1. **Purpose** (1 sentence): what the tool does in terms of the agent's goal, not its implementation
2. **Return type** (schema excerpt or natural language): what the agent gets back and how to parse it
3. **Limitation** (1 constraint): the single most important boundary — "returns at most 100 rows," "requires authenticated session," "no undo"
4. **Parameter constraints only for ambiguous types**: date vs. datetime, string vs. enum — skip scalar types with obvious values

Drop: full examples, detailed parameter descriptions for obvious types, implementation notes, version history.

**The augmentation ROI gate:**

Before augmenting any tool, run it through a 20-task eval with your agent at your target model. Measure baseline step count and success rate. Then measure with augmentation. If success rate improvement × estimated task frequency < step count increase × estimated calls per day × token cost, don't augment.

**The regression guardrail:**

16.67% of task categories regress with full augmentation. Track task-type → augmentation outcome in your eval harness. Build a per-category augmentation map: which tool descriptions get full augmentation, which get compact, which get minimal. Treat it like a feature flag, not a global setting.

## References

- arXiv:2602.14878v2 — "MCP Tool Descriptions Are Smelly! Towards Improving AI Agent Efficiency with Augmented MCP Tool Descriptions" (Hasan et al., Queen's University, 2026): 856 tools, 103 servers, 6-component ablation, execution step regression data, compact variant results
- S-1644 · The Tool Description Stack — smell prevalence (97.1%) and the MCP ecosystem context
- S-2709 · The MCP Schema Inflation Trap — token cost of MCP descriptions at scale
