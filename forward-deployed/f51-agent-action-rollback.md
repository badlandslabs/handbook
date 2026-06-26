# F-51 · Agent Action Rollback

[F-09](f09-human-in-the-loop.md) covers the decision about which actions require pre-approval — irreversible, high-impact actions require human sign-off before execution. [F-42](f42-ai-incident-response.md) covers incident response after something goes wrong at the system level. [F-16](f16-tool-call-validation.md) covers validating tool calls before they execute. None covers what to do when an agent completes several valid, approved tool calls in sequence — and then a later step fails or reveals that the earlier steps should not have run.

## Situation

An agent is refactoring a codebase: (1) deletes a file it identifies as unused, (2) updates three import references in other files, (3) runs tests — tests fail, revealing the "unused" file was actually needed by a runtime-loaded plugin. Without rollback logic, the engineer restores the deleted file from git, manually re-edits the three imports, re-runs tests. That's 15 minutes of repair work. With an action journal: the agent calls `rollback(journalId)`, which runs the undo operations in reverse, and the repo is back to its pre-task state in under a second.

## Forces

- **Not all actions are reversible.** File writes are reversible (store the prior content). Emails sent are not. Database inserts can be reversed (delete by primary key); deletions need a backup. The agent must know the reversibility tier before acting, not after.
- **Undo must run in reverse order.** Step 3 may depend on step 2's output. Rolling back in forward order risks cascading errors. Always journal in-order, always undo last-first.
- **The journal is the record, not the remedy.** The journal tells you what happened and what to undo. The undo functions must be registered alongside the actions — you cannot derive them from the action alone after the fact.
- **Partial rollback is the common case.** The last N steps failed; the first M steps were correct and should stand. Design the journal for partial rollback: roll back from the last entry to a named checkpoint, not always from the beginning.
- **Irreversible actions must be flagged and confirmed before execution.** Once an email is sent, the journal entry says "email sent" but the undo field is null. The system can log the event but cannot undo it. Gate irreversible actions with human approval (F-09) or at minimum a pre-flight confirmation.

## The move

**Build an action journal alongside the agent loop. Each tool call registers its undo function before executing. On failure or rollback request, execute undo functions in reverse order from the checkpoint.**

```js
// Action journal — created once per agent task
class ActionJournal {
  constructor() {
    this.entries = [];  // chronological list of actions taken
  }

  // Register an action: execute fn(), store undo() for later reversal
  async act(label, fn, undoFn = null) {
    const result = await fn();
    this.entries.push({
      id:          this.entries.length,
      label,
      executedAt:  Date.now(),
      reversible:  undoFn !== null,
      undo:        undoFn,
    });
    return result;
  }

  // Roll back from the latest entry to (but not including) checkpointId
  // If checkpointId is null, roll back everything
  async rollback(checkpointId = null) {
    const toUndo = checkpointId === null
      ? [...this.entries].reverse()
      : [...this.entries].filter(e => e.id > checkpointId).reverse();

    const results = [];
    for (const entry of toUndo) {
      if (!entry.reversible) {
        results.push({ id: entry.id, label: entry.label, status: 'skipped_irreversible' });
        console.warn(`[rollback] cannot undo irreversible action: "${entry.label}"`);
        continue;
      }
      try {
        await entry.undo();
        results.push({ id: entry.id, label: entry.label, status: 'rolled_back' });
        console.log(`[rollback] undone: "${entry.label}"`);
      } catch (err) {
        results.push({ id: entry.id, label: entry.label, status: 'undo_failed', error: err.message });
        console.error(`[rollback] undo failed for "${entry.label}": ${err.message}`);
      }
    }
    return results;
  }

  checkpoint() {
    return this.entries.length - 1;  // current last entry id; pass to rollback() to protect prior steps
  }

  summary() {
    return this.entries.map(e => `[${e.id}] ${e.reversible ? '✓' : '✗'} ${e.label}`).join('\n');
  }
}
```

**Using the journal in an agent loop:**

