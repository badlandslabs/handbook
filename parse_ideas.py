import re

with open('/opt/data/handbook/knowledge-pulse.md') as f:
    content = f.read()

start = content.find('## Ideas Bank')
end = content.find('## Pattern Log', start)
section = content[start:end]

# Find all positions of '| I-XXX'
positions = [m.start() for m in re.finditer(r'\| I-\d+', section)]

ideas = []
for i, pos in enumerate(positions):
    end_pos = positions[i+1] if i+1 < len(positions) else len(section)
    row = section[pos:end_pos]
    row = ' '.join(row.split())  # normalize whitespace
    parts = [p.strip() for p in row.split('|')]
    if len(parts) >= 11:
        id_ = parts[1]
        title = parts[2]
        status = parts[10]
        ideas.append((id_, title, status))

print(f'Total ideas found: {len(ideas)}')
print()

filtered = [(id_, title, status) for id_, title, status in ideas
            if 'WRITTEN' not in status and 'DUPLICATE' not in status]

print(f'Non-WRITTEN, non-DUPLICATE ideas: {len(filtered)}')
print()
for id_, title, status in filtered:
    print(f'{id_:8s} | {title} | {status}')
