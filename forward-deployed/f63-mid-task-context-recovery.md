# F-63 · Mid-Task Context Recovery

[S-21](../stacks/s21-context-compaction.md) covers context compaction — summarizing old conversation turns when the context window fills, so the session can continue. [F-39](f39-session-state-persistence.md) covers persisting session state across sessions with a structured state object. Neither covers the specific failure mode of a *long-running task* approaching the context limit mid-execution: when you're 12 steps into a 20-step task, blanket compaction loses the step results that the remaining steps depend on.

## Situation

An agent is auditing a 40-file codebase: checking each file for security issues, building an issues list, and producing a final report. It has completed 28 of 40 files. At this point the context is at 82% capacity — each file review added its tool call results and reasoning. S-21 compaction would summarize the conversation history, but the model needs the issues found in files 1-28 to be *enumerable* in the final report — not summarized into "some issues were found." Blanket compaction loses that enumerable list. Without mid-task context recovery: the agent either hits the context limit and fails, or compaction erases the accumulated work product. With it: the agent checkpoints the 28-file issues list into a structured state object, compresses the message history down to a compressed summary + the state object, and continues with enough headroom to finish.

## Forces

- **Task execution state and conversation history have different preservation requirements.** The conversation history (tool call traces, reasoning steps, intermediate responses) is expendable — it's how the agent got here, not what it found. The task execution state (the enumerable issues list, decisions made, step results that downstream steps need) is irreplaceable. Compacting without distinguishing these destroys the irreplaceable while saving the expendable.
- **"Approaching the limit" is the right trigger, not "at the limit."** Once the context is full, the next tool call fails. Trigger recovery when context usage exceeds 70-75% of the limit — this leaves enough headroom to (1) run the compaction call itself (which adds tokens), (2) inject the checkpoint, and (3) complete at least several more steps before hitting the limit again. Monitor token usage after every tool call.
- **The checkpoint must be designed ahead of time, not improvised at the limit.** You can't decide what to preserve when the context is at 95%. Define the task's essential state schema at design time — the same discipline as S-38 (agent state design). The schema answers: what would a fresh agent need to pick up this task from step N? That's exactly what to preserve.
- **Compaction has a cost.** Summarizing 80 turns of conversation into a compact summary requires a model call. At 70% trigger, you have ~30% of the window to work with. The compaction call consumes some of that. Budget for it: a 500-token compaction prompt + up to 1000 tokens of summary output leaves you with 25-28% of your original window for the continuation. For a 200k-token context model, that's 50-56k tokens — enough for many more steps.
- **Every task type has a natural checkpoint unit.** For file audits: each completed file. For research synthesis: each completed section. For multi-step data processing: each pipeline stage. Build checkpointing into the task loop at the natural unit; don't try to recover at the limit only.

## The move

**Define the task's essential state schema upfront. Checkpoint after each natural unit. When context exceeds 70%, run a compaction call to summarize message history, inject the checkpoint as a structured state block, and continue from the last completed step.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client = new Anthropic();

// --- Context usage monitoring ---

function contextUsagePct(usage, modelContextLimit) {
  // usage from response.usage: { input_tokens, output_tokens }
  return (usage.input_tokens / modelContextLimit) * 100;
}

// Context limits by model (tokens)
const MODEL_CONTEXT_LIMITS = {
  'claude-haiku-4-5-20251001': 200_000,
  'claude-sonnet-4-6':         200_000,
};

// --- Task state (define this for your specific task type) ---
// Example: multi-file security audit

function createAuditState(totalFiles) {
  return {
    task:          'security_audit',
    totalFiles,
    completedFiles: [],  // { file, issues: [{line, severity, description}] }
    pendingFiles:   [],  // remaining file paths
    summary:        { critical: 0, high: 0, medium: 0, low: 0 },
    decisions:      [],  // key decisions made during audit
    startedAt:      new Date().toISOString(),
    lastCheckpoint: null,
  };
}

