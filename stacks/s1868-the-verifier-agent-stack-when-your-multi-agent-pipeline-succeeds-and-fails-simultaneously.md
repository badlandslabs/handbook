# S-1868 · The Verifier Agent Stack — When Your Multi-Agent Pipeline Succeeds and Fails Simultaneously

Your multi-agent pipeline runs cleanly. No exceptions, no timeouts, logs show each agent completed its task. The output looks polished. Three weeks later, a domain expert flags that the analysis had a subtle methodological error from step 2 — propagated and amplified through every downstream agent. The pipeline was never broken. It was confidently wrong.

## Forces

- **Agents trust upstream output by default.** A code-review agent doesn't question whether the PR it received is the right PR. A synthesis agent doesn't verify whether its inputs were complete. Silent corruption flows downstream faster than errors.
- **Completion is not correctness.** Every agent framework measures task completion — whether the agent called its tools and returned a result. None measure whether that result was accurate, relevant, or methodologically sound.
- **The loop problem is structural.** A verifier that can only flag errors but not trigger rework creates an alert without a recovery path. Teams add verification but then ignore the results because there's no mechanism to loop back.
- **Verification is expensive.** Running a second LLM call to check the first feels wasteful until you compare it to the cost of shipping wrong output, rebuilding trust, or the $47K runaway that nobody caught until the billing statement.

## The Move

Build a **Planner → Executor → Verifier** pipeline as the foundational multi-agent primitive. The verifier isn't a review step — it's a gate that determines whether execution continues, loops, or aborts.

### Core mechanism

- **The executor produces output.** It calls tools, generates content, makes decisions. Output goes to the verifier, not directly to the user or next agent.
- **The verifier checks against explicit criteria.** These are not vibes — they are structured checks: "Does the API response contain a valid JSON schema?" "Are all referenced document IDs present in the source list?" "Does the generated code pass the provided test cases?" The criteria are defined at pipeline creation time, not inferred by the verifier.
- **The verifier routes to three destinations:** `PASS` (continue), `RETRY` with specific feedback (loop back to executor with notes), or `FAIL` (halt and surface to human). This is a deterministic state machine, not an LLM deciding what to do next.
- **Retry loops have hard limits.** Maximum 3 retries per step before `FAIL`. Without a cap, a failed verification can loop indefinitely — the exact failure that cost one team $47,000 when an analyzer-verifier pair ran 1.8M API calls over 11 days.
- **Verification criteria are pipeline-specific.** A code-generation pipeline checks test coverage and static analysis. A data-extraction pipeline checks row counts and schema compliance. A research pipeline checks source citation coverage. One-size-fits-all verification (e.g., "does this look good?") produces false confidence.
- **The verifier runs at every handoff boundary.** Not just at the end. If Agent A hands to Agent B, Agent B verifies Agent A's output before using it. This prevents corruption propagation.

### Architectural placement

The verifier lives inside the orchestration layer, not inside individual agents. LangGraph's conditional edges support this natively (`if verification_result == "PASS": continue()`). CrewAI's `Flow` API provides hooks for verification steps between agents. Even direct API usage can implement this with a 10-line check function.

## Evidence

- **Case study — Multi-Agent LLM System (bhavani-gbs):** Open-source production pipeline with a Planner → Executor → Verifier architecture using Google Gemini. The verifier agent operates as a separate node with shared memory, automatic retry logic, and evaluation metrics. — [GitHub](https://github.com/bhavani-gbs/Multi-Agent-LLM-System)
- **Engineering post — Microsoft ISE (Lily Jia, June 2026):** Retail customer migrated from a modular-monolith router to a microservices coordinator pattern. The key architectural insight: moving from "one agent handles everything" to "each agent owns a step, coordinator owns the handoff" — which is structurally a Planner→Executor pattern with explicit state transfer at every boundary. — [Microsoft ISE Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Production failure — $47,000 runaway loop (November 2025):** A four-agent LangChain market research pipeline entered an Analyzer → Verifier infinite loop. The analyzer generated content, the verifier found issues, the analyzer revised, the verifier found more issues — without a hard retry cap, this ran 11 days and 1.8M API calls before the billing statement revealed it. The system had logging and dashboards. It did not have a deterministic circuit breaker. — [Kognita](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch) / [Apick](https://apick.net/articles/ai-agent-cost-loops/)
- **Framework guidance — CrewAI Production Architecture:** Official docs recommend wrapping agents in a `Flow` with explicit verification gates between steps. The "Flow-First" philosophy explicitly prioritizes control flow over agent capability: "define precise execution paths including loops, conditionals, and branching logic for edge cases and predictable behavior." — [CrewAI Docs](https://docs.crewai.com/v1.15.9/en/concepts/production-architecture)
- **Community resource — Vectara awesome-agent-failures:** Documents "Response Hallucination" as a distinct failure mode: "Agent combines tool outputs into factually inconsistent response." This is the failure mode a verifier prevents — not by being smarter, but by checking the structural consistency of the output against the inputs. — [GitHub](https://github.com/vectara/awesome-agent-failures)

## Gotchas

- **Verification criteria drift.** As the pipeline evolves, verification logic is often the last thing updated. Add verification updates to the pipeline's definition of done, not as an afterthought.
- **A verifier can itself fail.** If the verification call times out or returns an error, the pipeline must handle it — default to `FAIL` (safe stop) rather than `PASS` (continuing on unknown state).
- **Verification cost compounds.** Each verification call is an extra LLM invocation. For high-volume pipelines, use a smaller/faster model for verification than for execution. The criteria are deterministic — you don't need GPT-4o to check "does this JSON have an `id` field."
- **Silent passes erode trust.** If the verifier always returns `PASS`, it provides no value. Monitor the `PASS`/`RETRY`/`FAIL` ratio per step. A step with a 99% pass rate and 1% retry rate is healthy. A step with 100% pass rate after launch is almost certainly not running verification.
