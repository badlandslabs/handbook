#!/usr/bin/env python3
import re

with open('/opt/data/handbook/knowledge-pulse.md') as f:
    content = f.read()
lines = content.split('\n')
idea_lines = [l for l in lines if l.startswith('| I-') and re.match(r'^\| I-\d+ \|', l)]

results = []
for l in idea_lines:
    bold = re.findall(r'\*\*(.+?)\*\*', l)
    composite = None
    for b in bold:
        try:
            v = float(b)
            composite = b
            break
        except:
            pass
    status = 'WRITTEN' if 'WRITTEN' in l else ('DUPLICATE' if 'DUPLICATE' in l else 'BLOCKED' if 'BLOCKED' in l else 'CANDIDATE')
    ids = re.findall(r'I-(\d+)', l[:20])
    parts = l.split('|')
    title = parts[2].strip() if len(parts) > 2 else '?'
    dim_parts = re.findall(r'\|\s*(\d+)\s+\|\s*(\d+)\s+\|\s*(\d+)\s+\|\s*(\d+)\s+\|\s*(\d+)\s+\|\s+\*\*', l)
    dims = dim_parts[0] if dim_parts else ('?','?','?','?','?')
    results.append((ids[0] if ids else '?', composite or '?', status, title, dims, l[:200]))

candidates = [r for r in results if r[2] == 'CANDIDATE']
candidates.sort(key=lambda x: float(x[1]) if x[1] != '?' else 0, reverse=True)
for r in candidates:
    print(f'I-{r[0]:>3} | {r[1]:>5} | U={r[4][0]} G={r[4][1]} S={r[4][2]} T={r[4][3]} D={r[4][4]} | {r[3][:70]}')
