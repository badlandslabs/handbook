with open('knowledge-pulse.md', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '| I-3108 |' in line:
        print(f"Found I-3108 at line {i+1}")
        new_entry = '| I-3113 | The Recursive Fidelity Stack — When Compression Middleware Silently Inverts Critical Constraints | recursive-compression, fidelity-loss, constraint-destruction, summarization-artifacts, context-engineering, incremental-compression, structured-output, compression-ci, information-fidelity, ACE, ACON, arxiv-2606-29251, arxiv-2510-04618 | 9 | 9 | 9 | 10 | 8 | **8.70** | WRITTEN — S-1962 | 2026-08-01 | 2026-08-01 |\n'
        lines.insert(i+1, new_entry)
        print(f"Inserted new entry at line {i+2}")
        break

with open('knowledge-pulse.md', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Done")
