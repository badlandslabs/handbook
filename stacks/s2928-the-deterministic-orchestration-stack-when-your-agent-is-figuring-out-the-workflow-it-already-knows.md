# S-2928 · The Deterministic Orchestration Stack — When Your Agent Is Figuring Out the Workflow It Already Knows

You've committed to multi-agent. You've got a researcher, a writer, a reviewer. The question now is: who decides the next step? The instinct is to let the LLM figure it out — another model that routes, plans, decides. The problem is that routing at runtime consumes tokens, adds latency, and introduces non-determinism into the one layer you actually want to be predictable. The workflow topology is known at definition time. Treat it that way.

## Forces

- **LLM-based routing conflates two jobs.** The LLM should produce domain output, not orchestrate. Routing is a control problem, not a reasoning problem.
- **Dynamic orchestration compounds cost.** Every routing decision is an inference pass. At scale, this is the hidden budget burner.
- **Non-deterministic routing is untestable.** You can't unit-test "the LLM decided to go here." You can test a condition on an output field.
- **Workflow structure is usually known.** The sequence exists because the business process exists. The agent shouldn't have to rediscover it.
- **Hybrid cases are real.** Some steps genuinely need judgment. The question is where to draw the line — and the answer is narrower than most teams initially think.

## The Move

Separate orchestration topology from LLM reasoning. Declare routing at definition time; let the LLM focus on producing outputs.

### The core pattern: deterministic control plane

Define the workflow graph in a config file (YAML/JSON). Each node is an agent or tool. Edges are conditional routes evaluated against structured outputs — not against natural language reasoning. The routing engine is a state machine, not a model.

```
architect:
  model: claude-opus-4-7
  prompt: "Design the system at {{ input.spec_path }}"
  output:
    file_path: { type: string }
    score: { type: number }
  routes:
    - to: reviewer
    - to: $end  # terminal if no condition matches

reviewer:
  model: claude-sonnet-4-20250514
  prompt: "Review the design at {{ architect.output.file_path }}"
  output:
    approved: { type: boolean }
    notes: { type: string }
  routes:
    - to: architect
      when: "{{ not output.approved }}"
    - to: $end
      when: "{{ output.approved }}"
```

Routes are evaluated in order. First matching condition wins. No LLM tokens consumed for routing decisions.

### Where to draw the line

| Route to deterministic if... | Keep dynamic (LLM) if... |
|---|---|
| Output has a structured boolean or enum field | The "right" next step requires judgment |
| The business process has a fixed topology | The agent needs to explore an unknown problem space |
| You're looping through an evaluator-optimizer cycle | The task genuinely has multiple valid paths |
| You need replayable traces for debugging | The input is too varied to predeclare |

### The pattern stack: 4 layers

1. **Tool/Agent** — produces structured output with typed fields
2. **Output schema** — explicitly declares which fields drive routing decisions
3. **Routing layer** — evaluates Jinja2 expressions against output fields; deterministic
4. **Orchestrator** — reads routing result, dispatches next agent; no LLM in this step

### Tool choice: use typed schemas, not descriptions

Function-calling schemas with `{type: "string", "enum": ["approved", "rejected", "needs_revision"]}` are both the contract and the routing input. The routing engine reads the enum value. If the model produces free text, you need an LLM to classify it — which puts routing back in the inference pass.

### Observability is a free win

Since routing is deterministic code, every step in the workflow produces a trace entry with: which node ran, what input it received, what structured output it produced, which route was selected, and why. No inference needed to reconstruct the execution path.

## Evidence

- **Microsoft Open Source Blog:** Microsoft published Conductor (MIT), an open-source CLI that defines multi-agent workflows in YAML with deterministic Jinja2-based routing. Routing between agents consumes zero tokens. "The structure is fixed at definition time — and that's the point." — [https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows/](https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows/)

- **HN Ask thread (47660705):** Practitioners reporting production multi-agent setups cite "roll your own" for serious work specifically because existing frameworks make routing decisions inside the LLM call graph. Multiple respondents identify LLM-based orchestration as the source of observability and cost problems. — [https://hn.nuxt.dev/item/47660705](https://hn.nuxt.dev/item/47660705)

- **arXiv (2606.26924):** "A Deterministic Control Plane for LLM Coding Agents" — from 10,008 GitHub repositories studying agent configurations, the paper's core thesis: "The configuration-and-process layer that surrounds an LLM coding agent can be treated as a managed software supply chain, governed deterministically and independently of the underlying harness or model." LLM-based governance of an LLM agent is circular; deterministic code must govern non-deterministic code. — [https://arxiv.org/abs/2606.26924](https://arxiv.org/abs/2606.26924)

- **Camunda (Project Orchesr-AI-te):** Working with 50+ enterprise customers across banking, insurance, healthcare, and telecom, Camunda's pattern is explicitly "deterministic process logic governs known, repeatable paths, while dynamic AI agents handle unpredictable scenarios." The control plane is process-orchestrated; agents fill the gaps. — [https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work](https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work)

## Gotchas

- **Over-engineering the deterministic layer.** If your workflow genuinely has unknown topology (exploratory research, open-ended coding), forcing deterministic routing on it adds friction without benefit. Use dynamic routing where the problem actually requires it.
- **Schema drift.** If the LLM doesn't reliably produce the typed enum/string fields your routes depend on, routing silently falls through to `$end`. Validate schema adherence in your eval pipeline before relying on it for routing.
- **Mixing paradigms mid-workflow.** A hybrid where some branches are deterministic and others are dynamic is valid, but the transition points need to be explicit. Ambiguous transitions make traces harder to reason about.
- **Hardcoding the happy path.** Deterministic routing only helps if the declared conditions actually cover the failure modes. Teams that define routes only for the success case end up with silent fallthrough on errors.
