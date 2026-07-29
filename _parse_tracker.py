import re, sys

with open('/opt/data/handbook/knowledge-pulse.md') as f:
    lines = f.readlines()

results = []
for line in lines:
    if not line.startswith('| I-'):
        continue
    parts = [p.strip() for p in line.split('|')]
    if len(parts) < 12:
        continue
    id_ = parts[2]
    title = parts[3]
    composite_raw = parts[10]
    status = parts[11].strip()
    m = re.search(r'\*\*([\d.]+)\*\*', composite_raw)
    score = float(m.group(1)) if m else 0.0
    results.append((score, id_, status, title))

results.sort(key=lambda x: -x[0])
for score, id_, status, title in results:
    print(f'{score:.2f} | I-{id_} | {status} | {title}')
