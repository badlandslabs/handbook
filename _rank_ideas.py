import re

content = open('knowledge-pulse.md').read()
lines = content.split('\n')

in_bank = False
pending = []
for line in lines:
    if '## Ideas Bank' in line:
        in_bank = True
        continue
    if in_bank and line.startswith('## '):
        break
    if in_bank and ('| I-' in line or '|| I-' in line):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 12:
            id_ = parts[1].strip()
            if not id_.startswith('I-'):
                continue
            title = parts[2].strip()
            composite_raw = parts[9].strip().replace('**','')
            status = parts[10].strip()
            if 'WRITTEN' not in status.upper() and 'DUPLICATE' not in status.upper():
                try:
                    score = float(composite_raw)
                except:
                    score = 0.0
                pending.append((id_, title, score, status))

pending.sort(key=lambda x: x[2], reverse=True)
print(f'Pending non-dup ideas: {len(pending)}')
print()
for idea in pending[:50]:
    print(f'{idea[0]} | {idea[2]:.2f} | {idea[1][:90]}')
    print(f'  Status: {idea[3][:120]}')
