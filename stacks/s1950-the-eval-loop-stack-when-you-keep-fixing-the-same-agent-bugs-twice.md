# S-1950 · The Eval Loop Stack — When You Keep Fixing the Same Agent Bugs Twice

Your agent failed in production for the third time this quarter. Each time, someone found the bug, rolled back, and fixed the prompt or tool schema. Each time, the fix worked — until a slightly different input triggered the same failure class again. You have no regression suite. You have no way to know whether the "fix" actually made things better or just moved the failure somewhere you haven't seen yet. You are evaluating your agent with vibes, and vibes are not a CI gate.

## Forces

- **The surface is infinite.** Agents fail on inputs you never imagined — malformed queries, tool timeout cascades, state corruption in long sessions. Your test cases cover 10% of what's possible.
- **The loop is broken.** Production failures generate traces, but traces don't become tests. Bugs you already fixed are somewhere in your backlog or someone's memory, not in a gate that prevents them from returning.
- **Benchmarks lie.** Standard benchmarks score your agent well but miss the failure modes that actually cost you — wrong tool selection under load, memory truncation mid-session, silent tool call failures that the agent hallucinates past.
- **Human review doesn't scale.** Spot-checking outputs catches obvious failures but misses subtle regressions: a tool being called with slightly wrong arguments, a recovery path that degrades gracefully into wrong answers.
- **Every change is a new regression surface.** A new prompt, a model swap, a tool schema update, a memory strategy change — any of these can alter behavior in ways you won't notice until production.

## The move

Build a **production-to-regression loop**: capture agent failures from production traces, distill them into test cases, and gate every deployment on the updated test suite. This closes the feedback loop so the same failure class cannot silently return.

**The core pipeline:**

- **Capture.** Instrument your agent to emit structured traces to a trace store (Langfuse, Arize Phoenix, or similar). Every tool call, every LLM decision point, every state change — logged, not just final output.
- **Triangulate.** Run LLM-as-judge on traces to flag regressions: compare current behavior against the golden dataset, surface轨迹-level anomalies (wrong tool selection, excessive tool calls, silent failures), and score task success. Run code-based deterministic checks for binary properties (did it call the right API? did it hit the correct endpoint?).
- **Distill.** Convert flagged production failures into test cases: input + expected trajectory + expected outcome. Tag them by failure class (tool selection, memory overflow, recovery failure, hallucinated completion).
- **Gate.** Run the golden dataset on every PR. Treat the test suite as a release gate — no deployment passes if any tagged regression test fails.
- **Iterate.** Add synthetic cases generated from failure clusters to cover the tail your production traffic hasn't hit yet.

**Scoring dimensions (three-layer approach):**

1. **System efficiency** — latency per task, tokens consumed, number of tool calls, cost per session
2. **Session-level outcome** — task success (did it complete?), trajectory quality (did it take a reasonable path?), user-visible correctness
3. **Node-level precision** — did it select the right tool? pass correct arguments? recover gracefully from tool failures?

**Two scorer types:** code-based scorers for deterministic checks (exact match, schema validation, return code), LLM-as-judge for nuanced qualities (response quality, tone, whether a recovery was appropriate).

## Evidence

- **HN discussion (Ask HN, ~4 months ago):** Practitioners described a "very heterogeneous and fast moving" eval landscape where "benchmarks suck because they are cheap knockoffs instead of comprehensive experiments." The hardest unsolved problem: measuring outputs that aren't binary right-or-wrong, especially for chatbots and coding agents where "that's a good response, but there is a better response." — [HN thread](https://news.ycombinator.com/item?id=47319587)

- **Arthur.ai (June 2026):** "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures." Their pattern: production failure → trace → test case → golden dataset → CI/CD release gate. Argues synthetic prompts only reflect what an engineer imagined, while production surfaces the actual long tail of ambiguous phrasings, malformed inputs, and tool sequences never anticipated. — [Arthur.ai](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

- **Amazon Bedrock engineering post (2025):** Documented a multi-dimensional eval framework for agentic systems addressing: multi-step autonomy evaluation, tool orchestration accuracy, retrieval quality, and recovery behavior. Stressed that traditional LLM eval treats agents as black boxes, scoring only final outcomes without revealing why agents fail. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Braintrust documentation (2026):** Core eval pattern: `data + task + scorers`. Emphasizes evaluating agents on both end-to-end outcomes AND individual steps. Notion's reported 10x velocity improvement came from building an eval loop before scaling agent deployments. — [Braintrust](https://www.braintrust.dev/articles/how-to-eval)

- **Maxim AI (November 2025):** Three-layer eval framework for agentic systems: System Efficiency, Session-Level Outcomes, and Node-Level Precision — combined with LLM-as-judge and human review. Emphasizes moving evaluation from offline simulation to online production monitoring with alerts and continuous dataset curation. — [Maxim AI](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices)

## Gotchas

- **LLM-as-judge has its own biases.** A single judge model may prefer certain writing styles or content, producing skewed evaluations. Multi-agent evaluation frameworks (multiple LLMs debating or collaborating on a verdict) are emerging to address this.
- **A passing eval doesn't mean the agent is good.** You can have high eval scores on a narrow test set and still fail on the input distribution your users actually send. Coverage of failure classes matters more than pass rate.
- **The golden dataset rots.** If you only add test cases from production failures and never add synthetic edge cases, you're always one step behind the failure. Build both.
- **Trajectory evaluation is expensive.** Evaluating every step an agent takes costs significantly more tokens than checking only the final output. Budget for it or focus trajectory checks on high-stakes tool calls.
- **Silent failures are the hardest to catch.** An agent can complete a task "successfully" — no errors, no exceptions — while doing the wrong thing (calling the wrong API, using stale memory, reporting a fabricated result). This is where trace-level inspection earns its cost.
