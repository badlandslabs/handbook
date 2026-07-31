# S-1916 · The Evals-Last Stack — When You Ship Agents but Can't Prove They'll Work Tomorrow

Your agent handles 400 customer interactions a day. You pushed a prompt change on Thursday. On Friday, a customer reports the agent booked a meeting room that doesn't exist. On Monday, you have no idea if that incident is an outlier or a pattern. The agent is in production. The evaluation never was. This is the gap that kills agent projects — not the first failure, but the second one, because you had no way to know the first one was coming.

The core problem is that agents break assumptions that made traditional testing feel sufficient. Agents are non-deterministic (the same input can produce different trajectories), the unit of quality is a trajectory (a sequence of tool calls and context), and the failure modes change as the agent evolves. Static test suites go stale; dashboards tracking latency and token counts don't catch quality regressions.

## Forces

- **Agents are trajectories, not calls.** A single agent turn involves a planner decision, a tool call, a tool response, and potentially a retry loop. Evaluating only the final output misses the decision chain that produced it.
- **Failure modes evolve.** An agent that once failed on basic correctness may start failing on escalation quality once correctness improves. A metric that was right at launch becomes misleading six months later.
- **Ground truth is expensive and incomplete.** You cannot hand-label every production interaction. Thumbs-up/thumbs-down feedback is sparse and un-actionable. Manual review covers less than 1% of real interactions.
- **Non-determinism makes regression tricky.** A test that passes on one run and fails on the next may not be flaky — it may be revealing a genuine sensitivity to context. You need tolerance built into your scoring.

## The move

The three-layer eval stack that separates teams who ship from teams who keep shipping:

**1. Start end-to-end, define success as a binary.** Before any sophistication, define one question: did the agent complete the user's task? Score yes/no. This catches regressions immediately and takes minutes to set up. Everything else builds on top.

**2. Use three evaluator types in a stack — not one.** Deterministic verifiers check properties (did the agent call `lookup_patient` exactly once? did it avoid `prescribe_medication` entirely? does structured output parse as valid JSON?). These are fast, cheap, and unambiguous. LLM-as-judge handles quality dimensions that require semantic reasoning (was the response helpful? did the agent explain its reasoning clearly?). Human review validates calibration and catches "metric green, user red" patterns. Each type covers what the others miss.

**3. Build the golden dataset from production failures, not imagination.** The highest-value test cases are the ones you did not anticipate. Every production failure gives you: an authentic edge-case input, the real tool context it encountered, and a concrete definition of what "broken" looks like for your system. These are better than handcrafted tests by a wide margin.

**4. Wire production traces into a regression flywheel.** The loop: production failure → trace capture → test case extraction → golden dataset entry → CI/CD release gate. Same failure cannot ship silently twice. AgentClash's 4-month pilot with 18 engineers caught 23 pre-release regressions this way, cutting median root-cause identification time from 4.2 hours to 22 minutes.

**5. Score traits, not exact outputs.** A real agent eval scores behavioral properties, not string matches. The agent's response text will vary; whether it called the right tool, avoided a forbidden tool, and produced structurally valid output — those traits are stable across runs.

**6. Let the dashboard evolve with the agent's maturity.** Early agents need basic correctness checks. Agents that achieve basic correctness need cost, behavior, safety, and edge-case metrics. The dashboard changes when the bottleneck changes. Keep the metric set small but updated.

**7. Calibrate LLM-as-judge against human review on a sample.** Run human review on a random sample of traces. Use that sample to validate whether your LLM judge and human assessors agree. In high-stakes domains (finance, legal, healthcare), calibrate before trusting. State Farm uses this to continuously validate judge accuracy — if the judge diverges from humans, they investigate before the judge makes thousands of calls at scale.

## Evidence

- **HN thread (Evaluating Agents, Sep 2025):** Practitioner describing that teams should start with e2e eval defining a single success criteria as yes/no — identify edge cases, refine prompts, measure progress. Key point: "no amount of evals will replace the need to look at the agent traces." — [HN #45121547](https://news.ycombinator.com/item?id=45121547)
- **State Farm Engineering (Jun 2026):** LLM-as-judge enables continuous evaluation of thousands of real interactions at scale without ground truth. Validates the judge against human review on a sample. Turns evaluation scores into actionable engineering work through meta-analysis of failure categories. — [engineering.statefarm.com](https://engineering.statefarm.com/grading-the-machine-using-llm-as-a-judge-to-monitor-ai-agents-in-production-25a071db9c50)
- **Arthur.ai (Jun 2026):** Production failure → trace → test case → golden dataset → CI/CD release gate. Highest-value regression test dataset comes from production failures, not handcrafted tests. Real input distribution and concrete definition of "broken" are irreplaceable. — [arthur.ai](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **AgentClash (ACL 2026 Industry Track):** 4-month pilot, 18 engineers, 23 pre-release regressions detected via CI/CD-integrated testing, median root-cause identification from 4.2 hours to 22 minutes. Benchmark traces confirm transferability with failure detection recall >= 0.78 without taxonomy or rubric modification. — [agentclash.dev](https://www.agentclash.dev/ci-cd-agent-evaluation)
- **Langchain eval taxonomy:** Offline evals (curated datasets, reference outputs, correctness and regression) vs. online evals (sampled production traces, quality patterns, safety, drift). Production traces seed offline datasets; offline datasets validate online quality. — [langchain.com](https://www.langchain.com/resources/agent-evals)
- **72Technologies (Jun 2026):** Treating agent behavior as a regression surface, wiring eval harness into CI. Traditional unit tests miss agent regressions; trait-based scoring catches when a model update or tool signature change silently breaks behavior. — [72technologies.com](https://www.72technologies.com/blog/agent-evals-ci-regression-tests)

## Gotchas

- **Tracking latency and token counts is not evaluation.** Those metrics tell you about cost and performance. They do not tell you whether the agent completed the task correctly. A dashboard of those metrics can be fully green while the agent is consistently giving wrong answers.
- **Golden datasets go stale.** Inputs and expected behaviors change as the product evolves. A golden dataset that isn't updated with product changes produces false regressions (agent passes because it's following old rules, not because it's right). Review and trim datasets quarterly.
- **LLM-as-judge has known failure modes.** It can be too lenient (giving passing scores to mediocre outputs), can be biased toward longer answers, and can disagree with humans in edge cases. Calibrate it on a human-reviewed sample before trusting its scores at scale.
- **Non-determinism is not an excuse for no eval.** If your agent sometimes fails the same test, that is not necessarily flake — it may be revealing a real sensitivity to context ordering or tool response formatting. Build tolerance into your scoring functions and run statistically meaningful sample sizes before calling a test flaky.
