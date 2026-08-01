with open('knowledge-pulse.md', 'r', encoding='utf-8') as f:
    content = f.read()

pattern_entry = "- *2026-08-01* — **Recursive fidelity loss via compression middleware**: arXiv:2606.29251 (June 2026) documents information fidelity as the core problem — LLM compression produces fluent, factually-plausible summaries that alter downstream decisions. Two dominant failure patterns: decontextualization (evidence retained but caveats/qualifiers dropped) and model dependency (compression-model assumptions leak into downstream reasoning). Tianpan.co (May 2026): 'never use eval()' dropped by turn 30, 'require valid ID' violated after 15 compression cycles. Microsoft ACON classifies four compression failure modes. ACE (ICLR 2026) formalizes incremental merge as correct pattern. Constraints are low-entropy by general summarizer standards so get dropped first. Defense: structural delimiters, incremental merge, structured output slots, delta probes in CI. Novel — no existing entry covers recursive fidelity loss in compression middleware. Cross-links: S-1962, S-1002, S-1000, S-1035.\n\n"

old_pattern_marker = "## Pattern Log\n\n-"
content = content.replace(old_pattern_marker, pattern_entry + old_pattern_marker, 1)

dedup_entries = """recursive-fidelity → I-3113
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

content = content.replace(old_pattern_marker, dedup_entries + old_pattern_marker, 1)

with open('knowledge-pulse.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
