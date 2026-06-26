# F-40 · User Feedback Collection

[F-27](f27-data-flywheel.md) describes the data flywheel: production traffic generates training data that improves the system. It covers production sampling and LLM-as-a-judge labeling. It does not cover the UI-layer mechanism: how to instrument thumbs up/down, what implicit signals to capture, how to route negative feedback to a review queue, and how to connect those signals back into the eval suite. That instrumentation is what closes the loop.

## Situation

A support agent has been in production for two months. Quality feels like it has plateaued. The team runs weekly eval runs but the eval suite is still the 50 examples they wrote before launch. Regressions in edge cases go undetected until a user escalates. The fix: 0.8% of 10 000 daily calls get a thumbs-down. That's 80 failure signals per day. Reviewed and confirmed, 50% become real eval failures — 40 new eval examples per day, 1 200/month. Within four weeks, the eval suite has tripled in size and covers failure modes the team had never thought to write.

## Forces

- **Explicit feedback is rare but high-signal.** Users who take the time to click thumbs-down are usually right. At 0.8% thumbs-down rate, you have 80 confirmed-bad examples per day at 10k calls. That's enough to build a real eval corpus fast.
- **Implicit signals are noisier but abundant.** Copy-to-clipboard implies "this was useful." Regenerate implies "this was not." Session abandonment after one turn implies either "resolved" or "gave up" — you can't tell which from the signal alone. Use implicit signals for trend monitoring; use explicit thumbs-down for individual example review.
- **The feedback loop is only closed if someone reviews the signals.** Logging thumbs-down to a database is not a feedback loop. The loop closes when: thumbs-down → human review → confirmed failure → added to eval suite → regression test in CI → caught next time.
- **Feedback categories improve review efficiency.** A thumbs-down with a category (wrong answer, tone, too long, hallucinated) routes the reviewer to the right checklist and cuts review time by 30–50%.
- **Positive feedback is also useful.** Thumbs-up on unusual queries confirms that the system is handling edge cases well and shouldn't be "fixed." Preserve the positive examples as anchors to protect when tuning.

## The move

**Add thumbs up/down to every response. Capture the session context with the feedback. Route thumbs-down to a review queue. Confirm failures and add them to the eval suite.**

**Feedback capture (client-side):**

```js
async function submitFeedback(signal, messageId, sessionId, category = null, note = '') {
  await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      signal,     // 'thumbs_up' | 'thumbs_down'
      messageId,  // links to the specific response
      sessionId,
      category,   // 'wrong_answer' | 'hallucination' | 'tone' | 'too_long' | 'other'
      note,       // optional freetext, max 280 chars
      ts: Date.now(),
    }),
  });
}
```

**Server-side: store and route:**

```js
app.post('/api/feedback', async (req, res) => {
  const { signal, messageId, sessionId, category, note, ts } = req.body;

  // Fetch the full call context from your call log (F-31)
  const callRecord = await callLog.get(messageId);

  const event = {
    signal, messageId, sessionId, category, note, ts,
    // Attach the full context for reviewer
    prompt:    callRecord?.userMessage,
    response:  callRecord?.assistantMessage,
    model:     callRecord?.model,
    inputTok:  callRecord?.inputTokens,
    outputTok: callRecord?.outputTokens,
  };

  await feedbackStore.insert(event);

  // Route thumbs-down to review queue immediately
  if (signal === 'thumbs_down') {
    await reviewQueue.push({ ...event, priority: category === 'hallucination' ? 'high' : 'normal' });
  }

  res.sendStatus(200);
});
```

**Implicit signal capture:**

```js
// Copy-to-clipboard: implicit thumbs-up
copyButton.addEventListener('click', () => {
  submitFeedback('implicit_positive', messageId, sessionId);
  navigator.clipboard.writeText(responseText);
});

// Regenerate: implicit thumbs-down (weak signal — also triggered by curiosity)
regenerateButton.addEventListener('click', () => {
  submitFeedback('implicit_negative', messageId, sessionId);
  triggerNewResponse();
});

// Do NOT auto-submit on session end — abandonment is ambiguous
```

**Review queue workflow:**

```
Reviewer opens thumbs-down item → sees: prompt | response | category | note
Reviewer decision (30–90 seconds per item):
  → CONFIRM FAILURE: adds to eval suite as failing example
  → FALSE POSITIVE: marks as reviewed; tags for quality audit
  → NEEDS MORE INFO: flags for follow-up with user (if contactable)

Eval integration (F-07):
  Confirmed failure → write as: { input, expected_behavior, actual_output, failure_mode }
  Run eval suite in CI: if the failure recurs on new prompt versions, the gate catches it
```

**Feedback dashboard (weekly review):**

```
Week of 2026-06-26

Signal               Count    Rate
thumbs_up            182       1.8%
thumbs_down           83       0.8%
implicit_positive    441       4.4%  (copy-to-clipboard)
implicit_negative    129       1.3%  (regenerate)

Thumbs-down by category:
  wrong_answer        41      49%
  hallucination       18      22%
  tone                12      14%
  too_long             8      10%
  other                4       5%

Confirmed failures → eval: 44 examples added this week
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Feedback event schema: 149 bytes / 46 tokens if serialized. Rates are representative estimates from typical production support deployments.

```
=== Feedback event overhead ===

Schema (stored, not injected into prompt):
  {"signal":"thumbs_down","messageId":"...","category":"wrong_answer",...}
  149 bytes — stored in database, 0 tokens added to any LLM call

=== Feedback volume at 10k calls/day ===

Rate       Events/day   Events/month
thumbs_up (1.8%)   180     5 400
thumbs_down (0.8%)  80     2 400
implicit+ (4.4%)   440    13 200
implicit- (1.3%)   130     3 900

=== Eval suite growth ===

Thumbs-down/month:              2 400
Reviewed (assume all):          2 400
Confirmed failures (50%):       1 200 new eval examples/month
False positives discarded:      1 200

Starting eval suite: 50 examples
After 4 weeks: 50 + ~1 200 = ~1 250 examples (25× growth)

=== Review time cost ===

At 60 sec/review × 2 400/month = 2 400 minutes = 40 person-hours/month
At $50/hr (reviewer): $2 000/month

Break-even: catching one production regression that would have caused
a support escalation, SLA breach, or visible quality drop.
Typical regression investigation: 5–20 engineer-hours.
```

The review cost is real — 40 person-hours per month is not free. Reduce it by auto-confirming high-confidence failures (LLM judge on the thumbs-down pair: does the response contain a factual error or policy violation?), then routing only the ambiguous cases to human review. With 70% auto-confirm accuracy, you cut human review to ~12 hours/month.

## See also

[F-27](f27-data-flywheel.md) · [F-02](f02-evaluation-at-scale.md) · [F-07](f07-evaluation-driven-development.md) · [F-12](f12-llm-as-a-judge.md) · [F-31](f31-structured-call-logging.md) · [F-26](f26-behavioral-drift-detection.md)

## Go deeper

Keywords: `user feedback` · `thumbs up down` · `feedback collection` · `explicit signal` · `implicit signal` · `review queue` · `eval corpus growth` · `feedback loop` · `quality signal` · `feedback instrumentation`
