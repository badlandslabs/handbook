# S-2195 · The Framework Gravity Stack — When Your Scaffolding Weighs More Than Your Agent

You have a task that needs an agent: route emails, analyze data, interact with a browser. You install LangGraph. Then CrewAI. Then you need async so you add a Celery layer. Two weeks later your agent does one useful thing and the framework takes four engineers to maintain. This is framework gravity: the tendency of agent scaffolding to grow until it outweighs the agent itself.

## Forces

- **The framework-to-agent ratio problem.** The core agent loop — call model, read tool, run tool, feed result back — is roughly 50 lines of Python. The frameworks shipping this in 2026 add hundreds of abstractions, hidden state, and opinionated defaults that interact in non-obvious ways
- **The ecosystem lock-in problem.** Each framework bundles its own abstractions for memory, tool definition, and state. Migrating off one is as hard as migrating off any other. Choosing wrong means paying twice
- **The right-answer-depends problem.** LangGraph is right for one team and wrong for another. CrewAI accelerates teams that think in roles. The OpenAI Agents SDK is right if you're in their ecosystem. No framework is universally correct — but most teams treat it as a settled question
- **The production readiness gap.** Frameworks excel at demos and prototypes. Production concerns — observability, graceful shutdown, partial failure recovery, cost tracking — are often afterthoughts in framework design

## The move

**Start with 50 lines. Add a framework only when you hit a specific, documented pain point.**

The agent loop you actually need is this:

```
1. Send prompt + tools to model
2. Read stop reason
3. If tool call: execute it, feed result back, repeat from step 1
4. If end: return result
5. Bound by max iterations or token budget
```

Every framework is an answer to one or more of the following: *how do I define tools cleanly? how do I manage state across steps? how do I coordinate multiple agents? how do I add human oversight? how do I trace what happened?*

Before choosing a framework, identify which of those you actually struggle with. Then pick the framework that solves that specific problem, not all of them.

**The six frameworks that matter in mid-2026, by what they optimize for:**

| Framework | Strength | Best for | Lock-in risk |
|-----------|----------|----------|-------------|
| **LangGraph** | Explicit state machine graphs | Complex multi-step workflows needing full control over state transitions | Medium — own graph semantics |
| **CrewAI** | Role-based agent teams | Fast prototyping of "team of agents" with defined roles | Medium — role/task abstractions |
| **OpenAI Agents SDK** | Built-in sandbox + async | Agents that write and execute code, OpenAI ecosystem | High — native to OpenAI |
| **Claude Agent SDK** | Coding agent patterns | File/shell/code tasks, Anthropic ecosystem | Medium — own tool conventions |
| **Google ADK** | Gemini + enterprise tooling | Google Cloud shops, Gemini-first deployments | High — GCP/Gemini native |
| **AutoGen/AG2** | Research conversation patterns | Experimental multi-agent research, Microsoft ecosystem | Low — most open/polymorphic |

**The decision heuristic:**
- Building a single agent that calls tools → build from scratch or use the model provider's own SDK
- Building a team of role-based agents → CrewAI
- Building a complex workflow with branching and state → LangGraph
- Need sandboxed code execution → OpenAI Agents SDK
- Already deep in GCP or Anthropic ecosystem → respective SDK
- Genuinely novel multi-agent research → AutoGen/AG2

**The "no framework" signal.** If your agent is: linear steps, fewer than 5 tools, single model, no multi-agent, no need for tracing at scale — write the loop by hand. The HN discussion on "principles for production AI agents" (July 2025, 128 points) surfaced a consistent theme: the teams with the most reliable production agents often had the leanest scaffolding. Evaluations and prompt engineering beat framework complexity.

## Evidence

- **HN discussion:** "Six Principles for Production AI Agents" (app.build) reached the front page with 128 points, with commenters consistently citing that evaluations, not frameworks, were the primary driver of production reliability. Multiple engineers reported shipping lean custom loops that outperformed heavy framework setups. — [HN thread](https://news.ycombinator.com/item?id=44712315)
- **Framework comparison:** aiarch.dev (June 2026, last updated July 2026) provides a vendor-neutral comparison of all six major frameworks, noting LangGraph reached 38M monthly PyPI downloads and crossed 14K GitHub stars, while explicitly recommending "no framework" as the right answer for many use cases. — [aiarch.dev](https://aiarch.dev/agent-frameworks)
- **SDK metrics:** A production comparison article (Requesty.ai, 2026) documents GitHub stars across frameworks: CrewAI 52K+, OpenAI Agents SDK 27K+, LangGraph 14K+, Claude Agent SDK 7.3K+. These numbers reflect community adoption, not quality — CrewAI's star count reflects fast prototyping appeal, not production dominance. — [Requesty.ai](https://www.requesty.ai/blog/best-ai-agent-sdks-compared-2026-langchain-crewai-openai-anthropic-google)

## Gotchas

- **The framework gravity trap.** Teams that start with a framework tend to add more framework rather than remove it. Each new capability requirement gets solved with another abstraction layer. Monitor the ratio of framework code to agent logic; if it exceeds 3:1, refactor or replace
- **Tracing and observability are afterthoughts in most frameworks.** LangSmith, Braintrust, and Phoenix are better observability investments than framework choice — they work regardless of which SDK you pick
- **Version churn is brutal.** The agent framework space is still consolidating. LangGraph hit stable 1.0 in 2025; OpenAI Agents SDK launched in 2025. Choosing a framework that was "obviously right" 12 months ago means you're now on version 3 of its API. Pin versions and treat upgrades as first-class engineering work
- **Multi-agent is the most overengineered feature.** The majority of agent tasks that teams implement as multi-agent are better served by a well-prompted single agent with good tools. CrewAI's role-based model is compelling for demos; it often adds unnecessary coordination overhead in production
