#!/usr/bin/env python3
with open('/opt/data/handbook/knowledge-pulse.md') as f:
    lines = f.readlines()

all_statuses = {}
for l in lines:
    s = l.strip()
    if s.startswith('| I-'):
        cols = s.split('|')
        status = cols[10].strip() if len(cols) > 10 else '(empty)'
        all_statuses[status] = all_statuses.get(status, 0) + 1

print('Status distribution:')
for status, count in sorted(all_statuses.items(), key=lambda x: -x[1]):
    print(f'  {status}: {count}')
