# S-2776 · The Trajectory Eval Stack — When Your Benchmark Tells You Nothing About Your Agent

You shipped an agent. It passes your test suite. It scores well on AgentBench. Six weeks later, users are filing bugs about the agent taking 47 steps to do something that should take 3, calling the wrong tools, and occasionally handing back confident nonsense. Your benchmark said it worked. It doesn't work. This is the trajectory eval gap: standard benchmarks evaluate outputs; production agents are defined by paths.

## Forces

- **Benchmarks test answers, agents are defined by trajectories.** A benchmark that scores a final answer treats the 47-step path and the 3-step path identically. Production teams care about both — the wrong answer is bad, but so is the right answer achieved through a wildly inefficient or dangerous path.
- **LLM-as-judge costs more than running the agent.** Scoring every output with a second large-model inference pass frequently costs more than the agent itself. A single PaperBench run with an LLM judge costs ~$9,500; a six-model comparison crosses $150,000. Teams that only budget for agent compute forget the judge tax.
- **Eval sets decay like test suites in traditional software.** When you update the model, the prompt, or the tools, your eval set produces systematically different scores even if nothing meaningful changed. Maintenance is not optional.
- **Ground truth is often undefined for agents.** A task like "research this topic and summarize findings" has no single correct answer. Rubric-based trajectory evaluation is the only viable path, but rubric engineering is a skill most teams lack when they start.
- **The judge's own biases can flip your conclusions.** LLM-as-judge has a known position bias (prefers longer outputs), a self-preference bias (prefers outputs that resemble its own writing), and a recency bias. A poorly calibrated judge produces systematically wrong quality signals.

## The move

Evaluate at three levels, with different tools and cadences at each:

**End-to-end (did the task succeed?)**
- Binary or rubric-scored task completion using LLM-as-judge on the final output
- Use deterministic assertions wherever ground truth is available (e.g., "does this tool call include the required parameter?")
- Run on a curated eval set that mirrors your production traffic distribution, not just academic benchmarks

**Trajectory-level (was the path sound?)**
- Measure: step count, tool call count, tool correctness rate, recovery attempts, context utilization
- Score intermediate steps with lightweight judges — you don't need a frontier model to verify that the agent called the right tool with the right arguments
- Flag trajectories where the agent diverged from the expected plan or accumulated context without progress

**Component-level (which part broke?)**
- Trace individual tool calls, retrievals, and sub-agent handoffs
- Use deterministic checks on tool schemas and argument shapes before grading outputs
- Isolate failures: a low task-completion score with high tool-correctness means the reasoning layer failed; high tool-correctness with wrong final output means the synthesis layer failed

**Build the eval set from real production failures**
- Every user-reported failure becomes a permanent test case
- Synthesize additional cases from production logs using an LLM to generate variations around failure modes
- Tag eval cases by failure category (tool error, reasoning error, hallucination, efficiency) so you can target regression tests

**Close the loop with production monitoring**
- Collect traces continuously: every tool call, argument, result, and agent decision logged in a structured format
- Detect anomalies: alert when tool error rate, step count, or outcome scores deviate from baseline by more than one standard deviation
- Route user feedback (thumbs-down, escalation) back into the eval set as new test cases within 48 hours

**Budget for the judge, not just the agent**
- Model the full cost: eval_set_size × (agent_inference_cost + judge_inference_cost)
- Consider smaller judge models (7B–13B) for trajectory-level checks where a frontier model adds little signal
- Run expensive evals (full trajectory grading with frontier judges) on a weekly or trigger-based cadence, not continuously

**Calibrate the judge before trusting it**
- Run the judge against a hand-annotated subset of 20–50 cases before relying on it at scale
- Measure agreement between judge and human annotators — if the judge disagrees more than 20% of the time, rebuild the rubric or switch the judge model
- Use pairwise comparison (Agent A vs. Agent B on the same inputs) rather than absolute scoring to reduce rubric-dependence

## Evidence

