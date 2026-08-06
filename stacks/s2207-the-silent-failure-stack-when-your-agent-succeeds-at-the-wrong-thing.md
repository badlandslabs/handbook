# S-2207 · The Silent Failure Stack — When Your Agent Succeeds at the Wrong Thing

A classical software bug crashes or throws an error. You know something went wrong. An AI agent with silent failure answers your question confidently, completes its task convincingly, and exits cleanly — with no indication that the answer is wrong, the action was destructive, or the goal was inverted. The system behaved exactly as designed. The outcome is simply wrong.

This is the most dangerous failure mode in production agents, and almost none of the standard engineering defenses catch it.

## Forces

- **Confidence and correctness are decoupled.** LLMs produce confident outputs regardless of accuracy. A hallucinated answer looks identical to a correct one from inside the agent loop. There is no exception thrown, no HTTP 500, no crash — only a plausible wrong answer.
- **Task completion and task success diverge.** An agent can call the right tools, follow the right sequence, and produce a coherent result that happens to be based on a tool's hallucinated output or a misinterpreted parameter. The trajectory looks perfect. The outcome is wrong.
- **Agents have tools and permissions.** The difference between a language model and an agent is that the agent has tools — and every tool is a new way to be wrong at scale. An agent that silently sends a wrong email, files a wrong record, approves a wrong refund, or moves money to the wrong account is orders of magnitude more dangerous than one that crashes.
- **Tests that pass on the happy path don't catch inversion.** If your eval suite only checks that the agent produces *something* on correct inputs, it tells you nothing about behavior on incorrect, adversarial, or out-of-distribution inputs. Silent failures live exactly in those gaps.

## The Move

Design your agent as if silent failure is the primary threat — because it is.

- **Output contracts before tools.** Define what correct output looks like before you define what tools the agent can call. A structured output schema with field-level constraints lets you validate the agent's response at each step, not just at the end.
- **Cross-validate critical tool outputs.** When a tool returns a result the agent will act on, route that result through a lightweight verifier — a second model call or a rule-based check — before the agent chains it into the next action. This catches tool hallucination (RAG returning false info) before it propagates.
- **Build behavioral evals, not functional ones.** Functional evals check that the agent does the thing. Behavioral evals check that the agent does the right thing under stress: malformed inputs, empty tool responses, permission errors, rate limits. Silent failures cluster at the edges.
- **Separate the signal from the output.** Treat confidence calibration as a first-class concern. Log not just what the agent returned but what the agent *believed* was true at each step — its interpretation of tool outputs, its reasoning about state. This creates the trace needed to diagnose silent failures in post-mortems.
- **Human-in-the-loop on irreversible actions.** For any tool call that modifies external state — email, database write, payment, approval — require an explicit human confirmation step. Silent failure on a reversible action is a bug. Silent failure on an irreversible action is an incident.
- **Golden set + adversarial testing.** Maintain a small, curated set of known-failure cases: inputs where the model is known to invert the goal, misinterpret context, or hallucinate a specific fact. Run these on every change. If the eval score drops, you introduced a regression in failure behavior — even if the happy-path score improved.

## Evidence

- **Research paper:** Vectara's "Awesome Agent Failures" repo (https://github.com/vectara/awesome-agent-failures) documents seven core failure classes including tool hallucination and response hallucination — both silent by nature. Tool hallucination: a RAG tool returns a plausible but fabricated passage. Response hallucination: the agent synthesizes a confident answer factually inconsistent with the tool outputs it received. Neither produces an error signal.
- **Engineering blog:** Gravity's "AI Agent Failures: Lessons From 2026" (https://gravity.fast/blog/ai-agent-failures-lessons-from-2026/) explicitly identifies silent failure as the most dangerous class: "An agent confidently wrong with no error returned." Cites Gartner's June 2025 forecast that over 40% of agentic AI projects will be canceled by end of 2027 — driven by cost overruns and risk incidents, not capability gaps.
- **HN discussion:** A 4-agent LangChain A2A system for market data research entered a loop where two agents produced plausible but incorrect outputs that fed each other's next steps, running up an estimated $47,000 bill before detection. The agents never errored. They produced coherent intermediate results at every step. (Source: agent-failure-handling-research.md, cross-referenced with Gravity's taxonomy of loop-based failures.)

## Gotchas

- **Silent failure hides in the happy path.** Teams naturally test the cases that should work. Silent failures occur precisely in the cases you didn't think to test — the empty RAG response that gets filled with a hallucination, the malformed API response the agent reinterprets confidently, the permission error the agent retries around without reporting.
- **Adding more tools increases silent failure surface.** Every new tool is a new source of incorrect output the agent can chain into downstream actions. MCP's rapid adoption (97M+ monthly SDK downloads, 10,000+ published servers by December 2025) means production agents are connected to more tools than ever — and each connection is a potential silent failure vector.
- **Retry logic amplifies silent failure.** If an agent retries a tool call that returned a plausible but wrong result, and the retry returns the same wrong result, the agent may double down on the incorrect answer with higher confidence. The $47,000 loop case illustrates this: the retry mechanism didn't recover from the error — it amplified it.
