# [S-2675] · The Workflow-First Stack — When You're So Ready for Agents You Forgot About Workflows

[You read "2025 is the year of agents" and immediately reached for LangGraph. After two weeks of building, you had a system that kind of worked in demos and fell over in production. Meanwhile, the team next door built the same thing in a weekend with a for-loop and a well-crafted prompt — and it never went down. The question isn't whether to use agents. It's whether you've exhausted every workflow pattern first. — This is the Anthropic principle, now cross-confirmed by production practitioners across HN and enterprise surveys.]

## Forces

- **The framework pull** — LangChain, LangGraph, CrewAI, AutoGen all come pre-wired for "agents," making it easier to build an agent than to question whether you need one
- **The hype cycle** — Agents are the headline; workflows are the unsexy reality that ships reliably, so teams skip straight to the exciting part
- **The definition problem** — Most systems called "agents" in production are actually workflows; Anthropic defines an agent as an LLM that dynamically directs its own processes, which most systems don't actually do
- **The complexity tax** — Full agent autonomy costs reliability, latency, and debuggability; every framework layer you add is another failure surface
- **The survivorship bias** — Successful workflow-first systems don't get blog posts; the failures from over-engineered agents do

## The move

The move is to **build the workflow first and graduate to an agent only when the workflow demonstrably fails**. This is not a guideline — it's what Anthropic's engineering team observed across "dozens of teams" building production systems, and it's been confirmed independently by enterprise surveys and HN practitioner threads.

Start at the bottom of the complexity ladder and climb only when forced:

- **Single LLM call** — one prompt, one response, done. Covers the majority of use cases.
- **Prompt chaining** — sequential LLM calls where each output feeds the next. For multi-step reasoning that doesn't need branching.
- **Routing** — a classifier or a single LLM call decides which specialized prompt or tool to invoke next. For handling heterogeneous input types.
- **Parallel tool calls** — one LLM call dispatches multiple tools simultaneously and synthesizes results. For data-gathering tasks with independent sources.
- **Agent loop** — LLM dynamically directs its own tool usage and iteration until a completion criterion is met. Only here do you have a true agent.

The progression is not just technical — it's a reliability contract. Each step up in autonomy is a step up in failure modes. The recommendation from multiple sources: **use full agent autonomy only when the task genuinely requires dynamic, multi-step problem-solving that can't be anticipated at build time**.

On the framework question, the pattern is consistent: **direct API calls beat frameworks for simple cases**. One HN practitioner (`segmondy`) put it plainly: "There's absolute 0 framework out there that's good enough for serious work." More measured practitioners layer custom orchestration on top of frameworks like LangGraph when they need state machines, checkpointing, and observability. The Turgon AI decision matrix makes this concrete:

| Use case | Go with |
|---|---|
| Fast prototyping or demos | LangChain |
| Production agents with control flow, retries, observability | LangGraph |
| Extreme performance, compliance, or flexibility needs | Custom |
| Simple 1-2 shot prompts or RAG | **None — stay simple** |

## Evidence

- **Anthropic engineering blog:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Their recommended progression: augmented LLM → compositional workflows → agents, only increasing complexity when the simpler pattern demonstrably fails. — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents), December 2024 (canonical; still referenced in June 2025 HN discussion with 543 points and 88 comments)
- **Hacker News practitioner thread:** Multi-agent orchestration thread reveals teams reaching for custom solutions or LangGraph + custom orchestrator. Key quote from `segmondy`: "There's absolute 0 framework out there that's good enough for serious work." Multiple practitioners confirm rolling their own for production reliability. — [Ask HN: How are you orchestrating multi-agent AI workflows in production?](https://news.ycombinator.com/item?id=47660705)
- **Enterprise survey (1,837 respondents):** Only 5% of surveyed engineering leaders have AI agents live in production. 70% of regulated enterprises rebuild their AI agent stack every 3 months or faster. These churn rates suggest over-engineered stacks that didn't start simple enough to stabilize. — [Cleanlab: AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **Frameworks optimize for the agent case** — even when your use case is a workflow. LangGraph's StateGraph is powerful but gives you a sledgehammer when you're solving a nail problem. The learning curve and abstraction cost may exceed your actual needs.
- **"Agent" is an overloaded term** — if you build with LangGraph, you're building a state machine with tool calls. That may be exactly what you need, but it doesn't make it an agent in the Anthropic sense, and treating it as one leads to over-engineering the control flow.
- **The graduation problem** — it's easy to start with a direct API call but hard to know when to migrate to a framework. The signal is: you need checkpointing, human-in-the-loop pauses, or structured state transitions that survive crashes. If you don't need those, don't add the complexity.
- **Stack churn is the cost of getting this wrong** — the Cleanlab finding that 70% of enterprises rebuild every 3 months is partly a consequence of starting too complex and never stabilizing.
