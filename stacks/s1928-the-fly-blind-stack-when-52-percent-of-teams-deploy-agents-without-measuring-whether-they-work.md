# S-1928 · The Fly-Blind Stack

When your agent ships to production and your only quality signal is "a user hasn't complained yet." Evaluation is the gap between "we have agents in production" and "we know whether those agents work." Most teams have the former; fewer than 40% have the latter — and that gap is where projects die quietly.

## Forces

- **Agent outputs are open-ended, not a single correct answer.** Classical ML metrics (accuracy, F1, AUC) assume a ground truth. Agents produce multi-step trajectories where "good enough" is domain-dependent and subjective.
- **A benchmark that passes means nothing about your workflow.** SWE-bench scores tell you about code repair on GitHub issues, not whether your customer service agent handles a billing dispute correctly.
- **Cost and latency are first-class constraints.** A 2-point accuracy improvement that costs 50× more or adds 3× latency is the wrong answer — but most evaluation frameworks don't measure either.
- **Multi-turn behavior is where agents actually fail.** A trace with 47 tool calls and a wrong final answer looks identical to a correct one if you only check the output. You need trajectory-level visibility.
- **Reproducibility requires golden datasets, but building them is painful.** Synthetic prompts are imagination, not reality. Production failures are the highest-signal source — but capturing, labeling, and maintaining them takes infrastructure most teams don't have.

## The move

**Evaluate the trace, not just the output.** The quality of an agent lives in its trajectory — tool call sequence, recovery behavior, and the state mutations it makes along the way.

- **Define success at the workflow level, not the model level.** Ask the workflow owner: "What counts as done?" A password-reset agent succeeds when the reset is confirmed; a coding agent succeeds when the test suite passes. Build pass/fail criteria from that definition, not from generic BLEU/ROUGE scores.
- **Layer three evaluation types:** unit (individual LLM calls, tool outputs), integration (chain behavior, memory reads/writes, handoffs), and end-to-end (task completion from user input to final state change).
- **Use LLM-as-judge as your primary scalable signal.** A judge model scoring 3–5 dimensions (accuracy, instruction-following, tool use correctness, safety, coherence) achieves 70–85% agreement with human reviewers on well-defined rubrics — matching inter-human agreement rates. Design rubrics that map to actual user satisfaction, not abstract quality proxies.
- **Gate CI/CD on a golden dataset sourced from production failures.** Every agent failure in front of a real user is a test case you couldn't have invented. Capture the trace → extract the input → define the correct behavior → add to the suite. Run it before every deploy.
- **Track operational metrics alongside quality metrics.** Token cost per task, latency per step, tool call count, and error recovery rate. An agent that gets 95% accuracy but calls the API 200 times per task is a cost problem.
- **Use public benchmarks for model comparison, not release gates.** SWE-bench, WebArena, and AgentBench compare agent architectures — use them to pick a foundation model or framework. Don't use them as proxies for "this agent is production-ready."

## Evidence

- **LangChain 2026 State of AI Agents survey (1,340 teams):** Only 52.4% run offline evaluations on test sets; only 37.3% run online/production evaluations. Meanwhile, 89% have some observability in place — teams watch their agents but don't measure them. — [langchain.com/stateofaiagents](https://www.langchain.com/stateofaiagents)
- **arXiv 2507.21504 (KDD '25, SAP Labs — "Evaluation and Benchmarking of LLM Agents"):** Formalizes the gap: "LLM evaluation is like examining the performance of an engine. Agent evaluation assesses a car's performance comprehensively, as well as under various driving conditions." Proposes a two-dimensional taxonomy (what to evaluate × how to evaluate) including agent-specific objectives like tool selection accuracy, recovery behavior, and trajectory efficiency. — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **arXiv 2511.14136 ("Beyond Accuracy: Multi-Dimensional Framework for Enterprise Agentic AI"):** Documents the cost and reliability blind spots: 50× cost variation ($0.10–$5.00 per task) for equivalent accuracy; complex Reflexion-style architectures making up to 2,000 API calls for a single task; no reliability metrics in standard benchmarks. Proposes the CLEAR framework (Cost, Latency, Effectiveness, Adaptation, Robustness). — [arxiv.org/html/2511.14136v1](https://arxiv.org/html/2511.14136v1)
- **InfoQ article ("Evaluating AI Agents in Practice"):** "Single-turn accuracy metrics (BLEU, ROUGE) don't capture how agents fail in multi-turn, tool-calling scenarios." Documents that hybrid evaluation (LLM-as-judge + trace analysis + human review) is the non-negotiable standard for teams shipping agentic systems to production. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Arthur.ai ("Regression Test Datasets for AI Agents From Production Failures"):** The highest-value test case is an agent failure in front of a real user. Documents the flywheel: Production Failure → Trace capture → Test case extraction → Golden dataset → CI/CD gate. Argues synthetic prompts cover only anticipated failures; production failures cover what you didn't think to test. — [arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Chanl blog ("LLM-as-a-Judge: Build a Production Eval Pipeline"):** LLM judges achieve 70–85% agreement with human reviewers on well-defined rubrics — matching the 80–85% inter-human agreement rate on the same tasks. Emphasizes rubric design (3–5 dimensions tied to user satisfaction) over judge model selection. — [channel.tel/blog/llm-as-a-judge-production-eval-pipeline](https://www.channel.tel/blog/llm-as-a-judge-production-eval-pipeline)

## Gotchas

- **A passing benchmark is a model comparison, not a release decision.** SWE-bench tells you Model A outperforms Model B on code repair. It does not tell you your customer-service agent is ready to handle billing disputes.
- **LLM-as-judge has a self-preference bias.** Models tend to score outputs from similar-capability models higher. Use a judge from a different capability tier than the agent under test, or fine-tune a specialized judge (e.g., Themis from arXiv 2502.02988).
- **Golden datasets drift.** As your agent, prompts, and upstream models evolve, test cases that passed 6 months ago may no longer reflect correct behavior. Re-label or retire stale cases quarterly.
- **The 75% reliability trap.** An agent with 75% per-trial reliability has only a 42% chance of passing 3 consecutive trials. Define your reliability target based on user impact, not abstract accuracy — a billing-error agent needs higher reliability than a research-summarization agent.
- **Eval saturation is real.** A suite at 100% gives you zero signal for improvement — it only detects regressions. Keep ~20% of cases intentionally hard to track whether you're getting better.
