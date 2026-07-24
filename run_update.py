#!/usr/bin/env python3
"""Update tracker, sidebar, and push to GitHub — single pass."""
import urllib.request
import urllib.error
import base64
import json
import os
import re
import sys

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = 'badlandslabs/handbook'
BRANCH = 'main'

headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
}

def get_sha(path):
    url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}'
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        return data['sha']
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def push_file(path, content, sha=None, message=None):
    data = {
        'message': message or f'Update {path}',
        'content': base64.b64encode(content).encode(),
    }
    if sha:
        data['sha'] = sha
    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method='PUT')
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

# ── 1. Update knowledge-pulse.md ──────────────────────────────────────────────
with open('knowledge-pulse.md', 'r') as f:
    tracker = f.read()

# Add new idea entry after I-2036 row
new_idea = (
    '| I-2038 | The Session Continuity Stack: When Your Agent Wakes Up Without Knowing What It Already Did | '
    'session-continuity, cross-session-state, continuity-protocol, checkpoint-attestation, committed-effects-ledger, '
    'world-state-attestation, semantic-memory-handoff, idempotent-replay, non-idempotent-recovery, '
    'session-handoff, state-reconstruction, control-plane, effects-ledger, session-resumption, '
    'checkpoint-vs-continuity, S-1536, S-09, S-1012 | '
    '9 | 10 | 9 | 9 | 9 | **9.25** | WRITTEN — S-1542 | 2026-07-23 | 2026-07-23 |\n'
)

# Find the I-2036 entry line and insert after it
lines = tracker.split('\n')
insert_idx = None
for i, line in enumerate(lines):
    if line.startswith('| I-2036 |'):
        insert_idx = i + 1
        break

if insert_idx:
    lines.insert(insert_idx, new_idea)
    print(f"Inserted I-2037 at line {insert_idx}")
else:
    print("WARNING: Could not find I-2036 entry!")
    sys.exit(1)

tracker_updated = '\n'.join(lines)

# Add dedup keywords
dedup_addition = (
    '\nsession-continuity → I-2038\n'
    'cross-session-state → I-2038\n'
    'continuity-protocol → I-2038\n'
    'checkpoint-attestation → I-2038\n'
    'committed-effects-ledger → I-2038\n'
    'world-state-attestation → I-2038\n'
    'semantic-memory-handoff → I-2038\n'
    'idempotent-replay → I-2038\n'
    'non-idempotent-recovery → I-2038\n'
    'session-handoff → I-2038\n'
    'state-reconstruction → I-2038\n'
    'effects-ledger → I-2038\n'
    'session-resumption → I-2038\n'
    'checkpoint-vs-continuity → I-2038\n'
)
    'temporalio-langgraph → I-2037\n'
)

# Insert before the ## Deduplication Index marker
tracker_updated = tracker_updated.replace(
    '## Deduplication Index',
    dedup_addition + '## Deduplication Index'
)
print("Added dedup keywords")

# Add recent decision
decision = (
    '| 2026-07-23 | I-2037 | WRITTEN — S-1536 | '
    'The Durable Execution Stack — composite 8.95. Tracker exhausted (I-001 through I-2036 all written or deduplicated). '
    'Fresh research: Temporal blog (Jul 16, 2026) on the new LangGraph plugin for durable execution — '
    'LangGraph defines agent logic, Temporal guarantees execution. Three crash-recovery failures from '
    'in-process checkpointing fixed by moving to activity-level durability. Key insight: LangGraph checkpointing '
    'saves state but replays expensive LLM calls; Temporal activity durability replays work transparently. '
    'Human-in-the-loop via Temporal signals (no pod required, no polling). Saga compensation for '
    'multi-step partial failures. Deduplication: no existing entry covers LangGraph-Temporal integration '
    'or the distinction between checkpointing (state) and durable execution (work). '
    'S-357 covers temporal layer design for agent orchestration but not durable execution guarantees. '
    'S-1532 covers failure governance but not crash-survivable workflow infrastructure. |'
)

tracker_updated = tracker_updated.replace(
    '|| 2026-07-22 | I-2029 | WRITTEN — S-1472 |',
    decision + '\n|| 2026-07-22 | I-2029 | WRITTEN — S-1472 |'
)
print("Added recent decision entry")

with open('knowledge-pulse.md', 'w') as f:
    f.write(tracker_updated)
print("Written: knowledge-pulse.md")

# ── 2. Update _sidebar.md ─────────────────────────────────────────────────────
with open('_sidebar.md', 'r') as f:
    sidebar = f.read()

new_sidebar_entry = (
    '  - [S-1536 · The Durable Execution Stack — When LangGraph Gives You the Agent and Temporal Gives You the Guarantee](stacks/s1536-the-durable-execution-stack-when-langgraph-gives-you-the-agent-and-temporal-gives-you-the-guarantee.md)\n'
)

# Insert after S-1535 entry
sidebar_lines = sidebar.split('\n')
insert_sb = None
for i, line in enumerate(sidebar_lines):
    if 'S-1535' in line:
        insert_sb = i + 1
        break

if insert_sb:
    sidebar_lines.insert(insert_sb, new_sidebar_entry)
    print(f"Inserted S-1536 in sidebar at line {insert_sb}")
else:
    print("WARNING: Could not find S-1535 in sidebar!")
    sidebar_lines.append(new_sidebar_entry)

sidebar_updated = '\n'.join(sidebar_lines)
with open('_sidebar.md', 'w') as f:
    f.write(sidebar_updated)
print("Written: _sidebar.md")

# ── 3. Push to GitHub ─────────────────────────────────────────────────────────
print("\nPushing to GitHub...")

def push(path, content, msg):
    sha = get_sha(path)
    result = push_file(path, content.encode(), sha=sha, message=msg)
    print(f"  ✓ {path} → {result.get('commit', {}).get('sha', 'OK')[:8]}")

push('stacks/s1536-the-durable-execution-stack-when-langgraph-gives-you-the-agent-and-temporal-gives-you-the-guarantee.md',
     open('stacks/s1536-the-durable-execution-stack-when-langgraph-gives-you-the-agent-and-temporal-gives-you-the-guarantee.md').read(),
     '[handbook-cron] S-1536: Durable Execution Stack — LangGraph + Temporal')
push('knowledge-pulse.md', tracker_updated,
     '[handbook-cron] Update tracker: I-2037 Durable Execution Stack')
push('_sidebar.md', sidebar_updated,
     '[handbook-cron] Sidebar: S-1536 Durable Execution Stack')

print("\nAll done.")
