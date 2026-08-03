#!/usr/bin/env python3
"""Parse the last Ideas Bank from knowledge-pulse.md - right-to-left approach"""
import re

with open('/opt/data/handbook/knowledge-pulse.md', 'r') as f:
    content = f.read()

# Find last Ideas Bank
last_idx = content.rfind('## Ideas Bank')
section = content[last_idx:]

# Split and find ideas + next section
lines = section.split('\n')
in_bank = True
ideas = []
for line in lines[1:]:  # skip header
    stripped = line.strip()
    if stripped.startswith('## ') and 'Ideas Bank' not in stripped:
        break
    if stripped.startswith('|| I-'):
        ideas.append(stripped)

print(f"Total ideas in last Ideas Bank: {len(ideas)}")
print()

for idea in ideas:
    parts = [p.strip() for p in idea.split('|')]
    # parts from LEFT: ['', ID, Title..., Tags, Urgency, Gap, Specificity, Timeliness, Density, Composite, Status, Discovered, LastSeen, '']
    # Count from RIGHT (11 trailing fields):
    # -2: '' (trailing)
    # -1: LastSeen
    # -2: Discovered  
    # -3: Status
    # -4: Composite
    # -5: Density
    # -6: Timeliness
    # -7: Specificity
    # -8: Gap
    # -9: Urgency
    # -10: Tags
    # -11+: Title (everything else)
    n = len(parts)
    lastseen = parts[-2] if n >= 2 else ''
    discovered = parts[-3] if n >= 3 else ''
    status = parts[-4] if n >= 4 else ''
    composite = parts[-5] if n >= 5 else ''
    density = parts[-6] if n >= 6 else ''
    timeliness = parts[-7] if n >= 7 else ''
    specificity = parts[-8] if n >= 8 else ''
    gap = parts[-9] if n >= 9 else ''
    urgency = parts[-10] if n >= 10 else ''
    tags = parts[-11] if n >= 11 else ''
    title_parts = parts[1:-11]
    title = ' '.join(title_parts)

    print(f"=== {parts[1]} ===")
    print(f"Title: {title}")
    print(f"Urgency={urgency} Gap={gap} Specificity={specificity} Timeliness={timeliness} Density={density}")
    print(f"Composite: {composite}")
    print(f"Status: {status}")
    print(f"Discovered: {discovered} | LastSeen: {lastseen}")
    print(f"Tags: {tags[:200]}")
    print()

# Print the pattern log and recent decisions
print("=== PATTERN LOG (last 40 lines) ===")
all_lines = content.split('\n')
for line in all_lines[-200:]:
    if 'Pattern Log' in line or 'Recent Decisions' in line or 'Deduplication Index' in line:
        marker = line
    elif '## ' in line:
        marker = line
    elif any(x in line for x in ['- *2026', '- *Pattern']):
        print(line)