function updateAuditState(state, completedFile, issues) {
  state.completedFiles.push({ file: completedFile, issues });
  state.pendingFiles = state.pendingFiles.filter(f => f !== completedFile);
  for (const issue of issues) {
    state.summary[issue.severity] = (state.summary[issue.severity] ?? 0) + 1;
  }
  state.lastCheckpoint = new Date().toISOString();
}

// Serialize state for context injection (compact but complete)
function serializeState(state) {
  const issuesFlat = state.completedFiles.flatMap(cf =>
    cf.issues.map(i => `${cf.file}:${i.line} [${i.severity}] ${i.description}`)
  );

  return `## Task Checkpoint (${state.lastCheckpoint})
Task: ${state.task}
Progress: ${state.completedFiles.length}/${state.totalFiles} files completed
Summary: critical=${state.summary.critical} high=${state.summary.high} medium=${state.summary.medium} low=${state.summary.low}
Pending files: ${state.pendingFiles.slice(0, 20).join(', ')}${state.pendingFiles.length > 20 ? ` (+${state.pendingFiles.length - 20} more)` : ''}

Issues found (${issuesFlat.length} total):
${issuesFlat.join('\n')}

Key decisions: ${state.decisions.join('; ') || 'none'}`;
}

// --- Compaction call ---

async function compactHistory(messages, taskGoal, model) {
  const historyText = messages
    .map(m => `[${m.role}]: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content).slice(0, 200)}`)
    .join('\n');

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',  // use cheap model for compaction
    max_tokens: 800,
    system:     'You are a conversation compactor. Summarize the key actions taken and findings from this conversation into a compact technical summary. Preserve all specific findings, file names, line numbers, and decisions. Omit reasoning traces and intermediate steps.',
    messages:   [{ role: 'user', content: `Task goal: ${taskGoal}\n\nConversation history to compact:\n${historyText.slice(0, 20000)}` }],
  });

  return resp.content[0].text;
}

// --- Main mid-task recovery function ---

const CONTEXT_TRIGGER_PCT  = 70;  // trigger compaction at 70% usage
const COMPACTION_BUDGET_PCT = 25; // expect compaction to use 25% of remaining window

async function runAuditWithRecovery(files, model = 'claude-haiku-4-5-20251001') {
  const contextLimit = MODEL_CONTEXT_LIMITS[model] ?? 200_000;
  const state        = createAuditState(files.length);
  state.pendingFiles = [...files];

  let messages    = [];
  const systemPrompt = `You are a security auditor. Review each file for security issues.
Return findings as JSON: { issues: [{line: number, severity: "critical"|"high"|"medium"|"low", description: string}] }`;

  let compactionCount = 0;

  for (const file of files) {
    // Audit the file
    messages.push({
      role:    'user',
      content: `Audit this file for security issues:\n\nFile: ${file.path}\n\n${file.content}`,
    });

    const resp = await client.messages.create({
      model, max_tokens: 512, system: systemPrompt, messages,
    });

    const responseText = resp.content[0].text;
    messages.push({ role: 'assistant', content: responseText });

    // Parse and checkpoint
    let issues = [];
    try { issues = JSON.parse(responseText)?.issues ?? []; } catch { /* malformed */ }
    updateAuditState(state, file.path, issues);

    // Check context usage after this step
    const usagePct = contextUsagePct(resp.usage, contextLimit);
    console.debug(`[context] ${file.path}: ${usagePct.toFixed(1)}% used`);

    if (usagePct >= CONTEXT_TRIGGER_PCT) {
      console.log(`[recovery] Context at ${usagePct.toFixed(1)}% — compacting history`);
      compactionCount++;

      // 1. Compact the message history
      const compactedSummary = await compactHistory(messages, 'security audit of codebase', model);

      // 2. Serialize the task state (the irreplaceable part)
      const checkpoint = serializeState(state);

      // 3. Reset messages with: compressed summary + checkpoint
      messages = [
        {
          role:    'user',
          content: `[CONTEXT RECOVERY — compaction ${compactionCount}]\n\nCompacted history:\n${compactedSummary}\n\n${checkpoint}\n\nContinue the security audit on the remaining files listed above.`,
        },
        { role: 'assistant', content: 'Understood. Resuming audit from checkpoint. Continuing with remaining files.' },
      ];

      console.log(`[recovery] Compacted ${compactionCount} time(s). Messages reset; state preserved.`);
    }
  }

  return {
    state,
    compactionCount,
    totalIssues: state.completedFiles.flatMap(cf => cf.issues).length,
  };
}
```

**Context budget planning for long tasks:**

```js
// Before starting a long task, estimate how many steps you can complete
// before hitting the recovery trigger.

