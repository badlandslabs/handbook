import re
with open('knowledge-pulse.md', 'r') as f:
    content = f.read()

lines = content.split('\n')
in_table = False
ideas = []
for line in lines:
    if '| ID | Title' in line:
        in_table = True
        continue
    if in_table and line.startswith('## '):
        break
    if in_table and line.startswith('| I-'):
        ideas.append(line)

print(f'Total ideas: {len(ideas)}')

results = []
for line in ideas:
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 13:
        id_str = parts[1].strip()
        title = parts[2].strip()
        composite = parts[9].strip() if len(parts) > 9 else ''
        status = parts[10].strip() if len(parts) > 10 else ''
        results.append({'id': id_str, 'title': title, 'composite': composite, 'status': status})

def get_num(id_str):
    m = re.search(r'(\d+)', id_str)
    return int(m.group(1)) if m else 0

results.sort(key=lambda x: get_num(x['id']), reverse=True)

print('\nTop 30 most recent ideas:')
for r in results[:30]:
    comp = r['composite'].replace('**','')
    print(f'  {r["id"]:8s} | {comp:6s} | {r["status"][:35]:35s} | {r["title"][:65]}')

# Count statuses
status_words = []
for r in results:
    s = r['status'].split('-')[0].strip().split()[0]
    status_words.append(s)
from collections import Counter
print(f'\nStatus distribution: {dict(Counter(status_words))}')

# PENDING/RESEARCHING
pending = [r for r in results if 'PENDING' in r['status'] or 'RESEARCHING' in r['status']]
pending.sort(key=lambda x: float(x['composite'].replace('**','')) if x['composite'] else 0, reverse=True)
print(f'\nPENDING/RESEARCHING ({len(pending)}):')
for r in pending:
    comp = r['composite'].replace('**','')
    print(f'  {r["id"]:8s} | {comp:6s} | {r["status"][:40]:40s} | {r["title"][:65]}')
