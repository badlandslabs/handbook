# S-993 · The Framework Selection Stack — When Every Agent Library Claims to Be the Right Choice and None of Them Are

Your team needs to ship a production agent system. You open the GitHub trending page: LangChain promises everything, CrewAI looks approachable, Agno is fast and minimal, and somewhere a 47-star GitHub repo claims it's all unnecessary. You spend two weeks evaluating and still don't know which one will cost you eight hours of debugging in November. The real differences between frameworks aren't in their feature matrices — they're in the failure modes they'll hand you when something breaks at 2 AM.

## Forces

- **Dependency weight kills performance at scale.** Agno ships <10 dependencies; CrewAI installs Kubernetes and half of PyPI. At 10,000 requests/minute instantiating agents per request, dependency overhead compounds into real infrastructure cost.
- **Inheritance depth hides bugs.** LangChain's Agent base class has 5-7 layers of inheritance. When something breaks, you don't know which layer is wrong. One HN user in the Agno discussion put it: "Every abstraction in LangChain is a wall you can't see through."
- **Production evaluation criteria don't match marketing criteria.** Frameworks are marketed on ease of getting started, not on state management, retries, type safety, or what happens when your agent hits a rate limit mid-pipeline.
- **Reliability and ergonomics trade off.** The easiest framework to prototype with is rarely the most reliable in production. Teams that choose for DX often find themselves retrofitting reliability after the first outage.

## The Move

Use a four-axis evaluation framework drawn from teams shipping agents to real users — not benchmarks. Rank candidates on these dimensions before you write a single line of agent code.

**Axis 1 — Reliability (non-negotiable for production)**

- Does it have explicit state management, or does state live in Python globals?
- Are retries configurable per tool, per step, and per model call?
- Does it handle partial failures (step 3 of 8 fails, steps 1-2 already ran)?
- Is there type safety at tool boundaries, or does everything become `dict[str, Any]`?

**Axis 2 — Ergonomics (counts for velocity, not correctness)**

- Can you trace a single agent decision from the API call to the tool result?
- Does the framework make it easy to write unit tests for agent behavior?
- Is there built-in observability, or do you instrument it yourself?
- How many layers between your code and the LLM call?

**Axis 3 — Failure recovery primitives**

- Does it have circuit breaker support for downstream API failures?
- Can it checkpoint mid-run and resume, or does a crash restart everything?
- Does it distinguish between transient failures (retry) and fatal ones (abort)?
- Is there a fallback model path when the primary model errors?

**Axis 4 — Deployment characteristics**

- What are the cold-start latency characteristics at your target scale?
- Can you isolate agents from each other (separate data/resource access)?
- Does the framework own your orchestration logic, or do you?
- What's the operational surface area when something goes wrong at 3 AM?

From Axioma AI's field experience across 40+ client deployments (2025): "We've noticed that most teams pick a framework for ease of use in the first week, and then spend the next six months working around the reliability gaps. The teams that pick for reliability first end up with better ergonomics anyway — because you can always add convenience layers, but you can't easily add circuit breakers you didn't design for."

## Evidence

- **Hacker News (Agno Show HN):** Agno team responded to criticism that the framework is "thin" by citing production scale — at 10,000 requests/minute instantiating agents per request, LangChain's 5-7 inheritance layers and CrewAI's Kubernetes dependency create measurable latency overhead. Agno's Agent base class is 1 file with <10 required dependencies. — https://news.ycombinator.com/item?id=44155074
- **Axioma AI Field Guide (2025):** Axioma AI evaluated frameworks across 40+ production deployments using reliability, ergonomics, deployment, and ecosystem fit. Their conclusion: "The teams that pick for reliability first end up with better ergonomics anyway." They maintain a battle-tested framework comparison at github.com/axioma-ai-labs/awesome-ai-agent-frameworks. — https://blog.axioma-ai.com/top-tier-ai-agent-frameworks-f84d40cfd4c7
- **AI Agents Blog (2026):** Identified five production reliability patterns — exponential backoff, circuit breakers, checkpoint-and-resume, fallback strategies, escalation queues — and noted these are framework-dependent for availability. Built-in support varies significantly: most lightweight frameworks provide none; most enterprise frameworks provide some; none provide all five out of the box. — https://aiagentsblog.com/blog/agent-error-recovery-patterns/

## Gotchas

- **"Easy to start" ≠ "easy to debug."** A framework that gets you from zero to demo in an hour will hide bugs in abstraction layers. Test the debugging experience, not the demo experience.
- **Production performance ≠ dev performance.** Evaluate at your actual request volume, not a single request. The difference between instantiating one agent per request and one per 1,000 requests can be 10x in cost.
- **Framework defaults are not production defaults.** Most frameworks ship with retries disabled or with a single global retry policy. You need per-tool, per-model, per-step configuration.
- **The ecosystem lock-in tax.** Some frameworks make it expensive to switch. Check whether your tools, memory layer, and orchestration logic are framework-native or portable before committing.
