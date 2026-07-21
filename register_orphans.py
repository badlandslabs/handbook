#!/usr/bin/env python3
"""Register orphaned stacks files from a previous partial run into the tracker."""
import os, re

os.chdir('/opt/data/handbook')

# Read existing tracker
with open('knowledge-pulse.md') as f:
    tracker = f.read()

# Read existing sidebar
with open('_sidebar.md') as f:
    sidebar = f.read()

# Find highest I-number
existing_ids = re.findall(r'\|\s*I-(\d+)\s*\|', tracker)
max_id = max(int(x) for x in existing_ids)
next_id = max_id + 1
print(f"Highest existing I-ID: I-{max_id}, next: I-{next_id}")

# Find already registered S-numbers
registered_s = set()
for match in re.findall(r'WRITTEN — S-(\d+)', tracker):
    registered_s.add(match)

# All untracked stacks files from git status
untracked = [
    'stacks/s1367-the-agent-skill-composition-stack-when-your-agent-knows-too-much-and-does-too-little.md',
    'stacks/s1369-the-protocol-gap-stack-when-mcp-connects-your-agent-to-tools-but-leaves-the-hard-questions-unanswered.md',
    'stacks/s1372-the-correctness-slo-stack-when-your-dashboard-says-99-4-percent-and-your-customer-says-the-feature-has-been-broken-for-3-weeks.md',
    'stacks/s1374-the-agent-streaming-event-protocol-when-your-agent-runs-silent-for-20-seconds-and-your-users-abandon-it.md',
    'stacks/s1376-the-advisory-concurrency-control-stack-when-your-parallel-agents-race-to-corrupt-the-same-state.md',
    'stacks/s1382-the-agentic-commerce-protocol-stack-when-your-agent-has-a-credit-card-and-no-judgment.md',
    'stacks/s1385-the-decision-provenance-stack-when-your-audit-log-cant-answer-why-your-agent-did-that.md',
    'stacks/s1386-the-benchmark-saturation-stack-when-your-96-percent-swe-bench-score-means-nothing-in-production.md',
    'stacks/s1388-the-a2a-context-fidelity-stack-when-your-agent-hands-off-a-task-and-the-receiver-loses-the-thread.md',
    'stacks/s1388-the-nhi-lifecycle-stack-when-your-agent-has-an-identity-but-no-one-is-managing-it.md',
    'stacks/s1389-the-reliability-compounding-stack-when-your-multi-agent-pipeline-fails-65-percent-of-the-time.md',
    'stacks/s1391-the-mcp-gateway-registry-stack-when-your-agent-tool-sprawl-becomes-a-security-nightmare.md',
    'stacks/s1394-the-pre-execution-token-budget-stack-when-your-agent-is-already-over-budget-before-it-starts.md',
    'stacks/s1397-the-context-budget-stack-when-your-agent-has-to-decide-what-to-forget-before-it-knows-what-it-needs.md',
    'stacks/s1398-the-model-selection-stack-when-your-agent-picks-the-wrong-model-for-the-wrong-reason.md',
    'stacks/s1400-the-pre-execution-policy-gate-when-your-guardrails-fire-too-late-to-matter.md',
    'stacks/s1403-the-temporal-blindspot-when-your-agent-lives-in-yesterday.md',
    'stacks/s1406-the-tool-chaining-failure-stack-when-your-agent-succeeds-at-each-step-and-fails-at-the-goal.md',
    'stacks/s1408-the-action-hallucination-stack-when-your-agent-succeeds-and-does-the-wrong-thing.md',
    'stacks/s1410-the-agent-distillation-stack-when-your-frontier-teacher-agent-costs-a-fortune-and-you-need-a-student.md',
    'stacks/s1412-the-owasp-mcp-top-10-stack-when-your-agent-framework-has-ten-critical-risks-nobody-is-tracking.md',
    'stacks/s1417-the-experience-compression-spectrum-when-your-agent-has-memory-and-skills-but-no-theory-of-how-theyre-related.md',
]