function estimateStepsBeforeRecovery(perStepTokens, modelContextLimit, triggerPct = 70) {
  const triggerTokens = modelContextLimit * (triggerPct / 100);
  return Math.floor(triggerTokens / perStepTokens);
}

// Example: 200k context, 3000 tokens per file review
// estimateStepsBeforeRecovery(3000, 200_000) → 46 files before first compaction
// Plan: 40-file audit won't need compaction; 80-file audit needs ~1 compaction
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Token usage estimates from a simulated 40-file audit, each file ~800 tokens, review response ~120 tokens. Context compaction call measured on claude-haiku.

```
=== Context growth without recovery (40-file audit, 200k context model) ===

Per file: ~800 tok input (file content) + 120 tok output (issues JSON) + overhead
Cumulative growth per file: ~950 tok average (with system prompt, prior history)

File  5: ~6 000 tok total  ( 3%)
File 10: ~13 500 tok total ( 7%)
File 20: ~29 000 tok total (15%)
File 30: ~47 000 tok total (24%)
File 40: ~67 000 tok total (34%)  ← 40-file audit stays well within limit

File 70: ~116 000 tok total (58%)
File 80: ~138 000 tok total (69%)  ← trigger at 70% fires here for an 80-file audit
File 90: would exceed context; recovery needed at file ~81

=== Recovery at 70% trigger (file 81 of 100) ===

Before compaction:
  Messages: 162 turns, ~140 000 tokens
  State checkpoint: 81 completed files, ~3 200 tokens (issues list + summary)

Compaction call (Haiku, cheap model):
  Input: 20 000 tok (history sample, truncated to fit)
  Output: ~700 tok compact summary
  Cost: $0.0163 + $0.0028 = $0.019

After recovery:
  Messages reset to: 2 turns (compacted history + acknowledgement)
  Injected: 3 200-tok checkpoint (all 81 issues, pending files)
  Total context: ~3 900 tok (2% of limit)
  Available headroom: 196 000 tok — enough for 206 more file reviews

=== What the checkpoint preserves ===

Essential (in checkpoint):                   Dropped in compaction:
  ✓ Issues found per file (enumerable)         ✗ File content (already processed)
  ✓ Files completed and pending                ✗ Intermediate reasoning
  ✓ Severity summary counts                    ✗ Model's self-correction steps
  ✓ Key decisions made                         ✗ Raw tool call traces
  ✓ Progress count (81/100)                    ✗ Prior user messages about scope

The final report needs the issues list — it survives.
The final report doesn't need to re-read file #23 — it doesn't.
```

## See also

[S-21](../stacks/s21-context-compaction.md) · [S-38](../stacks/s38-agent-state-design.md) · [F-39](f39-session-state-persistence.md) · [F-15](f15-durable-execution.md) · [S-54](../stacks/s54-multi-turn-conversation-design.md) · [S-56](../stacks/s56-preflight-token-check.md)

## Go deeper

Keywords: `context recovery` · `mid-task compaction` · `context limit` · `long-running agent` · `task checkpoint` · `context window full` · `state preservation` · `context compaction` · `token budget` · `agent task recovery`
