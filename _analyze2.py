import re

lines = open('knowledge-pulse.md').read().split('\n')

def parse_score(s):
    m = re.search(r'\*\*([0-9.]+)\*\*', s)
    return float(m.group(1)) if m else 0.0

for l in lines:
    if l.startswith('| I-'):
        parts = [p.strip() for p in l.split('|')]
        if len(parts) > 10 and parts[1].startswith('I-'):
            id_val = parts[1]
            title = parts[2]
            composite = parts[9]
            status = parts[10]
            sc = parse_score(composite)
            if 'WRITTEN' not in status and 'DUPLICATE' not in status and 'SUPERSEDED' not in status:
                print(f'{id_val} | {composite} | {status:<25} | {title[:80]}')
            elif sc >= 9.0:
                print(f'{id_val} | {composite} | {status:<25} | {title[:80]} *** HIGH SCORE')
