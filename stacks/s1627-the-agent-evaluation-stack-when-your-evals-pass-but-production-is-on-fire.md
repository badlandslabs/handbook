# S-1627 · The Agent-Evaluation Stack — When Your Evals Pass but Production Is On Fire

Your eval suite is green. Your release pipeline is clean. Three weeks after deployment, a customer reports the agent told them the return window is 90 days — it is 30 days, changed three weeks ago. Your staging evals never caught it because they run on the same test cases written before the policy changed. Your dashboards show no errors. You have no idea anything is wrong until a human flags it.

This is the eval gap: the distance between checking what you anticipated and catching what you didn't. Most teams build evaluation as a pre-deployment gate and call it done. The teams that ship reliable agents treat evaluation as a continuous loop — offline tests that gate releases, online tests that watch live traffic, and a flywheel that turns every production failure into a new test case.

## Forces

- **The outcome-output mismatch.** Agent dashboards track latency, tokens, traces, and tool calls — useful signals, not proof the agent did the job. The agent can execute a perfect trajectory toward the wrong goal and score green across every metric.
- **Static datasets go stale.** Evals written in February test against the world of February. Policy changes, API behavior shifts, and distribution drift all go undetected because the eval dataset never updates.
- **Agents fail in ways LLMs don't.** Standard LLM benchmarks measure final output quality. Agent evals must also measure trajectory — did the agent take a sound path, use the right tools, recover from errors, and stop at the right time? The process matters as much as the answer.
- **Eval-as-judge introduces its own bias.** LLM-as-a-judge scales evaluation cheaply but inherits the judge's own blind spots, position effects, and hallucination tendencies. A judge model can rate a broken trajectory as acceptable.
- **The 52-point gap.** Research across production teams shows 89% have observability but only 37% run online evaluations. Most teams know something broke — they just don't have a way to measure it automatically.

## The Move

**Layer three evaluation modes in a closed loop — offline, online, and ad-hoc — with production traces feeding the dataset.**

1. **Trace before you test.** Read 20–50 raw agent traces by hand before building any eval infrastructure. Understand whether the agent fails on reasoning, tool selection, parameter construction, or silent assumption. You cannot evaluate what you haven't observed.

2. **Write unambiguous success criteria per task.** Not "did the agent do a good job" but "did the agent complete steps A, B, and C in that order and produce output matching schema X." Ambiguous criteria produce noisy eval scores that tell you nothing.

3. **Gate releases with offline evals in CI.** Treat agent eval failures like test failures — block the merge. Run them against every material change to prompts, tools, or model versions. Datadog's contract-redliner example shows this pattern: golden datasets → trajectory capture → rule + LLM-as-judge scoring → CI gate.

4. **Run online evals on production traffic, not just your eval dataset.** Sample live requests, run them through evaluators on an ongoing basis, and track scores over time. A drop after a deploy triggers an alert; a trend line shows regression before users complain. 91% of ML systems experience silent performance degradation without this.

5. **Use deterministic checks for exact things, LLM-as-judge for everything else.** Tool-call sequence and schema compliance are deterministically checkable — write rules for those. Response quality, reasoning coherence, and goal completion require a judge. Don't use an expensive judge for what a regex can verify.

6. **Turn every production failure into a test case.** When a real failure surfaces, capture the trace, write the success criteria, add it to the dataset. The eval dataset should grow from production reality, not from imagined test cases. This is the flywheel that closes the gap.

7. **Evaluate at three levels.** End-to-end: did the task succeed? Trajectory-level: was the path efficient and sound? Component-level: which retriever, tool, or sub-agent broke? Each level catches different failure modes.

## Evidence

- **Survey (arXiv:2507.21504, KDD '25):** Systematic review of 84 papers (2023–2025) found 83% report capability metrics while only 30% consider human-centered or economic axes — indicating a systematic underweighting of real-world reliability in how the field evaluates agents. — [arXiv:2507.21504](https://arxiv.org/html/2507.21504v1)
- **Blog post (Chanl, April 2026):** Survey finding that 89% of teams have observability but only 37% run online evaluations, with a concrete example of a policy-staleness failure that staging evals missed because the test data predated the policy change. — [chanl.com](https://www.channel.tel/blog/online-evals-offline-evals-production-ai-agents)
- **Blog post (Tian Pan, Sept 2025):** Prescriptive sequence for getting evaluation right: trace review → unambiguous criteria → offline eval dataset → CI gate → online monitoring → flywheel. — [tianpan.co](https://tianpan.co/blog/2025-09-23-agent-evaluation-readiness-checklist)

## Gotchas

- **Benchmarks are not evals.** SWE-bench, HumanEval, and MMLU measure capability at a point in time against a fixed test set. They tell you nothing about whether your agent will handle your specific users, your specific APIs, and your specific failure modes. Use benchmarks to compare models; use evals to ship your agent.
- **LLM-as-a-judge needs its own evaluation.** A judge model can rate a broken trajectory as acceptable due to surface-level polish. Calibrate judges against human-labeled examples before trusting them at scale. LangSmith and TruLens both offer calibration workflows for this.
- **Trajectory length is not a quality signal.** More tool calls and longer reasoning traces can indicate the agent is lost, not that it is thorough. Weight goal completion and output correctness, not step count.
- **Eval staleness is invisible.** A test case written against last quarter's product behaves like a test case written against a different product. Set a schedule to audit eval datasets for relevance, not just correctness.
- **The intent-execution gap is unobservable by default.** Most tooling records what happened (tool X was called, output was Y) but not why the agent deviated from the plan. Without intent-level instrumentation, you can see the symptom but not the cause.
