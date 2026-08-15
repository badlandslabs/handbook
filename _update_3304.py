content = open('knowledge-pulse.md').read()
# Add I-3304 to Recent Decisions after I-3303
old = '- *2026-08-14* — **I-3303 → S-2618'
new = '''- *2026-08-14* — **I-3304 → S-2620 — The Knowledge Compilation Stack — Composite 9.80**: Discovered via multi-source research: Karpathy LLM Wiki pattern (compile-once-query-many), The New Stack "Context Layer Bottleneck" (Karpathy cited: compile step dominates, July 2026), VentureBeat "Context Architecture Replacing RAG" (Redis Iris, May 2026), SuperML "MCP Bloat Tax" (Atlassian Teamwork Graph: 48% token reduction via structured query, May 2026). Core insight: raw-source RAG forces the LLM to re-derive synthesized understanding on every query. The fix: two-phase architecture — compile once (LLM synthesizes raw sources into interlinked entity/topics wiki pages), then query many (cheap, consistent, no re-derivation). Incremental update: watch source timestamps, recompile affected pages only. Implementation refs: agent-wiki npm, openclaw_llm-wiki-compiler (54 commits), llm-wiki-hermes skill. Deduplicated from S-2600 (RAG failure taxonomy), S-2607 (agent memory tiers), S-2619 (memory architecture). Tags: I-3304.

- *2026-08-14* — **I-3303 → S-2618'''
count = content.count(old)
print(f"Found {count} occurrences of I-3303 entry")
content = content.replace(old, new, 1)
open('knowledge-pulse.md', 'w').write(content)
print("Done")