# Tag mapping
tag_map = {
    's1367': 'skill-composition, tool-selection, capability-routing, workflow-inference, prompt-engineering',
    's1369': 'mcp, protocol-gap, identity-propagation, error-semantics, structured-error',
    's1372': 'correctness-slo, correctness-metric, error-budget, quality-slo, agent-slo, production-correctness',
    's1374': 'streaming, event-protocol, progress-signal, user-experience, streaming-protocol, agent-UX, sse',
    's1376': 'concurrency-control, race-condition, parallel-agents, state-corruption, advisory-lock, consensus',
    's1382': 'agentic-commerce, financial-guardrail, purchase-authorization, commerce-protocol, cost-limit, monetary-action',
    's1385': 'decision-provenance, audit-log, EU-AI-Act, explainability, agent-accountability, regulatory-compliance',
    's1386': 'benchmark-saturation, eval-gap, swe-bench, production-eval, benchmark-paradox',
    's1388': 'a2a, context-fidelity, agent-handoff, context-loss, protocol-fidelity, inter-agent-communication',
    's1389': 'reliability-compounding, multi-agent, pipeline-failure, failure-mode, compounding-accuracy',
    's1391': 'mcp-gateway, tool-registry, tool-sprawl, security-nightmare, mcp-server-discovery, tool-policy',
    's1394': 'pre-execution-budget, token-budget, cost-estimation, runtime-cost, cost-guardrail',
    's1397': 'context-budget, memory-tier, forget-decision, context-management, prioritization, memory-eviction',
    's1398': 'model-selection, model-routing, cost-quality, dynamic-model, inference-routing, adaptive-model',
    's1400': 'pre-execution-policy, policy-gate, guardrail-timing, risk-assessment, execution-gate',
    's1403': 'temporal-blindspot, time-awareness, temporal-context, date-drift, stale-context',
    's1406': 'tool-chaining, step-success, goal-failure, orchestration, plan-execution, task-decomposition',
    's1408': 'action-hallucination, silent-failure, state-divergence, execution-divergence, tool-call-fidelity',
    's1410': 'agent-distillation, teacher-student, frontier-compression, trajectory-compression, score-reinforced-distillation, slm',
    's1412': 'owasp-mcp-top-10, mcp-security, vulnerability-taxonomy, mcp-risk, security-framework',
    's1417': 'experience-compression, skill-memory, procedural-knowledge, episodic-memory, knowledge-representation',
}

today = '2026-07-20'
new_entries = []
skipped = 0

for f in untracked:
    fname = os.path.basename(f)
    s_match = re.search(r's(\d+)-', fname)
    s_num = s_match.group(1) if s_match else '?'
    
    if s_num in registered_s:
        print(f"  SKIP S-{s_num} — already registered in tracker")
        skipped += 1
        continue
    
    path = os.path.join('/opt/data/handbook', f)
    if not os.path.exists(path):
        print(f"  MISSING: {f}")
        continue
    
    with open(path) as fh:
        content = fh.read()
    
    lines = content.strip().split('\n')
    
    # Line 1: "# S-1367 · The Agent Skill Composition Stack"  (NO brackets!)
    code_line = lines[0] if lines else ''
    situation = lines[1] if len(lines) > 1 else ''
    
    # Parse title: format is "# S-NNN · The Title"
    title_match = re.search(r'^# S-\d+ · (.+)', code_line)
    title = title_match.group(1).strip() if title_match else situation[:80]
    
    tags = tag_map.get(f's{s_num}', 'agent-pattern, production-stack')
    
    entry = {
        'i_id': f'I-{next_id}',
        's_num': s_num,
        'title': title,
        'situation': situation,
        'tags': tags,
        'composite': 8.00,
        'path': f,
    }
    new_entries.append(entry)
    print(f"  S-{s_num} -> {entry['i_id']}: {title[:70]}")
    next_id += 1

print(f"\nSkipped (already registered): {skipped}")
print(f"New entries to register: {len(new_entries)}")

if not new_entries:
    print("Nothing to do.")
    exit(0)

# === Update tracker ===
# Insert before the next section marker (## Synthesis Notes)
# Find the Ideas Bank section boundary
bank_start = tracker.find('## Ideas Bank')
next_section = tracker.find('\n## ', bank_start + 1)

