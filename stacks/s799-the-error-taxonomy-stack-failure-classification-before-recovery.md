# S-799 · The Error Taxonomy Stack: Classify Before You Recover

Your agent returns HTTP 200 with a hallucinated tool call. Another agent loops 12 times on a rate-limited endpoint, burning $180 in tokens. A third one exits cleanly — but its output is valid JSON with semantically wrong values that pass every schema check. You didn't handle these errors. You didn't even know they were errors. The error taxonomy stack is the practice of building an explicit classification layer into your agent before anything goes wrong — so the right recovery fires automatically, not after a human notices.

## Forces

- **Agents fail in ways HTTP status codes don't describe.** Hallucinations, semantic garbage, and confident loops all return 200. Your error handling reaches past the network into meaning — which requires knowing what "error" means in your domain.
- **Without classification, recovery is random.** Retrying a malformed prompt five times wastes tokens. Falling back to a cheaper model when you're hitting a token cap makes things worse. Recovery without diagnosis amplifies failures.
- **The prompt-band-aid trap.** When teams encounter failures, they add directives: "ALWAYS check the schema." "NEVER call Tool C without verifying." Each fix breeds the next exception, producing a 20,000-token system prompt that contradicts itself. The architectural fix comes before the prompt.
- **Most frameworks give you try/catch, not failure intelligence.** Retry with backoff, circuit breakers, and fallback models are all standard patterns — but they're applied generically. The insight from production is that different failure classes need different recovery, and you need to classify before you route.

## The Move

Build an explicit error taxonomy into your tool-call layer, then route each class to its matching recovery:

**Classify at the boundary, not after.** When a tool returns, run classification logic before checking whether it "succeeded":

```
TRANSIENT (retry) → rate limit (429), timeout, 503, DNS
SEMANTIC (re-prompt) → malformed JSON, wrong schema, hallucinated tool name
RESOURCE (reduce) → token cap, context overflow, spending limit hit
FATAL (abort) → 401/403 auth failure, revoked key, policy violation
```

**Never retry without a ceiling.** Cap retries by error class: transient gets 3 attempts with exponential backoff + jitter; semantic gets 1 with corrective context injected; resource and fatal get 0 — route to reduce or abort immediately.

**Check output quality, not just format.** Schema-valid JSON can still be semantically wrong. Add a lightweight validator that runs after parsing: does the tool's response satisfy the invariants the agent needs to proceed? If not, classify as semantic and re-prompt with the specific violation.

**Build for "agents will fail" not "prevent failure."** Design your orchestration around inevitable failure modes: checkpoint state before every tool call, make every action idempotent, wire human-in-the-loop for irreversible operations. The agents that run longest in production are the ones designed to survive crashes, not avoid them.

## Evidence

- **Blog post:** Microsoft AI Red Team published a formal taxonomy of failure modes grounded in real incidents, classifying failures by cause (internal vs. adversarial) and providing a hierarchical taxonomy with concrete examples — including autonomous policy violations and data exfiltration. The methodology was built from internal incident cataloguing, red team findings, and 2025 community submissions. — [Microsoft Security Blog](https://www.microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents/), April 2025
- **Engineering blog:** A practitioner documented the pattern of teams stacking prompt directives to fix failures, producing 20,000+ token "Frankenstein" prompts that contradict themselves. The proposed alternative: architectural patterns (classification gates, validation layers, policy enforcement) instead of prompt-level directives. Teams using structured error classification with architectural recovery see measurable gains in reliability. — [Magnetic Growth / Alex Furmansky](https://magneticgrowth.substack.com/p/stop-fixing-ai-agent-with-prompt), December 2025
- **Show HN:** OpenTiger — autonomous dev orchestration built on the explicit assumption that agents WILL fail. The system handles quota limits, test failures, policy violations, and bad judgment calls by designing recovery into the orchestration layer rather than relying on the agent to self-correct. The core insight: "what if the system was designed around the assumption that agents WILL fail?" — [Hacker News / Show HN](https://news.ycombinator.com/item?id=47108068), ~60 days ago
- **Engineering blog:** Formal 4-class taxonomy applied in production: transient (rate limits, timeouts → retry), semantic (malformed JSON, invalid tool calls → re-prompt with corrective context), resource (token budget, context overflow → reduce payload by summarizing/switching models), fatal (auth failures, policy violations → abort and alert). Teams combining layered defenses (retries → fallbacks → circuit breakers) with structured error classification report 24%+ improvement in task success rates. — [Geta.Team](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it), November 2025

## Gotchas

- **Classifying too late loses state.** If you don't checkpoint before the tool call, a crash on retry loses all accumulated state. Classify on the response, but checkpoint before you call.
- **Semantic errors are the hardest to detect.** They look like success. You need domain-specific validators — not just JSON schema, but invariants about what the output should contain relative to the task.
- **Circuit breakers help at the API level but not the agent level.** A circuit breaker on your LLM API call prevents cascading failures to downstream services, but it doesn't help when the agent itself loops 40 times on a correctable error. You need both layers.
