#!/usr/bin/env python3
with open('knowledge-pulse.md', 'rb') as f:
    content = f.read()

new_entry = b'| I-3354 | The Cascading Failure Blast Radius Stack \xe2\x80\x94 When One Agent\'s Bad Output Becomes Everyone\'s Fact | cascading-failure, blast-radius, ASI08, OWASP-agentic, multi-agent-cascade, access-scope, operating-velocity, detection-window, blast-radius-formula, planning-execution-separation, replay-gate, circuit-breaker, belief-entropy, cascade-compounding, agent-handoff-contract, inter-agent-trust, least-agency, cascade-observability, microsoft-hve-core, beyondscale-2026, OWASP-ASI08-2025 | 9 | 9 | 10 | 10 | 9 | **9.40** | WRITTEN \xe2\x80\x94 S-2792 | 2026-08-17 | 2026-08-17 |\n'

search_for = b'| I-3353 |'
pos = content.rfind(search_for)
if pos == -1:
    print("Could not find I-3353")
else:
    line_end = content.find(b'\n', pos)
    if line_end == -1:
        line_end = len(content)
    insert_pos = line_end + 1
    new_content = content[:insert_pos] + new_entry + content[insert_pos:]
    with open('knowledge-pulse.md', 'wb') as f:
        f.write(new_content)
    print(f"Inserted after I-3353 at byte {insert_pos}")
    print("Done")
