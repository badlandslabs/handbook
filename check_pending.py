with open('knowledge-pulse.md', 'r') as f:
    content = f.read()

import re
rows = re.findall(r'\|\| I-\d+ \|.*', content)
print(f"Found {len(rows)} idea rows\n")

# Print header for reference
header_lines = [l for l in content.split('\n') if '| ID |' in l or l.startswith('|--')]
for h in header_lines[:3]:
    print(f"HEADER: {h}")

print("\n--- ALL IDEAS (status col analysis) ---\n")
for r in rows:
    cols = [c.strip() for c in r.split('|')]
    # cols[0]=empty, cols[1]=empty, cols[2]=ID, cols[3]=Title, cols[4]=Tags, cols[5]=U, cols[6]=G, cols[7]=S, cols[8]=T, cols[9]=D, cols[10]=Composite, cols[11]=Status
    if len(cols) >= 12:
        id_ = cols[2]
        title = cols[3]
        composite = cols[10]
        status = cols[11] if len(cols) > 11 else "N/A"
        print(f"{id_}: {title[:60]} | Composite: {composite} | Status: {status}")
