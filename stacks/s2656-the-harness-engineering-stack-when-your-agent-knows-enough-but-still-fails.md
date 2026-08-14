# S-2656 · The Harness Engineering Stack — When Your Agent Knows Enough but Still Fails

You gave your agent a frontier model. You wrote detailed system prompts. You loaded it with RAG and tool access. It still loops on the same failure, can't verify its own output, and quietly returns wrong answers with full confidence. The model isn't the problem. Everything around the model is. This is the harness engineering problem: making the execution environment reliable, not just the model.

## Forces

- **Two teams, same model, different outcomes.** Agent capability = model quality × harness quality. In 2026 the harness term has the steeper gradient. The model is fixed at deploy time; the harness is where engineering happens.
- **Compounding failure kills multi-step agents.** 95% accuracy per step → ~60% by step 10 in a 10-step workflow. The agentic capability that makes multi-step reasoning useful is the same property that makes it fragile.
- **Feedforward vs. feedback are different engineering disciplines.** Guiding the agent before it acts (AGENTS.md, guardrails, tool design) requires different thinking than observing what it did and triggering correction (traces, evaluators, recovery loops).
- **Observability ≠ evaluation.** 89% of agentic teams have traces; only 52% run correctness checks. Watching your agent run without knowing if it succeeded is a category of failure, not a safety signal.

## The Move

The core shift: stop engineering the model, start engineering the world the model operates in.

**1. Internalize Agent = Model + Harness.**
The model provides raw intelligence. The harness provides everything else: tools, guardrails, feedback loops, memory, orchestration, and observability. When the agent fails, the fix lives in the harness, not the prompt.

**2. Build a feedforward + feedback loop.**
Feedforward controls guide behavior before acting: AGENTS.md docs, structured tool definitions, guardrails that block dangerous actions, and pre-flight checks. Feedback controls observe outcomes after acting: traces, success/failure status codes propagated through tool responses, and post-execution assertions that confirm expected state changes occurred. The loop closes when feedback feeds back into feedforward — failures become harness improvements.

**3. Engineer the harness on every failure, permanently.**
When the agent makes a mistake, invest the time to make that class of mistake structurally impossible going forward. Most of the time that means a harness improvement: a linter that blocks the bad pattern, a guardrail that catches the edge case, a tool that provides the information the agent was missing. Don't just retry.

**4. Use three reflection loops for scientific rigor.**
Bayer's PRINCE platform (built with Thoughtworks) uses three nested loops:
- **Process reflection** — did the agent follow a sound trajectory? (workflow correctness)
- **Data reflection** — did the agent retrieve the right information? (retrieval quality)
- **Output reflection** — does the final answer match the source material? (answer correctness)

**5. Keep quality left — catch failures as early as possible.**
Checks at the harness boundary (pre-execution guardrails, tool schema validation) are cheaper than checks at the output stage. Build evaluation into the tool layer itself, not just post-hoc.

**6. Measure harness quality, not just model quality.**
Track step-level success rates, loop counts per task, recovery rates after failures, and false-positive rates on guardrails. The harness is where you catch regression; instrument it specifically.

## Evidence

- **Martin Fowler case study (June 2026):** Bayer AG + Thoughtworks built PRINCE — a cloud-hosted agentic RAG platform for pharmaceutical safety reports. Every sentence in responses links to the exact page and verbatim quote from source documents. The system evolved from keyword search to intelligent research assistant through systematic harness improvements around context routing, recovery, and observability. — [martinfowler.com/articles/reliable-llm-bayer.html](https://martinfowler.com/articles/reliable-llm-bayer.html)

- **Mitchell Hashimoto (February 2026):** HashiCorp co-founder and Terraform creator published his personal AI adoption journey, including the pivotal "Step 5: Engineer the Harness" — a practice of permanently fixing every agent mistake by improving the environment rather than prompting around it. Within weeks, OpenAI and Anthropic both published harness engineering frameworks. — [mitchellh.com/writing/my-ai-adoption-journey](https://mitchellh.com/writing/my-ai-adoption-journey)

- **Birgitta Böckeler / Martin Fowler (April 2026):** "Harness Engineering for Coding Agent Users" formalizes the discipline for software engineering contexts: the distinction between builder harness (built into the agent) and user harness (outer controls for specific use cases), with explicit feedforward/feedback categories and a trust-building framework for teams skeptical of AI-generated code. — [martinfowler.com/articles/harness-engineering.html](https://martinfowler.com/articles/harness-engineering.html)

- **LangChain State of Agent Engineering survey (2025):** 1,340 teams surveyed. 89% have some observability for agents. Only 52% run correctness evaluations. The 37% watching dashboards without outcome validation are flying blind. — cited in [paperclipped.de](https://www.paperclipped.de/en/blog/ai-agent-production-issues)

## Gotchas

- **Prompt engineering is not harness engineering.** Editing a system prompt when the agent misbehaves is a local fix that doesn't prevent recurrence. The failure is usually in the tool definition, the guardrail logic, or the feedback loop — not in what you told the model.
- **Observability without evaluation is a false sense of safety.** LangSmith traces, LangGraph state inspection, and OpenTelemetry spans tell you what happened. They don't tell you if it was right. You need ground-truth evaluation sets paired with harness instrumentation.
- **The harness compounds too.** A poorly designed guardrail that fires on 30% of legitimate requests creates a new failure mode: the agent learns to circumvent it or the user loses trust entirely. Harness components need their own evaluation.
- **Human-in-the-loop is a harness element, not a substitute for it.** Approval gates catch failures but don't prevent them. The goal is a harness that makes human review unnecessary for routine cases, with HITL as a safety layer on the tail, not a first-line defense on every call.