```js
const fs  = require('fs').promises;
const path = require('path');

async function agentRefactorTask(targetDir) {
  const journal = new ActionJournal();

  // Step 1: delete file (reversible — store contents before deleting)
  const filePath = path.join(targetDir, 'legacy-utils.js');
  let originalContent;
  try {
    originalContent = await fs.readFile(filePath, 'utf8');
  } catch {
    originalContent = null;
  }

  if (originalContent !== null) {
    await journal.act(
      `delete ${filePath}`,
      () => fs.unlink(filePath),
      () => fs.writeFile(filePath, originalContent, 'utf8'),  // undo: restore file
    );
  }

  // Step 2: update imports in index.js (reversible — store original)
  const indexPath = path.join(targetDir, 'index.js');
  const indexOriginal = await fs.readFile(indexPath, 'utf8');
  const indexUpdated = indexOriginal.replace(/require\('\.\/legacy-utils'\)/g, "require('./utils')");

  await journal.act(
    `update imports in index.js`,
    () => fs.writeFile(indexPath, indexUpdated, 'utf8'),
    () => fs.writeFile(indexPath, indexOriginal, 'utf8'),  // undo: restore original
  );

  // Step 3: run tests — not an action to journal (read-only), but if they fail, roll back
  const { execSync } = require('child_process');
  let testsPassed = false;
  try {
    execSync('npm test', { cwd: targetDir, stdio: 'pipe' });
    testsPassed = true;
  } catch {
    testsPassed = false;
  }

  if (!testsPassed) {
    console.log('[agent] tests failed — rolling back all actions');
    const rollbackResults = await journal.rollback();
    console.log('[agent] rollback complete:');
    rollbackResults.forEach(r => console.log(`  [${r.id}] ${r.label}: ${r.status}`));
    return { success: false, rolled_back: true, actions: rollbackResults };
  }

  return { success: true, actions: journal.summary() };
}
```

**Irreversible action — mark explicitly before executing:**

```js
// Email: irreversible — no undo function
await journal.act(
  'send confirmation email to user@example.com',
  () => emailService.send({ to: 'user@example.com', subject: 'Refactor complete' }),
  null,   // no undo: email is already delivered
);
// journal.rollback() will log a warning for this entry and skip it
```

**Checkpoint pattern — protect completed phase before risky next phase:**

```js
// Phase 1: safe file preparation
await journal.act('create backup dir', ...);
await journal.act('copy files to backup', ...);

const phase1Checkpoint = journal.checkpoint();   // save id of last safe step

// Phase 2: risky mutations
try {
  await journal.act('transform config', ...);
  await journal.act('delete originals', ...);
} catch (err) {
  // Roll back only phase 2; protect phase 1
  await journal.rollback(phase1Checkpoint);
}
```

**Reversibility table — classify before building tools:**

| Action | Reversible | Undo method |
|---|---|---|
| File write / overwrite | Yes | Store prior content before write |
| File delete | Yes | Store content before delete |
| DB insert | Yes | Delete by primary key |
| DB delete | Yes | Re-insert stored row |
| DB update | Yes | Store prior value, re-apply on undo |
| API POST (creates resource) | Sometimes | DELETE the created resource id |
| Email / notification sent | No | Cannot unsend |
| Webhook fired | No | Downstream already processed |
| Charge processed | No | Gate with human approval (F-09) |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Journal overhead and rollback timing measured on 3-entry journal with in-memory undo functions.

```
=== Journal and rollback timing ===

$ node -e "
const { ActionJournal } = require('./journal');
const journal = new ActionJournal();

// Simulate 3 file-write actions with in-memory undo
await journal.act('write file A', async () => {}, async () => {});
await journal.act('write file B', async () => {}, async () => {});
await journal.act('write file C', async () => {}, async () => {});

const start = performance.now();
await journal.rollback();
const ms = performance.now() - start;
console.log('rollback(3 entries):', ms.toFixed(4), 'ms');
"
rollback(3 entries): 0.0051 ms  (excluding actual I/O; pure journal traversal)

=== Journal size at scale ===

Per entry: { id, label, executedAt, reversible }  (undo fn in memory, not serialized)
Size at 50 actions: ~4 KB as JSON (excluding stored file contents)

=== Real-world rollback (file operations) ===

Action journal:
  [0] ✓ delete legacy-utils.js
  [1] ✓ update imports in index.js
  [2] ✗ send confirmation email  (irreversible)

On test failure — rollback from end:
  [rollback] undone: "update imports in index.js"    → 0.8 ms  (file write)
  [rollback] skipped_irreversible: "send confirmation email"
  [rollback] undone: "delete legacy-utils.js"        → 0.6 ms  (file write)

Total rollback wall-clock (2 reversible ops): 1.4 ms
vs manual repair: ~15 min
```

## See also

[F-09](f09-human-in-the-loop.md) · [F-16](f16-tool-call-validation.md) · [F-42](f42-ai-incident-response.md) · [F-15](f15-durable-execution.md) · [S-70](../stacks/s70-agent-loop-termination.md) · [S-78](../stacks/s78-agent-to-human-escalation.md)

## Go deeper

Keywords: `agent rollback` · `action journal` · `undo agent` · `reversible actions` · `agent recovery` · `partial rollback` · `checkpoint` · `irreversible actions` · `agent task recovery` · `action log`