- **arXiv survey (2507.21504):** Systematic taxonomy of LLM agent evaluation — two dimensions: evaluation objectives (behavior, capabilities, reliability, safety) and evaluation process (interaction modes, datasets, metric computation, tooling). Notes that enterprise-specific challenges include role-based access to data, reliability guarantees, and dynamic environments that academic benchmarks cannot capture. — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)
- **Survey on LLM-based Agent Evaluation (2503.16416):** Comprehensive analysis across five perspectives — core LLM capabilities needed for agents (planning, tool use, memory), application-specific benchmarks (web agents, SWE agents), generalist agent evaluation, core benchmark dimensions, and evaluation frameworks/tools. Key finding: agents require evaluating not just the final output but the entire reasoning-action-feedback cycle. — [arXiv:2503.16416](https://arxiv.org/html/2503.16416v2)
- **ContextQA blog:** Judge model compute is the cost teams forget. "LLM-as-a-judge can be more expensive than running the agent." Documents five cost centers: judge model compute, tooling/platform, human review time, engineering to build harnesses and golden datasets, and ongoing maintenance. Notes a single PaperBench run costs ~$9,500; six-model comparison exceeds $150,000. — [ContextQA: Real Cost of AI Agent Evaluation](https://contextqa.com/blog/real-cost-of-ai-agent-evaluation/)
- **MASEval paper (2603.08835):** Framework-agnostic library for evaluating multi-agent systems. Key finding: across models within a capability tier, framework choice matters as much as model choice. Systems that differ only in topology, orchestration logic, and error handling show substantial performance variation that benchmarks fixing the setup cannot measure. — [arXiv:2603.08835](https://arxiv.org/html/2603.08835)
- **Confident AI:** Metrics that matter for agents group into four areas — tool calling, planning, task completion, and reasoning — plus safety, latency, and cost for production. Three evaluation levels: end-to-end (task success), trajectory-level (path efficiency), component-level (which part broke). Recommends deterministic checks for exact things, LLM-as-judge only for things requiring judgment. — [Confident AI: LLM Agent Evaluation Metrics](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **Zylos Research:** The gap between a naively-configured judge and a well-calibrated one is wide enough to produce opposite conclusions about agent quality. Documents judge position bias (prefers longer outputs), self-preference bias, and recency bias as calibration failure modes. Recommends pairwise comparison and rubric engineering as mitigation. — [Zylos: LLM-as-Judge Patterns](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/)
- **AgentMode AI:** Enterprises buy agent evaluation platforms (DeepEval, Braintrust, LangSmith, Patronus) but then under-invest in the operational disciplines that make them produce useful signal: eval-set design, drift detection, and regression-budget frameworks. — [AgentMode: Agent Evaluation in Production](https://agentmodeai.com/agent-evaluation-in-production)
- **Databricks:** Evaluates agents on single-turn (isolated capabilities) vs. multi-turn (iterative workflows where reasoning depends on prior steps). Notes that multi-turn evaluation requires inspecting continuity, state management, and coherence across steps — something trace-based observability enables. — [Databricks: What is AI Agent Evaluation](https://www.databricks.com/blog/what-is-agent-evaluation)
- **Langfuse cookbook:** Three evaluator types for agent behavior: Final Response Evaluation (black-box output quality), Trajectory Evaluation (path through tool calls), and Tool Call Evaluation (individual tool correctness). Each tests a different aspect; all three together give coverage the final answer alone cannot. — [Langfuse: Pydantic AI MCP Agent Evaluation](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)

## Gotchas

- **Measuring only the final output hides the most expensive failure mode.** An agent can produce a correct answer through a catastrophically inefficient path, burning tokens and latency without failing any output-level metric. Trajectory metrics (step count, tool call count, context reuse rate) catch this.
- **Synthetic eval data without production grounding produces overconfidence.** An LLM-generated eval set will share the distribution and failure modes of the model that generated it. Real production failures and user-reported bugs are the highest-signal eval cases.
- **Eval sets don't survive model upgrades.** A prompt change or model upgrade requires re-running the full eval suite against the new version. Teams that skip this step ship regressions undetected.
- **Judge selection is itself an eval problem.** Using the same model as both agent and judge introduces self-preference bias. Use a different provider or model family for the judge where possible.
- **Latency of evaluation determines whether you catch failures before users do.** If eval runs take 4 hours, you won't catch a regression before the next deploy reaches users. Budget for fast path-level checks in CI and reserve full trajectory grading for pre-release gates.
