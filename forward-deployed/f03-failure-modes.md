# F-03 · Failure Modes

The specific ways AI systems break in production, and what to do about each one.

## Forces
- AI failures are probabilistic and subtle — they don't throw exceptions
- The same failure mode looks different depending on where in the pipeline it occurs
- Failure rate compounds across pipeline steps (see [S-05](../stacks/s05-multi-agent-patterns.md))
- Users rarely report AI failures; they just stop using the feature

## The move

**The common failure modes, and their fixes:**

### Hallucination
The model confidently states something false.  
**Fix:** Ground outputs in retrieved facts (see [S-07 RAG](../stacks/s07-rag.md)). Add a verification step. Prompt: "Only use facts from the context below. If the answer isn't there, say so."

### Context overflow
The input exceeds the context window; the model truncates silently or errors.  
**Fix:** Count tokens before sending (see [S-02](../stacks/s02-context-budget.md)). Chunk and summarize long documents. Set hard limits and fail explicitly.

### Tool call failure
The model calls a tool with invalid parameters, or the tool returns an error.  
**Fix:** Validate tool inputs server-side. Return structured error messages the model can parse. Add retry logic with a max retry budget.

### Prompt injection
Malicious content in user input overrides your system prompt.  
**Fix:** Never concatenate user input directly into your system prompt. Use separate `user` role for user content. Add input sanitization for high-risk deployments.

### Model degradation
The model's output quality drops over time as the provider updates the model.  
**Fix:** Pin model versions (use `claude-sonnet-4-6-20251001` not `claude-sonnet-4-6`). Run your eval suite on every model update before switching.

### Silent regression
Quality drops but no alert fires because you're not measuring the right things.  
**Fix:** Eval suite with coverage of your actual use cases. Alert on metric change, not just crashes. See [F-02](f02-evaluation-at-scale.md).

### Rate limiting
API calls fail at volume because you've hit provider rate limits.  
**Fix:** Implement exponential backoff with jitter. Track rate limit headers. Queue requests and shed gracefully under load.

## Receipt
> Receipt pending — 2026-06-25. Failure modes synthesized from production AI deployment experience and public post-mortems. Specific failure rates vary by system; measure yours.

## See also
[F-01](f01-shipping-ai.md) · [F-02](f02-evaluation-at-scale.md) · [S-05](../stacks/s05-multi-agent-patterns.md)

## Go deeper
Keywords: `LLM hallucination` · `prompt injection` · `model version pinning` · `exponential backoff` · `AI safety` · `red teaming` · `jailbreaking`
