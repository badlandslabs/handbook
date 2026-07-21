#!/usr/bin/env python3
import re, sys

with open('/opt/data/handbook/knowledge-pulse.md', 'r') as f:
    content = f.read()

# Parse pending ideas (no WRITTEN/DUPLICATE, have composite score)
lines = content.split('\n')
pending = []

for line in lines:
    if '| I-' in line and 'WRITTEN' not in line and 'DUPLICATE' not in line:
        m = re.search(r'\| (I-\d+) \|', line)
        s = re.search(r'\*\*([\d.]+)\*\*', line)
        if m and s:
            parts = line.split('|')
            idea_id = m.group(1)
            score = float(s.group(1))
            title = parts[2].strip() if len(parts) > 2 else 'N/A'
            # Check it's not header
            if idea_id.startswith('I-'):
                pending.append((idea_id, title, score))

pending.sort(key=lambda x: x[2], reverse=True)
print(f'Total pending: {len(pending)}')
for idea_id, title, score in pending:
    print(f'{idea_id} | {score:.2f} | {title[:80]}')
