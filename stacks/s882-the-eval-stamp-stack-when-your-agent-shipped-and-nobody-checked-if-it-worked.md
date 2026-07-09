# S-882 · The Eval Stamp Stack — When Your Agent Shipped and Nobody Checked If It Worked

You shipped the agent. The benchmark numbers looked fine in the notebook. Six weeks later, a user reports the agent deleted their production database, and you discover it passed every test because the tests never checked for that behavior. The Eval Stamp pattern fixes this: a layered eval surface that puts behavioral assertions on every path an agent can take — before merge, before deploy, and continuously in production.

## Forces

- Agents are probabilistic and multi-step — a small error in step 2 cascades through steps 3–10; traditional unit tests pass and production still breaks
- Early GPT-4 agents completed only 14% of multi-step tasks versus 78% for humans (Galileo 2026); the gap is not capability — it is verification
- Only 5% of AI projects reach production (Cleanlab 2025), and of those that do, only 11% operate at true production scale (Galileo 2026); the bottleneck is quality discipline, not model quality
- Elite teams — the top 15% — achieve 2.2× better reliability outcomes than median teams (Galileo 2026); the difference is systematic eval practice, not better models
- The capabilities that make agents useful (autonomy, flexibility, tool use) also make them harder to evaluate than single-turn LLMs
- 40%+ of agentic AI projects will be cancelled by 2027 due to quality and reliability issues (unverified — internal team estimates); treat as risk signal, not fact

## The move

**Layer 1 — Spec your success criteria before writing a single test.**
Define what "done" means for this agent: task completion criteria, output quality thresholds, and the behaviors that are explicitly forbidden (e.g., "never DELETE a database without human approval"). Write these as assertions, not as prose in a design doc. The act of writing an eval is the act of specifying behavior.

**Layer 2 — Offline eval suite: gate on every code change.**
Run a golden-dataset eval against every pull request. GitHub's Copilot team runs over 4,000 offline tests — automated code quality checks and chat capability evaluations — before deploying any model change (ZenML/GitHub 2025). Use DeepEval or equivalent: it runs like Pytest but for LLM outputs, with 50+ plug-and-play metrics for task completion, tool correctness, hallucination, and faithfulness. Tag evals as either *warning* (don't merge if this fails) or *milestone* (track progress, don't block). Scoped, feature-level evals outperform broad eval suites — less surface area, clearer signal.

**Layer 3 — Capture production failures as permanent regression tests.**
The highest-value test cases come from production incidents. When a production trace fails a scorer, convert that trace to a dataset entry immediately — Braintrust and LangSmith both support one-click trace-to-dataset conversion. This creates a flywheel: production incidents → regression tests → eval suite grows stronger with every failure. Teams doing this report eval suites that compound rather than stagnate.

**Layer 4 — LLM-as-judge for behavioral dimensions, not factual ones.**
LLM judges are effective for scoring tone, instruction-following, and helpfulness — dimensions where judgment is subjective. They are unreliable for factual accuracy and mathematical reasoning — prefer code-based assertions and static analysis for those. One HN practitioner who worked with "well-respected researchers" reported finding no empirical evidence that LLMs are good critics for factual tasks. Anthropic's own eval documentation recommends using separate, targeted graders for each behavioral dimension rather than a single monolithic judge.

**Layer 5 — Continuous production eval with drift detection.**
Run automated scoring on a sample of live traffic alongside offline tests. When scores degrade beyond threshold, alert and roll back or hold deploy. 92% of teams integrating evals into CI/CD (Galileo 2026), but only 52% run offline evaluation workflows and a smaller fraction run continuous production evaluation — meaning most teams have a eval gap at the production boundary. LangSmith and Braintrust both support this as managed infrastructure.

## Evidence

- **HN discussion (543 pts, 88 comments):** Practitioners debate "LLM as critic" effectiveness; one reports internal experiments found LLMs are not good critics for factual tasks, reinforcing the case for code-based assertions alongside LLM judges — [HN #44301809](https://news.ycombinator.com/item?id=44301809)
- **Anthropic engineering blog (Jan 2026):** Defines the eval vocabulary (task/trial/grader/transcript/outcome), recommends layered graders and trace-based eval; notes that one team built an eval system in 3 months using static analysis + browser agents + LLM judges — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Galileo AI survey of 500+ enterprise practitioners (2026):** 72% deployed agents, only 11% at production scale, top 15% of teams achieve 2.2× reliability advantage over median; early GPT-4 agents completed 14% of multi-step tasks vs 78% human baseline — [Galileo](https://galileo.ai/blog/ai-agent-evaluation)
- **Cleanlab enterprise survey (Aug 2025):** 1,837 respondents, only 95 (~5%) had agents live in production; 70% of regulated enterprises rebuild their AI stack every 3 months — [Cleanlab](https://cleanlab.ai/ai-agents-in-production-2025/)
- **Reddit viral post (r/replit, 2025):** Replit Agent deleted a $1M production SaaS database because: no environment separation (dev/staging/prod looked identical), no human-in-the-loop on destructive actions, no eval checking whether "delete database" was a valid fix for a UI bug — [Reddit r/replit](https://www.reddit.com/r/replit/comments/1m5biur/replit_agent_deleted_a_1m_saas_startups/)
- **AWS Bedrock engineering post (2025):** Amazon's agent eval library on Bedrock uses a two-component framework: a generic evaluation workflow that standardizes assessment across diverse agent implementations, and an agent evaluation library providing systematic measurements and metrics — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **GitHub Copilot eval system (ZenML/GitHub 2025):** 4,000+ offline tests run before any model change ships to production, including automated code quality assessments and chat capability evaluations — [ZenML](https://www.zenml.io/llmops-database/comprehensive-llm-evaluation-framework-for-production-ai-code-assistants)

## Gotchas

- **LLM-as-judge is not reliable for factual dimensions.** Use it for style, helpfulness, and instruction-following. For anything that requires ground truth, use code-based assertions or static analysis. Anthropic's own engineers recommend separate graders per dimension.
- **Eval suites drift stale without a production capture loop.** A static golden dataset built at launch will not catch regressions from upstream data changes, API contract changes, or new edge cases. The regression flywheel (production failure → trace → dataset entry → eval) is the only self-sustaining approach.
- **"Warning" vs "milestone" evals conflated kills team velocity.** If every eval blocks merge, engineers игнорируют all evals. If no eval blocks merge, regressions ship. Tag explicitly and instrument the gate — if a warning eval fails, the build breaks; if a milestone eval fails, it does not block but is surfaced in the PR.
- **Multi-turn eval is not the same as single-turn eval.** You cannot evaluate a 10-step agent by grading only the final output. You need trajectory-level evaluation — check intermediate states, tool call sequences, and decision points. DeepEval and LangSmith support multi-turn eval; simpler frameworks do not.
