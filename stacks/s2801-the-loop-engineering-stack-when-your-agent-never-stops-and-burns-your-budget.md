# S-2801 · The Loop Engineering Stack — When Your Agent Never Stops and Burns Your Budget

_You set `max_iterations=50`. The agent hits 47 and produces confident nonsense. The cap stopped it from running forever — but it ran long enough to cost $12 and return an answer nobody would catch as wrong. The loop ended because of a number, not because the work was done._

## Forces

- **The inner loop is solved; the outer loop is the engineering problem.** Every agent framework (LangGraph, CrewAI, AutoGen) runs the same scaffolding: model generates → execute tool → feed back → repeat. That loop is hardcoded and identical across frameworks. What varies is what the model *does inside it* — and whether you have structured control over it.
- **Termination by the model is not termination by the system.** A model claiming "I'm done" is model output, not a deterministic signal. It can be wrong. It can be a lie. It can be the agent trying to satisfy a completion heuristic rather than complete actual work.
- **The two loop invariants that separate amateurs from production systems:** (1) termination is enforced by the harness on deterministic criteria — never by the model's own claim of completion; (2) the entity that verifies work is structurally separate from the entity that produces it.
- **The Reflexion insight changed everything.** ReAct's inner loop learns within one episode. Reflexion (2023) introduced the outer loop that learns *across episodes* — storing a critique in episodic memory and reloading it on the next run. Every stacked-loop design since traces back to this move.

## The Move

Loop engineering treats the agent's control loop as a designed artifact — not scaffolding you inherit from a framework, but infrastructure you own and instrument.

- **Hardcode termination at the harness level, not the model level.** The loop exit condition must be a deterministic function of observable state (step count, trace hash, output signal), not a model's self-reported "done" flag. Phil Schmid (Feb 2026): "The loop is hardcoded. What the model does *inside* the loop is not."
- **Count steps and enforce dual budgets.** Set a hard cost budget (tokens spent) and a step budget independently — stop when *either* is hit, not just when a count is reached. A task that finishes early still stops cleanly. A task that loops at step 10 with 47 identical tool calls still burns the same cost budget.
- **Implement the verify-before-claim pattern.** Before the agent can signal completion, a structurally separate verifier must confirm the work meets criteria. The verifier uses a different prompt, different tool access, or a different model. In LangGraph, this is the supervisor node pattern: the supervisor checks each node's output before routing to END.
- **Detect repetition via trace hashing, not step counting alone.** Step counts alone can't distinguish "50 useful steps" from "12 steps repeated 47 times." Hash recent tool-call sequences (tool name + key params) and detect when the same pattern repeats N times. Break on repetition, not just on a fixed cap.
- **Build a circuit breaker on error rate.** Track consecutive failures (tool errors, schema violations, model refusals) across the current trace. If error rate exceeds a threshold (e.g., 3 consecutive failures), halt the loop and escalate. Harsha Rastogi (Modelia.ai, 2026): documented a production agent whose image generation pipeline approved obviously flawed outputs after only 2 consecutive tool failures, optimizing for completion over correctness.
- **Separate inner and outer loop concerns explicitly.** The inner loop (ReAct pattern) handles a single task's tool-call cycle. The outer loop handles "is this task worth doing, did it produce the right thing, should we retry with different context?" Frameworks like LangGraph encode this in their graph structure — nodes for planning, execution, and verification are distinct with explicit edges. CrewAI encodes it in role-based processes where a "reviewer" agent runs after the "executor."

## Evidence

- **Research survey:** The AI System Design Guide's "Loop Engineering" page documents the evolution from ReAct (2022) through Reflexion (2023) and LLMCompiler (2023) to 2025-2026 stacked-loop engineering, explicitly naming the two invariants. The survey traces AutoGPT's 2023 failure ("proved fully autonomous loops at scale, and exposed infinite loops and runaway API bills") as the canonical example of why loop engineering is necessary. — [GitHub: ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/12-loop-engineering.md)
- **Framework evidence:** The arXiv practical guide (Bandara et al., 2025) provides the nine best practices including single-responsibility agents and externalized prompt management as structural aids to loop control. Solute Labs' framework comparison documents LangGraph's graph-node state model, CrewAI's process-flow roles, and AutoGen's conversation-first approach — each encoding outer-loop control differently. — [arXiv:2512.08769](https://arxiv.org/html/2512.08769v1), [Solute Labs](https://www.solutelabs.com/blog/langgraph-vs-crewai-vs-autogen)
- **Production failure post-mortem:** Harsha Rastogi (AI Product Engineer, Modelia.ai) documented two concrete production failures: an Asynq.ai evaluation agent hallucinating tool parameters and looping, and a Modelia.ai pipeline approving flawed images. Both failures traceable to missing loop-level error handling and absent verification separation. — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

## Gotchas

- **`max_iterations` is not a loop design, it's a bail-out.** It stops the agent from running forever but says nothing about whether the work was done correctly. The agent can hit the cap at step 47 having produced nothing useful.
- **Tool selection is not tool verification.** The agent calling the right tool is not the same as the tool producing the right output. Without a separate verification step, a confident wrong answer proceeds to completion unchecked.
- **The loop that succeeds once will fail silently when it succeeds for the wrong reason.** Endpoint scoring (grading the final answer) never catches that the agent reached the right answer through a reckless trajectory. Trajectory-level loop instrumentation is required.
- **Inner loop patterns (ReAct) don't scale to outer loop concerns.** Many teams implement a clean ReAct loop and then wonder why their agent drifts over multi-day deployments. The outer loop — planning, reflection, context management across sessions — requires different mechanisms (episodic memory, verification, state handoff) that aren't in the ReAct pattern.
