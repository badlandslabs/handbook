with open('knowledge-pulse.md', 'r', encoding='utf-8') as f:
    content = f.read()

# The pattern entry is currently misplaced at line 2578 (in Ideas Bank table)
# Remove it from there
bad_prefix = "- *2026-08-01* — **Recursive fidelity loss via compression middleware**:"
content = content.replace(bad_prefix + " arXiv:2606.29251", "", 1)

# Now insert it in the correct Pattern Log (line 3570 area, most recent)
# The MCP Transport entry is the most recent pattern entry
mcp_pattern = "- *2026-08-01* — **MCP Transport Boundary"
good_entry = bad_prefix + " arXiv:2606.29251 (June 2026) documents information fidelity as the core problem — LLM compression produces fluent, factually-plausible summaries that alter downstream decisions. Two dominant failure patterns: decontextualization (evidence retained but caveats/qualifiers dropped) and model dependency (compression-model assumptions leak into downstream reasoning). Tianpan.co (May 2026): 'never use eval()' dropped by turn 30, 'require valid ID' violated after 15 compression cycles. Microsoft ACON classifies four compression failure modes. ACE (ICLR 2026) formalizes incremental merge as correct pattern. Constraints are low-entropy by general summarizer standards so get dropped first. Defense: structural delimiters, incremental merge, structured output slots, delta probes in CI. Novel — no existing entry covers recursive fidelity loss in compression middleware. Cross-links: S-1962, S-1002, S-1000, S-1035.\n\n" + mcp_pattern

content = content.replace(mcp_pattern, good_entry, 1)

# Now add deduplication index entries before the Pattern Log at line 3570
# Find the Deduplication Index entries before the MCP Transport pattern
# They end with an empty line before "## Pattern Log"
dedup_block = """recursive-fidelity → I-3113
compression-fidelity → I-3113
information-fidelity → I-3113
constraint-loss → I-3113
constraint-destruction → I-3113
summarization-artifacts → I-3113
context-compression-artifacts → I-3113
constraint-inversion → I-3113
compression-drift → I-3113
recursive-summarization → I-3113
delta-probe → I-3113

"""

# Insert dedup entries just before the MCP Transport entry
content = content.replace(mcp_pattern, dedup_block + mcp_pattern, 1)

with open('knowledge-pulse.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
