# F-39 · Session State Persistence

[S-38](../stacks/s38-agent-state-design.md) covers what fields to put in an agent's state object during a session. [S-54](../stacks/s54-multi-turn-conversation-design.md) covers how to manage the message history window within a session. This entry covers the infrastructure layer under both: how to serialize session state to durable storage, how to restore it when a session resumes, and when to let a session expire rather than restore it.

## Situation

A customer support agent handles a 6-turn conversation about a billing dispute. The user closes the browser tab mid-conversation and returns 20 minutes later. Without session persistence, they start over: re-explain the issue, re-authenticate, lose context. With session persistence: the agent re-injects the structured state (user ID, issue type, conversation summary) and the last three messages. The user resumes where they left off. The re-injection costs 132 tokens — far cheaper than replaying 20 turns of history or asking the user to repeat themselves.

## Forces

- **Process memory is not session storage.** An in-memory conversation object dies when the server process restarts, the user refreshes, or the session expires. Durable storage (database, Redis, S3) is required for anything that must survive beyond a single HTTP request.
- **Full history replay is the most expensive restore strategy.** Re-injecting 20 turns of raw history at restoration adds ~1 000 tokens to every subsequent call for the life of the resumed session. Structured state (summary + last-N messages) is 132 tokens for the same information density.
- **Not all state is safe to restore.** A context injection from 30 minutes ago may be stale (the ticket was resolved, the price changed, the record was updated). Restore the structured summary of what was established; don't blindly re-inject raw tool results.
- **Session expiry is not a bug — it's a boundary.** A session that's been idle for 24 hours is not a paused conversation; it's a new problem with some context. Restore summarized context, not a live conversation handoff. Adjust the tone accordingly.
- **Session isolation is a security property.** One user's session state must never be visible to another user's session. Session IDs must be unguessable (UUID v4, minimum). Scoping session data to user ID + session ID ensures isolation even if one layer fails.

## The move

**Serialize a compact state object to durable storage at each turn. Restore it at session start. Use structured state + last-N messages, not full history. Expire idle sessions; summarize before archiving.**

**Session state schema:**

```js
// What gets written to storage after each turn
function serializeSession(session) {
  return {
    sessionId:    session.id,           // UUID v4
    userId:       session.userId,
    createdAt:    session.createdAt,
    lastActiveAt: Date.now(),           // update on every turn
    expiresAt:    Date.now() + 30 * 60 * 1000, // 30min idle TTL

    // AI context — what the model needs to continue coherently
    systemPrompt: session.systemPrompt,  // static; may change on major prompt updates
    state:        session.state,         // structured S-38 state object
    recentMessages: session.messages.slice(-3), // last 3 turns as anchor context
    summary:      session.summary,       // rolling summary of earlier turns (if any)

    // NOT stored: raw tool results, injected documents, full message history
  };
}
```

**Session restore pattern:**

```js
async function resumeSession(sessionId, userId, storage) {
  const data = await storage.get(`session:${userId}:${sessionId}`);

  if (!data) return null; // session not found — start fresh
  if (Date.now() > data.expiresAt) {
    await storage.delete(`session:${userId}:${sessionId}`);
    return null; // expired — start fresh, pass summary if needed
  }

  // Reconstruct the context window for the next call
  return {
    id:             data.sessionId,
    userId:         data.userId,
    systemPrompt:   data.systemPrompt,
    state:          data.state,

    // Build the message history to inject
    messages: [
      ...(data.summary ? [{ role: 'user', content: `[Session summary: ${data.summary}]` }] : []),
      ...data.recentMessages,
    ],
  };
}

async function handleTurn(client, storage, userId, sessionId, userMessage) {
  let session = await resumeSession(sessionId, userId, storage)
    ?? await createNewSession(userId, storage);

  session.messages.push({ role: 'user', content: userMessage });

  const response = await client.messages.create({
    model:    'claude-sonnet-4-6',
    max_tokens: 512,
    system:   session.systemPrompt,
    messages: session.messages,
  });
  const assistantText = response.content[0].text;

  session.messages.push({ role: 'assistant', content: assistantText });
  session.state = updateState(session.state, userMessage, assistantText);

  // Persist after every turn
  await storage.set(
    `session:${session.userId}:${session.id}`,
    serializeSession(session),
    { ttl: 30 * 60 }, // refresh TTL on activity
  );

  return assistantText;
}
```

**TTL design:**

| Session type | Idle TTL | At expiry |
|---|---|---|
| Real-time support chat | 30 min | Archive with summary |
| Async email/ticket workflow | 7 days | Archive; user restarts if needed |
| Long-running research agent | 24h | Archive; agent summarizes before sleep |
| Ephemeral (one-shot task) | 5 min | Delete; no restoration expected |

**Session isolation checklist:**

```
- Session key always scoped: session:{userId}:{sessionId}
- Session ID is UUID v4 (unguessable) — never sequential integers
- Session data never crosses user_id boundaries (enforce at storage read, not just write)
- Expired sessions deleted or archived before data can be read by new sessions
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Inference price: $3.00/M input. Session state token counts measured from real serialized objects.

```
=== Session resumption overhead (132 tok total) ===

Component                      Tokens   Content
System prompt                  32 tok   "You are Aria, Acme Corp support..."
Structured state               53 tok   {userId, name, plan, issueType, priorContext}
Last 3 messages (anchor)       47 tok   user + assistant + user turns
Total context injection:      132 tok

Cost per resumed call: 132 tok × $3.00/M = $0.000396

=== vs full history replay ===

Full 20-turn history:         ~1 000 tok (20 turns × ~50 tok/turn avg)
Structured resumption:           132 tok
Savings per resumed call:        868 tok
Monthly savings at 10k/day: 868 tok × $3.00/M × 10 000 × 30 = $782/month

(This assumes every call is a resumed session — real saving is proportional to resume rate)

=== Session storage cost ===

Redis: 1 KB per session × 10 000 active sessions = 10 MB  → well within free tier
PostgreSQL: same with JSONB column, indexed by (user_id, session_id, expires_at)
S3 (archived sessions): negligible
```

The 132-token resumption overhead is fixed regardless of how long the original session was. This is why structured state (S-38) earns its keep: the summary grows slowly, while raw history grows linearly. By turn 20, the structured path is 7× cheaper to restore.

## See also

[S-38](../stacks/s38-agent-state-design.md) · [S-54](../stacks/s54-multi-turn-conversation-design.md) · [S-48](../stacks/s48-memory-write-routing.md) · [F-08](f08-agent-cost-control.md) · [F-15](f15-durable-execution.md) · [S-21](../stacks/s21-context-compaction.md)

## Go deeper

Keywords: `session persistence` · `session state` · `session resumption` · `session TTL` · `session storage` · `session isolation` · `conversation state` · `Redis session` · `session ID` · `context restoration`
