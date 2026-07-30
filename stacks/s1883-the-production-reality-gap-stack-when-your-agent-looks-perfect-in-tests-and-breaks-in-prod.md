# S-1883 · The Production Reality Gap Stack — When Your Agent Looks Perfect in Tests and Breaks in Prod

Your agent scores 94% on your eval suite. It passes every CI gate. It ships. Three weeks later, a pattern of silent failures surfaces in production that your tests never caught — because your eval suite tested the wrong thing. The agent was always broken. You just couldn't see it until real users touched it. This is the Production Reality Gap, and it is the most expensive blind spot in agentic systems today.

## Forces

- **Offline evals measure what you thought to test, not what actually breaks.** The 86 deployed agents in the first large-scale production study all had eval suites. Many still shipped with undetected failure modes. The gap isn't effort — it's that real failures live in dimensions offline tests don't cover.
- **Agents have infinite input space.** Users express the same intent in thousands of variations. A test suite of 50 cases cannot cover the tail. Real production inputs arrive with noise, ambiguity, and adversarial patterns that never appear in a controlled eval dataset.
- **Static evals rot.** A dataset of "representative tasks" built at launch degrades as the product evolves. Teams that evaluate thoroughly before launch and stop post-launch experience quality degradation within 30–60 days — Deloitte found continuous evaluation cuts production incidents by 67%.
- **Two eval worlds exist and most teams live in only one.** Offline evals (controlled, reproducible) catch regression but miss novelty. Online evals (live traffic, realistic) catch what you didn't predict but are expensive and noisy. The gap between them is where agents silently fail.

## The move

The move is **bifurcated eval infrastructure with a feedback loop**: one layer that runs reproducible offline tests on every commit, and another that continuously samples production traces and converts failures into test cases. These layers are connected — production failures update the offline suite — creating a system where coverage grows over time rather than stays static.

- **Capture production traces as eval datasets.** Don't just observe what the agent does in production — tag failing traces and export them directly into the eval suite. Braintrust's platformformalizes this: "Production traces become eval datasets. The traces you debug today are the tests you ship tomorrow." The format is identical in both environments so there's no conversion friction.
- **Score at the trace level, not the session level.** Agents fail at individual steps — a wrong tool call, a hallucinated parameter, a loop that should have exited. Braintrust scores factuality, task completion, tool use accuracy, and groundedness per-step, then traces which specific step caused a regression. Session-level pass/fail masks the cause.
- **Snapshot real environment state for offline eval.** Before running offline evals, capture actual tool call outputs from live environments. This closes the gap between "the agent called the right tool" and "the agent would have gotten the right result." Per Braintrust: "Capture tool calls and responses from live environments for accurate offline evaluation scenarios."
- **Run adversarial inputs against every release.** Maintain a red-team set of tricky cases: ambiguous instructions, conflicting tool schemas, prompt injection attempts, and cases that exploit your agent's specific weaknesses. Google Cloud's eval methodology explicitly recommends "tricky inputs: ambiguous instructions, conflicting tool schemas, malicious injections."
- **Use LLM-as-judge for the dimensions you can't programmatically check.** Task completion, reasoning quality, and groundedness require judgment. Chain a second LLM to evaluate the first — but use guardrails: give the judge a rubric with score definitions and weighted criteria so it's consistent across runs.
- **Instrument cost and latency as first-class metrics.** An agent that produces correct output in 60 seconds when users expect 10 has failed. MLflow ships `ToolCallEfficiency` and `RoleAdherence` scorers alongside correctness — reflecting that efficiency and safety are not secondary to accuracy.

## Evidence

- **arXiv 2512.04123 "Measuring Agents in Production":** First large-scale study of 306 practitioners with 86 deployed agents across 26 industries. Found 82% of surveyed agents were in production or pilot. Primary motivation: increasing productivity/efficiency (73%) and reducing human hours (64%). The study notes that most agents had eval suites — but still shipped with undetected failure modes, confirming the offline/online gap is systemic, not anecdotal.
  — [https://arxiv.org/abs/2512.04123](https://arxiv.org/abs/2512.04123)

- **Google Cloud, "A methodical approach to agent evaluation" (Nov 2025):** Recommends adversarial test sets ("maintain a red-team set of tricky inputs"), continuous sampling ("coverage evolves as the product does"), and trace-driven dataset creation. Cites Anthropic's postmortem on a routing bug that ran August–September 2025: "The evaluations we ran simply didn't capture the degradation."
  — [https://cloud.google.com/blog/topics/developers-practitioners/a-methodological-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodological-approach-to-agent-evaluation)

- **Braintrust, "Evaluating agents" (Jan 2025):** Documents the trace-as-dataset pattern, per-step scoring, and the production-trace-to-eval-failure pipeline. Quotes a Bill engineering lead: "Braintrust helps us ship AI agents customers actually trust." The platform's design explicitly bridges offline regression testing and online observability.
  — [https://www.braintrust.dev/blog/evaluating-agents](https://www.braintrust.dev/blog/evaluating-agents)

- **agentevals (GitHub, agentevals-dev, ~148 stars):** Framework-agnostic evaluation built on OpenTelemetry traces. "Benchmark your agents before they hit production. agentevals scores performance and inference quality from OpenTelemetry traces." Self-hostable, spans Python SDK.
  — [https://github.com/agentevals-dev/agentevals](https://github.com/agentevals-dev/agentevals)

## Gotchas

- **A passing eval suite is necessary but not sufficient.** The eval suite only tests what you thought to encode. The most expensive failures — novel input patterns, downstream consequences of correct-seeming decisions, silent data leakage — never appear in offline tests.
- **LLM-as-judge has its own failure modes.** A judge model can be biased, inconsistent across runs, or fooled by confident-sounding wrong answers. Always audit judge scores against a human-labeled sample, especially after model updates.
- **One-time evaluation is a trap.** Teams that evaluate before launch and stop monitoring post-launch consistently see degradation within 30–60 days. Eval must be an operational practice, not a pre-launch checklist. Budget for it accordingly.
- **Eval infrastructure has real costs.** Benchmark suite execution runs $500–$2,000/month; production quality scoring adds $1,000–$3,000/month depending on traffic volume. Teams that treat evals as free find out otherwise when the bill arrives — or worse, when they discover the gaps too late.
