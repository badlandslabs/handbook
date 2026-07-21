#!/usr/bin/env python3
import re

with open('knowledge-pulse.md') as f:
    lines = f.readlines()

# Find Ideas Bank section
start = None
end = None
for i, line in enumerate(lines):
    if '## Ideas Bank' in line:
        start = i
    if start is not None and '## Synthesis Notes' in line:
        end = i
        break

bank_lines = lines[start:end]

ideas = []
for i, line in enumerate(bank_lines):
    stripped = line.strip()
    if stripped.startswith('| I-') and '|' in stripped:
        parts = [p.strip() for p in stripped.split('|')[1:-1]]
        if len(parts) < 2:
            continue
        id_str = parts[0]
        score_m = re.search(r'\*\*([\d.]+)\*\*', stripped)
        score = float(score_m.group(1)) if score_m else 0
        status = parts[9] if len(parts) > 9 else ''
        written = 'WRITTEN' in status or status == 'DONE'
        ideas.append({
            'id': id_str,
            'score': score,
            'status': status,
            'title': parts[1] if len(parts) > 1 else '',
            'tags': parts[2] if len(parts) > 2 else '',
            'lastseen': parts[10] if len(parts) > 10 else '',
            'written': written,
            'line_num': start + i + 1
        })

print(f'Ideas in bank: {len(ideas)}')
written_count = sum(1 for x in ideas if x['written'])
pending = [x for x in ideas if not x['written']]
print(f'Written: {written_count}, Pending: {len(pending)}')

if pending:
    print()
    print('=== PENDING IDEAS ===')
    for idea in sorted(pending, key=lambda x: -x['score']):
        print(f'Line {idea["line_num"]}: {idea["id"]} | Score={idea["score"]:.2f} | {idea["title"][:80]}')
        print(f'  Tags: {idea["tags"][:100]}')

print()
print('=== TOP 15 BY SCORE ===')
for idea in sorted(ideas, key=lambda x: -x['score'])[:15]:
    print(f'{idea["id"]} | Score={idea["score"]:.2f} | Written={idea["written"]} | {idea["title"][:70]}')
