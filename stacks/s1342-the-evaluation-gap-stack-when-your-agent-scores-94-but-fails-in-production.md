# S-1342 · The Evaluation Gap Stack — When Your Agent Scores 94% and Fails in Production

Your agent scores 94% on your eval suite. You ship it. Two weeks later a customer reports the agent has been returning structurally wrong outputs since launch. The eval suite still passes. Nobody caught it because your eval suite tests the output, not the decision chain. An agent that confidently picks the wrong tool 6% of the time and generates plausible-but-wrong results 100% of the time will sail through output-scoring evals. This is the evaluation gap: the standard approach to testing software breaks when the software reasons.

## Forces

- **Agents compound errors across steps.** A bad decision in step 2 corrupts step 3, which corrupts step 4, until the final output is wrong. Standard LLM eval (one prompt, one response) cannot catch this. You need to score the decision chain, not just the final output.
- **LLM-as-judge is unreliable for agents.** LLM critics are susceptible to position bias, self-preference, and failing to detect subtle reasoning errors. Practitioners report no empirical evidence that LLM-as-critic works reliably for agent tasks specifically.
- **Eval quality does not transfer to production.** An agent scoring 94% in controlled eval may drop to 81% in production after a minor model provider update — discovered through customer complaints, not dashboards. Offline evaluation (52% adoption) and continuous/online evaluation (37% adoption) have a 15-percentage-point gap.
- **Evaluations are expensive to run at scale.** Thorough evaluation tasks tend to be slow, expensive, and exhibit high variance across N attempts. Running SWE-Bench or Terminal Bench on every code change becomes infeasible quickly.
- **The output tells you nothing about the process.** A causal log (what happened, and why the agent deviated from the plan) is fundamentally different from a temporal log (tool X called, output was Y). Without causal structure, incidents like the DataTalks database wipe are visible in hindsight but invisible in real-time.

## The Move

The eval stack for agents has three distinct layers, each solved by different tools:

### Layer 1 — Trace and Debug (LangSmith)
Inspect what actually happened during a run. LangSmith is the consensus choice for multi-step run tracing. It records inputs, outputs, tool calls, and intermediate steps for post-hoc debugging. The gap it fills: you need to understand *what happened* before you can measure *whether it was right*.

### Layer 2 — Score and Gate (Braintrust)
Measure whether changes made things better or worse, and gate releases on regression. Braintrust provides custom scorers, CI/CD integration, and regression testing against production traffic. The key capability: you define what "correct" means for your specific task domain, then run it against every commit.

### Layer 3 — Safety and Compliance (Patronus AI)
For regulated domains or high-stakes outputs, use a dedicated safety evaluator. Patronus AI focuses on hallucination detection, safety classification, and regulatory compliance — areas where LLM-as-judge has the worst track record and the stakes are highest.

### The Continuous Eval Loop
The most important architectural decision: eval must run continuously, not as a one-time gate. Three patterns that work:
1. **Shadow mode** — run production traffic through the eval scorer in parallel, never blocking on it. Catch regressions before they affect users.
2. **Canary diffing** — route 5% of traffic to the new agent version, compare outputs pairwise against the old version on the same inputs.
3. **Regression suites as code** — define golden inputs and expected outputs as versioned test files. Run them in CI on every PR. Treat eval failures like test failures: you cannot merge until they pass.

### Score the Decision Chain, Not Just the Output
Multi-step agents require per-step scoring. At minimum, track:
- **Tool selection correctness** — did the agent call the right tool?
- **Tool use correctness** — were the parameters correct?
- **Output interpretation** — did the agent correctly use the tool's output for the next step?
- **Final outcome correctness** — did the task complete successfully?

A 60% on tool selection that improves to 65% after a prompt change is more actionable signal than a 94% overall score that obscures which layer is failing.

## Evidence

- **LangChain State of Agent Engineering (Dec 2025):** 57.3% of practitioners now have agents in production (up from 51%). Top blockers: quality (32%), security (24%), cost (16%), latency (14%). Survey of 1,340 practitioners, Nov 18 – Dec 2, 2025.
  — [https://www.langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)
  — Analyzed at: [https://amlalabs.com/blog/langchain-state-of-agents-2025](https://amlalabs.com/blog/langchain-state-of-agents-2025)

- **AgentMarketCap Continuous Eval Report (April 2026):** An agent scoring 94% accuracy in controlled eval may drop to 81% in production after a minor model update. 57% of organizations run agents in production; 32% cite quality as the top blocker to wider deployment. Offline eval adoption at 52%; continuous/online eval at 37% — a 15-point gap.
  — [https://agentmarketcap.ai/blog/2026/04/07/continuous-agent-evaluation-production-braintrust-langsmith-databricks-quotient](https://agentmarketcap.ai/blog/2026/04/07/continuous-agent-evaluation-production-braintrust-langsmith-databricks-quotient)

- **Braintrust Agent Eval Framework:** Multi-step agent evaluation requires scoring the decision chain (tool selection, tool use, output interpretation, final outcome) rather than just final output. LLM-as-judge patterns are unreliable for agent tasks specifically.
  — [https://www.braintrust.dev/articles/ai-agent-evaluation-framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)

- **HN Discussion — "Most AI agents don't survive production" (2025):** Practitioners from deepsense.ai deploying multi-agent systems for pharma, sports analytics, and telecom highlight that the gap between proof-of-concept and production is measured in reliability architecture, not code quality.
  — [https://news.ycombinator.com/item?id=45718390](https://news.ycombinator.com/item?id=45718390)

- **HN Discussion — "Principles for production AI agents" (2025):** Debate on LLM-as-critic reliability. One practitioner: "Over, and over again my experience building production AI tools has been that evaluations are vital for improving performance — but no empirical evidence supports LLM as critic working effectively."
  — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

- **HN Ask — "How are you monitoring AI agents in production" (2025):** Recent incidents (DataTalks database wipe, Replit agent deleting data during code freeze) drove HN discussion on causal vs. temporal logging. "Most tools record what happened, but not *why* the agent deviated from the plan."
  — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

## Gotchas

- **Eval at 94% is not production-ready.** The eval suite measures what you told it to measure. If it scores outputs but not decision chains, a confidently wrong agent will pass. Design evals around the failure modes, not the happy path.
- **LLM-as-judge fails silently for agent tasks.** An LLM judging a single-response task may work. An LLM judging a 12-step agent reasoning chain is prone to self-preference bias and missing subtle reasoning errors. Use deterministic scorers where possible.
- **Eval is not one-time.** A single eval run at launch tells you nothing about what happens after a model update, a dependency change, or a traffic pattern shift. Continuous evaluation catches the 15-point drop that static evals miss.
- **Shadow mode has a cost.** Running evals on production traffic requires careful handling of PII and edge cases. Isolate eval workloads from live data flows.
- **Coding agent evals are uniquely hard.** Benchmarks like SWE-Bench are slow, expensive, and high-variance. Companies like Anthropic (via their engineering blog on harness design) and OpenAI (via critiques of SWE-Bench Pro reliability) have both documented this gap.
