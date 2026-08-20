import re
with open('knowledge-pulse.md') as f:
    content = f.read()

# Find Ideas Bank section
idx_start = content.find('## Ideas Bank')
idx_end = content.find('## Recent Decisions')
if idx_end == -1:
    idx_end = content.find('## Pattern Log')
ideas_section = content[idx_start:idx_end]

# Split into lines
lines = ideas_section.split('\n')

# Find lines with triple-pipe idea entries
results = []
for line in lines:
    if re.match(r'\|\|\|\s*I-\d+', line):
        results.append(line)

pending = []
for r in results:
    score_m = re.search(r'\*\*(\d+\.\d+)\*\*', r)
    status_m = re.search(r'\|\s*WRITTEN\s*—|\|\s*DUPLICATE', r)
    id_m = re.search(r'I-(\d+)', r)
    # Title is after "The "
    title_m = re.search(r'\|\s*\|\s*\|\s*\|\s*The\s+([^\|]+)', r)

    if not status_m and score_m and id_m:
        score = float(score_m.group(1))
        iid = 'I-' + id_m.group(1)
        title = title_m.group(1).strip() if title_m else '?'
        pending.append((score, iid, title))

pending.sort(reverse=True)
print(f"Pending ideas: {len(pending)}")
for s, i, t in pending[:25]:
    print(f'{s:.2f} | {i} | {t[:85]}')
