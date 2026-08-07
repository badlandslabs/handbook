# S-2255 · The Re-Reading Loop Stack — When Your Agent Forgets What It Already Read

Your agent spent 20 minutes reading your codebase. You ask it to fix the bug at line 847 of `auth/middleware.py`. It re-runs a file search. Finds the same file. Reads it again. And again. The session burns through 60% of its context budget re-reading the same 3,000-line file it already read — because the compression summary dropped the line numbers and the agent no longer knows where to look.

This is the **re-reading loop**: a compression-induced cycle where context summarization strips exact identifiers, the agent can't locate previously-handled content, re-searches, re-fetches, re-fills the context, and re-triggers compression. The loop costs tokens, compounds latency, and degrades task quality — all without a single error message.

## Forces

- **Summarization is lossy by default.** LLM summarizers optimize for fluency and coverage. Exact identifiers — file paths, line numbers, function names, API keys, database IDs — are treated as low-information tokens and dropped. The summary is faithful; it is not complete.
- **Agents locate content by identifier, not by meaning.** When a human says "fix the code from earlier," the agent needs the exact file:line to act. When that identifier was in a compressed message, the agent searches semantically, which matches the same file it already read, wasting context on a no-op.
- **Context rot makes the loop invisible to monitoring.** Standard token-count dashboards look healthy. The failure is qualitative, not quantitative — the agent is using tokens, just not productively. No alert fires because no error occurred.
- **The re-reading loop compounds with session length.** Each compression cycle drops more identifiers. Each re-search re-fills the context. The agent gets progressively slower and less accurate without any crash or explicit failure signal.

## The Move

### 1. Instrument for re-read detection

Track file/URL/ID access frequency per session. Flag any resource accessed more than once as a re-read event.

```python
from collections import defaultdict

class ReReadTracker:
    def __init__(self):
        self.access_log = defaultdict(list)

    def track(self, session_id: str, resource: str, turn: int):
        self.access_log[(session_id, resource)].append(turn)

    def re_reads(self, session_id: str) -> dict[str, list[int]]:
        """Return {resource: [turn_numbers]} for resources accessed multiple times."""
        return {
            resource: turns
            for (sid, resource), turns in self.access_log.items()
            if sid == session_id and len(turns) > 1
        }

    def re_read_rate(self, session_id: str) -> float:
        re_reads = self.re_reads(session_id)
        total_turns = max(
            turn for (sid, _), turns in self.access_log.items() if sid == session_id
            for turn in turns
        ) if re_reads else 1
        return sum(len(turns) - 1 for turns in re_reads.values()) / max(total_turns, 1)
```

### 2. Anchor identifiers before compression

Before any summarization pass, extract a structural inventory of exact values and preserve them as a lightweight header.

```python
import re

IDENTIFIER_PATTERNS = [
    r'[/\\][\w\-\.]+/[\w\-\.]+\.py',
    r'line\s+\d+',
    r'\b(line|fn|func|class)\s+\d+',
    r'`[^`]+`',
    r'["\'][\w\-\.]+/[\w\-\./:]+["\']',
    r'GET|POST|PUT|DELETE /[\w/\-\{\}]+',
]

def extract_identifiers(text: str) -> list[str]:
    anchors = []
    for pattern in IDENTIFIER_PATTERNS:
        anchors.extend(re.findall(pattern, text))
    return list(set(anchors))

def compression_header(messages: list[dict]) -> str:
    """Build identifier anchor block before summarization."""
    all_text = " ".join(m["content"] for m in messages if m.get("content"))
    anchors = extract_identifiers(all_text)
    if not anchors:
        return ""
    header = "# Preserved identifiers (do not re-fetch)\n"
    header += "\n".join(f"- {a}" for a in anchors[:50])  # cap at 50
    return header
```

### 3. Use structured compression over free-form summarization

Structured summaries act as checklists: the agent can verify whether a required identifier is in the summary before deciding to re-fetch.

```python
COMPRESSION_TEMPLATE = """\
Summarize the following messages as a structured record.

## Task: {task_description}

## Key Decisions Made
1. ...

## Preserved Identifiers (file paths, IDs, URLs — do NOT re-fetch)
- ...

## Actions Taken
- ...

## Outstanding Work
- ...

## Context Required to Continue
- ...
"""

def structured_summary(messages: list[dict], task: str) -> str:
    header = compression_header(messages)
    prompt = COMPRESSION_TEMPLATE.format(task_description=task)
    if header:
        prompt += f"\n\n# Identifier Preservation Block\n{header}"
    return llm.complete(prompt)
```

### 4. Check before re-fetch

Before the agent calls a search or retrieval tool, inject a re-read check that compares the query against known identifiers in the compression summary.

```python
def pre_fetch_check(agent_context: dict, query: str, summary: str) -> dict:
    identifiers = extract_identifiers(summary)
    matched = [i for i in identifiers if i.lower() in query.lower()]
    if matched:
        return {
            "action": "BLOCK_REFETCH",
            "reason": f"Identifiers found in compression summary: {matched}",
            "suggestion": "Use the preserved identifier directly instead of re-searching."
        }
    return {"action": "ALLOW_FETCH"}
```

### 5. Monitor re-read rate as a quality signal

Re-read rate above 15% per session is the operational indicator of compression damage. Track it in your observability stack alongside token count and latency.

```python
# Alert threshold: re-read rate > 15% in any session window
ALERT_THRESHOLD_RE_READ_RATE = 0.15

def check_re_read_health(tracker: ReReadTracker, session_id: str):
    rate = tracker.re_read_rate(session_id)
    if rate > ALERT_THRESHOLD_RE_READ_RATE:
        send_alert(
            f"Session {session_id}: re-read rate {rate:.1%} exceeds {ALERT_THRESHOLD_RE_READ_RATE:.1%}",
            severity="warning"
        )
```

## Cross-links

- [S-1467 · Context Rot](/stacks/s1467-the-context-rot-stack-when-your-agent-is-still-running-but-no-longer-thinking.md) — this is the mechanism that *causes* context rot; S-2255 is the specific re-reading symptom of identifier loss
- [S-2206 · Context Compilation](/stacks/s2206-the-context-compilation-stack-when-your-agent-re-reads-the-same-raw-materials-every-single-turn.md) — addresses re-reading at the raw-material level (pre-summarization); S-2255 is the post-compression loop it creates
- [S-753 · Compression Guideline Optimization](/stacks/s753-compression-guideline-optimization-the-feedback-loop-that-fixes-context-compaction.md) — ACON-style adaptive compression can be directed to preserve identifiers as a learnable guideline
- [S-1631 · Memory Laundering](/stacks/s1631-the-memory-laundering-stack-when-memory-compression-cleans-adversarial-content-but-preserves-its-harm.md) — compression corrupts content in different ways; S-2255 focuses on identifier loss specifically
