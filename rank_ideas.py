#!/usr/bin/env python3
with open('knowledge-pulse.md', 'r') as f:
    content = f.read()

lines = content.split('\n')
in_bank = False
ideas = []
for line in lines:
    if '## Ideas Bank' in line:
        in_bank = True
        continue
    if not in_bank or not line.startswith('| I-'):
        continue
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 13:
        id_ = parts[1]
        title = parts[2]
        score_raw = parts[9]
        status = parts[10]
        discovered = parts[12]
        if 'WRITTEN' in status or 'DONE' in status or 'Archived' in status:
            continue
        try:
            score = float(score_raw.replace('**','').replace('*',''))
        except:
            score = 0.0
        ideas.append((score, id_, title, status, discovered))

ideas.sort(key=lambda x: -x[0])
print(f"Total unwritten ideas: {len(ideas)}\n")
for s, i, t, st, d in ideas[:25]:
    print(f"{s:.2f} | {i} | {t[:75]} | {st} | {d}")
