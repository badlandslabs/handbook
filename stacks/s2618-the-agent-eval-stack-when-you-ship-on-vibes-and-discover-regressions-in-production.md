# S-2618 · The Agent Eval Stack — When You Ship on Vibes and Discover Regressions in Production

Your agent passes all your tests. Your model benchmark score went up 4 points last sprint. Your CI pipeline is green. Then three weeks in production, a prompt change degrades your tool-calling accuracy silently for eleven days before anyone notices — because you were grading the final answer, not the trajectory that produced it. Grading agents like traditional software catches less than 30% of failure events. The rest are invisible until a post-mortem.

## Forces

- **Agents are trajectories, not outputs.** A median of 4–7 tool invocations per agent run means 4–7 independent failure points per task. Grading only the final output is like grading a math test on the final answer alone — you catch the runs that failed loudly and miss the ones that reached a wrong conclusion by an apparently correct path. (NVIDIA, May 2026)
- **Traditional testing assumptions collapse.** Traditional software assumes deterministic outputs, a single correct answer, reproducible results, and pre-deployment completeness. Agents assume non-deterministic outputs, multiple valid paths, varying results from identical inputs, and behaviors that only emerge under production load. You cannot apply the same assertion model. (The Thinking Company, March 2026)
- **Aggregate metrics mask where things broke.** A single pass/fail rate tells you the agent regressed, not where. A layer-isolated approach with per-slice deterministic gates catches regressions in specific components (tool routing, memory retrieval, output formatting) that a single aggregate number would bury. (Lumivate / arXiv:2606.11686, June 2026)
- **Eval datasets drift.** Production usage evolves. Edge cases that were 2% of traffic become 20%. An eval suite that isn't refreshed from production logs gradually becomes a fantasy. Teams that skip evaluation investment typically spend 3–5× more on incident response and quality remediation. (McKinsey Digital, 2025, cited by The Thinking Company)
- **LLM-as-judge introduces systematic bias.** Single-model judges show length bias (longer answers appear better), self-model bias (favor outputs from similar models), and domain-blindness in specialized fields. These aren't minor noise — they're directional distortions that can make a worse agent look better. (arXiv:2508.02994, August 2025)

## The Move

Build a layered evaluation architecture: offline regression suites that gate deployment, online shadow evaluation that watches production traffic, and human calibration anchors that prevent eval drift. The framework you choose is downstream of this architecture — it doesn't replace it.

### Core practices

- **Start with end-to-end binary success evals.** Define one question per agent: did it accomplish the user's goal? Output a yes/no. This is much better than no evals. Add trajectory-level checks once you have baseline coverage. (aunhumano, September 2025)
- **Build your golden dataset from production traces.** Dogfood your agent internally, collect real traces, hand-curate the cases that went wrong. Real production cases predict real production performance better than any synthetic dataset. Prioritize adversarial inputs, edge cases, and the failure modes you paid to discover. (HN user kbdiaz, 2025)
- **Use trajectory-level evaluation, not just output grading.** Test the full execution path — which tools were called, in what order, with what parameters. An agent can reach the right answer via an unreliable path, and that unreliability will surface in production as fragility under drift. (LangChain agentevals, 2025)
- **Layer your eval types.** Offline regression catches known failure modes before deployment. Online/shadow evaluation watches production traffic for failures you didn't anticipate. Neither alone is sufficient. (Big Data Boutique, May 2026)
- **Calibrate LLM-as-judge against human feedback.** Run a sample of judge scores through human reviewers. Measure agreement. Tune the judge prompt or switch the judge model until human-LLM agreement is acceptable for your domain. (LangSmith Align Evals, 2025)
- **For highly specialized domains, use multi-agent debate.** Replace a single judge with two adversarial agents arguing opposite verdicts. CourtEval and DEBATE frameworks show this reduces systematic judge bias in legal, medical, and financial evaluation. (arXiv:2508.02994, August 2025)
- **Isolate eval slices to localize failures.** Decompose your agent into architectural layers (tool routing, context retrieval, output generation, memory read/write). Write deterministic, no-LLM assertion slices per layer. Aggregate pass-rates will hide which layer broke; per-slice gates pinpoint it. Lumivate's 238-case suite across 23 slices runs in 2.39 seconds and gates CI with regression-locked baselines. (arXiv:2606.11686, June 2026)
- **Allocate 10–25% of agent operating costs to evaluation.** Production quality scoring (LLM-as-judge on sampled outputs), human review on a 5–10% sample, monitoring infrastructure, and shadow testing together typically cost USD 5,000–20,000 per agent per year. This is cheaper than the incidents it prevents. (The Thinking Company, March 2026)

## Evidence

- **HN practitioner on golden dataset construction:** "Shipping early/dogfooding internally, collecting real traces, and then hand-curating a golden dataset from those traces" — recommends this approach over synthetic benchmarks for teams without established evaluation methodology. (HN Ask: How are people doing AI evals these days?, 2025) — https://news.ycombinator.com/item?id=47319587
- **monday.com on offline evals as safety net:** Built a code-first evaluation strategy on LangSmith, testing groundedness, retrieval accuracy, and tool-calling plus edge cases like knowledge base conflicts. Describes offline evals as "the safety net" for core logic — catching regressions before they reach users. (LangChain blog, 2025) — https://www.langchain.com/blog/customers-monday
- **Layer-isolated evaluation at Lumivate:** 238 baseline cases across 23 architectural slices, pure deterministic execution in 2.39s (~10ms/case), with per-slice regression gates that identify exactly which layer failed. Demonstrated that aggregate pass-rates mask where regressions occurred. (arXiv:2606.11686, June 2026) — https://arxiv.org/pdf/2606.11686
- **The Thinking Company's eval cadence:** Runs full benchmark suite for 12 production agents across 4 workflows every Monday. Tracks 10–25% of operating costs to evaluation infrastructure. Organizations skipping eval investment see 3–5× higher incident response costs. (The Thinking Company, March 2026) — https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/
- **NVIDIA on model vs. agent eval:** Model benchmarks test knowledge in isolation. Agent evaluation tests end-to-end behavior: planning, tool use, uncertainty handling, and workflow completion in dynamic environments. The evaluation paradigm shift is from measuring knowledge to measuring outcomes. (NVIDIA Technical Blog, May 2026) — https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation

## Gotchas

- **Synthetic test cases predict synthetic performance.** A dataset you write in a notebook doesn't reflect what real users actually ask. Build from production logs or dogfood traces.
- **A single aggregate eval score is a lie of precision.** 73% pass rate tells you nothing about whether your tool-calling accuracy degraded or your memory retrieval is failing silently. Slice your metrics or you will be surprised.
- **LLM-as-judge will favor your judge model's style.** If your judge is the same family as your agent, it will have systematic leniency bias. Use a different provider or model family for judging.
- **Eval suites rot.** If you don't refresh from production traces quarterly, your eval suite becomes a museum of problems you've already fixed, with no coverage of problems you've recently introduced.
- **Most teams evaluate on vibes.** HN thread on AI evals (2025) found the majority of companies still make model selection decisions based on subjective assessment rather than systematic evaluation — even when they have the infrastructure to do otherwise. The tooling exists; the discipline doesn't.