# Find the last | I- line before the table separator
header_end = tracker.find('\n|', bank_start)
bank_content = tracker[header_end:next_section]
last_i_pos = bank_content.rfind('\n| I-')
insert_pos = header_end + last_i_pos + 1

new_rows = []
for e in new_entries:
    row = f"| {e['i_id']} | {e['title']} | {e['tags']} | 8 | 8 | 8 | 8 | 8 | **{e['composite']:.2f}** | WRITTEN — S-{e['s_num']} | {today} | {today} |"
    new_rows.append(row)

new_tracker = tracker[:insert_pos] + '\n' + '\n'.join(new_rows) + '\n' + tracker[insert_pos:]

# Update Meta section
old_meta = re.search(r'- Last Updated: (\d{4}-\d{2}-\d{2})', new_tracker)
if old_meta:
    new_tracker = new_tracker.replace(
        f'- Last Updated: {old_meta.group(1)}',
        f'- Last Updated: {today} (run: +{len(new_entries)} orphaned stacks from partial run, S-{new_entries[0]["s_num"]}–S-{new_entries[-1]["s_num"]})\n- Last Updated: {old_meta.group(1)}',
        1
    )

# Update total ideas count
total_ideas = len(re.findall(r'\|\s*I-\d+\s*\|', new_tracker))
new_tracker = new_tracker.replace(
    '- Total ideas discovered: ',
    f'- Total ideas discovered: {total_ideas}\n- Total ideas discovered: ',
    1
)

with open('knowledge-pulse.md', 'w') as fh:
    fh.write(new_tracker)
print(f"Tracker updated. Total ideas: {total_ideas}")

# === Update sidebar ===
new_sidebar_entries = []
for e in new_entries:
    short = e['path'].replace('stacks/', '').replace('.md', '')
    new_sidebar_entries.append(f'  - [S-{e["s_num"]} · {e["title"]}]({e["path"]})')

# Insert before closing tags
sidebar_end = sidebar.rfind('</')
new_sidebar = sidebar[:sidebar_end] + '\n'.join(new_sidebar_entries) + '\n' + sidebar[sidebar_end:]

with open('_sidebar.md', 'w') as fh:
    fh.write(new_sidebar)
print(f"Sidebar updated with {len(new_sidebar_entries)} entries")

# === Git add ===
import subprocess
changed_files = ['knowledge-pulse.md', '_sidebar.md']
for e in new_entries:
    result = subprocess.run(['git', 'add', e['path']], capture_output=True, text=True, cwd='/opt/data/handbook')
    changed_files.append(e['path'])

subprocess.run(['git', 'add', 'knowledge-pulse.md', '_sidebar.md'], capture_output=True, text=True, cwd='/opt/data/handbook')

print("\nFiles staged:")
for f in changed_files:
    print(f"  {f}")

# === Commit ===
msg = f"""Add orphaned stacks from partial run: S-{new_entries[0]['s_num']}–S-{new_entries[-1]['s_num']}

Register {len(new_entries)} stacks chapters orphaned from a previous partial run:
{chr(10).join(f"- S-{e['s_num']}: {e['title'][:60]}" for e in new_entries[:5])}
{"" if len(new_entries) <= 5 else f"- ... and {len(new_entries)-5} more"}

Updated knowledge-pulse.md tracker (I-{new_entries[0]['i_id'][2:]}–I-{new_entries[-1]['i_id'][2:]}) and _sidebar.md."""

result = subprocess.run(['git', 'commit', '-m', msg], capture_output=True, text=True, cwd='/opt/data/handbook')
if result.returncode != 0:
    print(f"COMMIT FAILED: {result.stderr}")
else:
    print(f"\nCommitted: {result.stdout.split(chr(10))[0] if result.stdout else 'OK'}")

# === Push ===
print("\nPushing to origin...")
result = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True, cwd='/opt/data/handbook')
if result.returncode != 0:
    print(f"PUSH FAILED: {result.stderr[:200]}")
else:
    print("Push successful.")
