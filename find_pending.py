#!/usr/bin/env python3
import re

with open('/opt/data/handbook/knowledge-pulse.md', 'r') as f:
    lines = f.readlines()

pending = []
for line in lines:
    line = line.rstrip()
    if '| I-' in line and 'WRITTEN' not in line and 'DUPLICATE' not in line:
        parts = line.split('|')
        if len(parts) >= 4:
            # Reconstruct idea_id (may have || prefix)
            prefix = ''
            p0 = parts[0]
            if p0.startswith('||'):
                prefix = '||'
            elif p0.startswith('|'):
                prefix = '|'
            idea_id = prefix + parts[1].strip() + parts[2].strip()
            m = re.search(r'\*\*([\d.]+)\*\*', line)
            score = m.group(1) if m else 'N/A'
            # Title is parts[3] for || prefixed, parts[2] for | prefixed
            if prefix == '||':
                title = parts[3].strip() if len(parts) > 3 else 'N/A'
            else:
                title = parts[2].strip() if len(parts) > 2 else 'N/A'
            if idea_id.replace('|', '').strip().startswith('I-'):
                pending.append((idea_id.replace('|', '').strip(), title, score))

pending.sort(key=lambda x: float(x[2]) if x[2] != 'N/A' else 0, reverse=True)
print(f'Total pending: {len(pending)}')
for idea_id, title, score in pending:
    print(f'{idea_id} | {score} | {title[:80]}')
