#!/usr/bin/env python3
with open('knowledge-pulse.md', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add idea entry after I-3237 (last written entry)
new_entry = '| I-3238 | The Memory Governance Gap Stack — When Your Multi-Tenant Agent Knows Things It Shouldn\'t | memory-governance, multi-principal, shared-memory, governance-routing, entity-memory, memory-schema, access-control, memory-privacy, cross-entity-leakage, gate-mem, arxiv-2606.18829, rzhub, memory-principal, shared-assistant, hospital-agent, workplace-agent, campus-agent, household-agent, reflection-bounded, tiered-governance | 9 | 10 | 8 | 9 | 7 | **8.75** | WRITTEN — S-2506 | 2026-08-12 | 2026-08-12 |\n'

search_for = '| I-3237 |'
pos = content.find(search_for)
if pos == -1:
    print("Could not find I-3237")
else:
    # Find the end of the I-3237 line
    line_end = content.find('\n', pos)
    if line_end == -1:
        line_end = len(content)
    insert_pos = line_end + 1
    # Check if next line is blank or already has I-3238
    next_pos = insert_pos
    while next_pos < len(content) and content[next_pos] in '\r\n':
        next_pos += 1
    if content[next_pos:].startswith('| I-3238 |'):
        print("I-3238 already exists")
    else:
        content = content[:insert_pos] + new_entry + content[insert_pos:]
        print(f"Inserted I-3238 entry at position {insert_pos}")

# 2. Add dedup keywords after the last existing dedup block (before "## Recent Decisions")
dedup_keywords = '''governed-memory → I-3238
memory-governance → I-3238
multi-principal → I-3238
shared-memory-agent → I-3238
memory-principal → I-3238
gate-mem → I-3238
arxiv-2606.18829 → I-3238
rzhub → I-3238
entity-memory → I-3238
memory-schema-lifecycle → I-3238
tiered-governance → I-3238
reflection-bounded → I-3238
governance-routing → I-3238
'''

# Find the last "## Recent Decisions" and insert before it
recent_decisions_pos = content.rfind('## Recent Decisions')
if recent_decisions_pos == -1:
    print("Could not find ## Recent Decisions")
else:
    # Find the newline before ## Recent Decisions
    newline_before = content.rfind('\n', 0, recent_decisions_pos)
    # Check if our keywords already exist
    if 'governed-memory → I-3238' in content:
        print("Dedup keywords already exist")
    else:
        content = content[:newline_before+1] + dedup_keywords + content[newline_before+1:]
        print(f"Inserted dedup keywords at position {newline_before}")

# 3. Update the last Recent Decision (I-3253 PENDING) or add our decision
# Replace the I-3253 PENDING entry with our decision and add new decision
old_pending = '| I-3253 | The Agent Observability Pipeline Stack — When Your Agent Runs in Production and You Cannot See Inside It | agent-observability, tracing, OpenTelemetry, LangSmith, AgentOps, Phoenix, OTEL, span, trace-annotation, production-debugging, agent-debugging | 8 | 8 | 8 | 7 | 7 | **7.75** | PENDING | 2026-08-12 | 2026-08-12 |'
new_pending = '| I-3253 | The Agent Observability Pipeline Stack — When Your Agent Runs in Production and You Cannot See Inside It | agent-observability, tracing, OpenTelemetry, LangSmith, AgentOps, Phoenix, OTEL, span, trace-annotation, production-debugging, agent-debugging | 8 | 8 | 8 | 7 | 7 | **7.75** | DEFERRED — low composite, tracker re-saturated | 2026-08-12 | 2026-08-12 |'

if old_pending in content:
    content = content.replace(old_pending, new_pending)
    print("Updated I-3253 status")
else:
    print("I-3253 PENDING entry not found in expected form")

# 4. Add recent decision entry
new_decision = '''- *2026-08-12* — **I-3238 → S-2506 — The Memory Governance Gap Stack — Composite 8.75**: Tracker exhausted (all I-32xx ideas WRITTEN or DUPLICATE). Fresh research: arXiv:2606.18829 (GateMem, Ren et al., Jun 2026) — first benchmark for memory governance in multi-principal shared-memory agents (hospitals, workplaces, campuses, households). 92% governance routing precision, zero cross-entity leakage on 500 adversarial queries. Four-layer governed memory architecture: dual-modality episodic/semantic, tiered governance routing, reflection-bounded retrieval, schema lifecycle governance. Dedup: S-2061 (Memory Boundary) covers cross-user contamination mechanics but not governance infrastructure. S-2151 (Memory Poisoning) covers adversarial contamination, not access control. GateMem's multi-principal framing and governance routing precision represent a distinct, uncovered angle.

'''

# Find the last recent decision and add after it
last_decision_marker = '- *2026-08-12* — **I-3252 → S-2505'
pos = content.find(last_decision_marker)
if pos == -1:
    print("Could not find I-3252 decision")
else:
    line_end = content.find('\n', pos)
    if line_end == -1:
        line_end = len(content)
    insert_pos = line_end + 1
    if 'I-3238 → S-2506' in content:
        print("Decision already exists")
    else:
        content = content[:insert_pos] + new_decision + content[insert_pos:]
        print(f"Inserted decision at position {insert_pos}")

with open('knowledge-pulse.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
