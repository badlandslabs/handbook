# S-1018 · The Component-Level Attribution Stack: When Your Agent Is Wrong but Says 200 OK

Your agent returns well-formed JSON, hits all SLA markers, and logs no errors. Three days in, a user reports it has been routing insurance claims to the wrong department, generating confident hallucinations, and losing the original query context — all silently, all under a green infrastructure dashboard.

This is the **failure attribution problem**: aggregate agent metrics tell you something failed. They don't tell you which of four independent components broke, or why the fix you applied to one actually masked a second failure.

## Forces

- **200 OK is not a correctness signal.** The HTTP response code and the LLM output are independent systems. A non-zero exit code means the tool ran; it says nothing about whether the output was what you intended.
- **Components fail independently.** Routing, retrieval, reasoning, and generation each have their own failure modes. Wrong output can originate in any of them — aggregate metrics hide which.
- **Loops look like work.** A recursive agent loop generates coherent, token-billed output indefinitely. No crashes. No alerts. The termination condition never fires because it was never correctly defined.
- **Failure cascades.** A retrieval miss produces empty context. The generator then fills the void with plausible-sounding output. By the time you see the wrong answer, the retrieval failure has long since scrolled off your logs.
- **Patch masking.** Teams fix the symptom (the wrong output) without fixing the cause (which component degraded). The same failure recurs in a different shape.

## The Move

**Break the agent into taxonomically distinct components and build failure classification as a first-class output of the system, not an afterthought.**

The architecture: four specialized components — Router, Retriever, Reasoner, Generator — each with independent failure modes and independent remediation paths.

### Failure classification taxonomy (6 primary modes)

1. **Routing failures** — wrong workflow or agent selected for the incoming intent. Example: a customer complaint about billing gets routed to the sales agent instead of support.
2. **Retrieval failures** — relevant context exists but was not retrieved. Empty results, wrong document rank, or stale index.
3. **Reasoning failures** — correct inputs, wrong strategy. The agent understood the context but chose the wrong approach.
4. **Generation failures** — poor output despite good inputs. Hallucination, tone drift, or format corruption at the output stage.
5. **Latency failures** — within SLA on time but the time pressure caused shortcut-taking.
6. **Degradation failures** — quality drops over time without a triggering event; model drift, index staleness, or upstream API behavior change.

### Implementation approach

- **Automated failure classification** runs on every agent trace, not just on human-flagged cases. Classify each failure to a component before a human reviews it.
- **Component-level metrics** are tracked independently: routing accuracy, retrieval recall@k, reasoning step-to-outcome ratio, generation faithfulness score. Each component has its own regression threshold.
- **Traces over aggregates.** When a failure occurs, the first question is always "which span caused this" — trace IDs tie every output back to the specific component invocation that produced it.
- **Structured logging with schema.** Log the component, the input, the output, the elapsed time, and a confidence signal on every pass. This makes post-hoc analysis reproducible.
- **Regression suite per component.** When you fix a retrieval failure, you need a retrieval-specific test harness — not a full end-to-end agent test.

### The 14-failure-mode taxonomy (from practitioner field research)

Beyond the 6 primary modes, granular practitioner research identifies 14 distinct failure modes across three categories: **specification failures** (the task was ambiguous or under-specified), **inter-component misalignments** (output format from one component doesn't match input expectations of the next), and **environmental failures** (tool timeout, API change, context window exhaustion).

The key insight: most agent failures in production are **inter-component misalignments**, not failures of the LLM itself. The model did its job; the contract between components broke.

## Evidence

- **HN post:** "How to fix AI Agents at the component level" — describes a production agent broken into Router, Retriever, Reasoner, and Generator with automated 6-category failure classification and per-component regression tests. HN thread id 46245184, 2025.
- **GitHub: agent-triage (converra):** An open-source tool for diagnosing AI agents in production by extracting policies from prompts, evaluating traces, and generating diagnostic reports. Supports automated failure attribution across agent components. — [https://github.com/converra/agent-triage](https://github.com/converra/agent-triage)
- **Field guide: "Debugging LLM Failures Systematically" (Tian Pan, 2026):** Documents a fintech case where a single comma in a system prompt caused an invoice generation agent to output gibberish — $8,500 in losses, no errors logged. Proposes structured boundary testing and 14-mode failure taxonomy. — [https://tianpan.co/blog/2026-04-15-debugging-llm-failures-field-guide](https://tianpan.co/blog/2026-04-15-debugging-llm-failures-field-guide)
- **Real World Data Science:** Practitioner account of deploying agentic AI in clinical settings, noting that failures were dominated by retrieval and reasoning errors, not generation — [https://realworlddatascience.net/applied-insights/case-studies/posts/2025/08/12/deploying-agentic-ai.html](https://realworlddatascience.net/applied-insights/case-studies/posts/2025/08/12/deploying-agentic-ai.html)

## Gotchas

- **Don't build one regression test for the whole agent.** A test that exercises the full pipeline will tell you something broke, not where. Component-level tests are required for targeted fixes.
- **Confidence scores lie.** LLMs report high confidence on hallucinated outputs. Your failure classifier cannot use the model's own confidence as a signal — use structural cues (empty retrieval results, schema mismatches, tool call failures) instead.
- **Degradation is invisible without baselines.** You cannot detect quality drift without a fixed reference set. Run evaluation on a held-out golden dataset continuously, not just at deploy time.
- **Fixing one component can break another.** A change to the retriever that improves recall may increase latency enough to trigger shortcut-taking in the reasoner. Treat component changes as system changes and re-run full trajectory evaluation.
- **The termination condition is a first-class component.** Many agent loops that run too long are not bugs — they are missing or incorrect stop conditions. Treat the termination logic as a component that requires its own tests and failure modes.
