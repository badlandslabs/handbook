import re

lines = open('knowledge-pulse.md').read().split('\n')

ideas = []
for line in lines:
    if '| I-' in line:
        parts = [p.strip() for p in line.split('|')]
        # parts[0]=empty, parts[1]=ID, parts[2]=Title, parts[3]=Tags, parts[4]=Urgency,
        # parts[5]=Gap, parts[6]=Specificity, parts[7]=Timeliness, parts[8]=Density,
        # parts[9]=Composite, parts[10]=Status, parts[11]=Discovered, parts[12]=LastSeen
        if len(parts) >= 12 and parts[1].startswith('I-'):
            id_val = parts[1]
            title = parts[2]
            tags = parts[3]
            urgency = parts[4]
            gap = parts[5]
            composite = parts[9]
            status = parts[10]
            ideas.append((id_val, title, composite, status, urgency, gap, tags))

def parse_score(s):
    m = re.search(r'\*\*([0-9.]+)\*\*', s)
    return float(m.group(1)) if m else 0.0

ideas.sort(key=lambda x: parse_score(x[2]), reverse=True)

print(f'Total ideas found: {len(ideas)}')
print()
print('=== ALL IDEAS ===')
for id_val, title, composite, status, urgency, gap, tags in ideas[:80]:
    sc = parse_score(composite)
    flag = ' *** NOT WRITTEN ***' if 'WRITTEN' not in status else ''
    print(f'{id_val} | {composite} | {status:<25} | U={urgency} G={gap} | {title[:75]}{flag}')
