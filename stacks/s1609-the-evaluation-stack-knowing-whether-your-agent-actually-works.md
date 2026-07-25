# S-1609 · The Evaluation Stack — Knowing Whether Your Agent Actually Works

You shipped the agent. The benchmark said 94% accuracy. Production traffic shows 61% task completion and your largest enterprise customer just filed a complaint about hallucinations in the underwriting copilot. You have no idea which runs were bad, which steps failed, or whether the benchmark ever matched your real workload. This is the stack for evaluating agents before, during, and after deployment.

## Forces

- **Agents are non-deterministic systems, not functions.** Traditional software tests check "same input → same output." Agents produce different trajectories on identical inputs, call tools in unpredictable orders, and fail in ways that live in the middle of a multi-step workflow — not at the end.
- **End-to-end pass/fail hides everything that matters.** A task can "succeed" after 47 wrong tool calls that got corrected by accident. Or it can "fail" because a parameter was slightly off on step 3 of 12. You need component-level visibility, not just outcome scoring.
- **Benchmarks don't transfer.** MMLU, GPQA, and HumanEval scores do not predict agentic capability. A model scoring in the 99th percentile on trivia can fail at a five-step WebArena task. Public agent benchmarks measure specific task categories — your production workload is not one of them.
- **Evaluation data is expensive and goes stale fast.** Golden datasets require expert annotation. Production traffic shifts. Without a compounding feedback loop, your evals drift from reality over time.
- **88% of AI agent pilots never reach production** — the top blocker is not model quality, it's the absence of observability and evaluation infrastructure.

## The move

**Build a three-layer evaluation system that runs offline before deploy and online after, with production traces feeding back into test data.**

### Layer 1 — Task success (session-level outcome)

Measure whether the agent completed what it was asked to do. Track:

- **Task completion rate** — did the agent reach the end goal?
- **Trajectory quality** — how many steps did it take? Were there loops, retries, or unnecessary detours?
- **Error budget** — what fraction of runs hit a failure mode (tool error, hallucination, timeout, handoff failure)?

Use task success as your primary release gate in CI.

### Layer 2 — Step precision (node-level component checks)

Inspect individual decisions within a trajectory:

- **Tool selection accuracy** — did the agent pick the right tool for each step?
- **Argument correctness** — were parameters correct, complete, and within valid ranges?
- **Handoff accuracy** — in multi-agent systems, did control transfer to the right agent?
- **Hallucination detection** — did the agent claim to call a tool it didn't, or invent facts from pretrained knowledge?

Anthropic's eval framework calls the full record of a run a *transcript* (also called *trace* or *trajectory*); a *grader* applies multiple *assertions* (checks) to score components. Run graders against every production trace to catch component-level failures that don't appear in end-to-end scores.

### Layer 3 — Operating envelope (system efficiency)

Track cost and performance alongside quality:

- **Token usage per task** — agents that solve problems with fewer calls are more practical to deploy at scale
- **Latency per step and end-to-end** — multi-step agents compound latency
- **Tool call count** — excessive tool calls signal poor planning or retry loops
- **Cost per successful task** — the only metric that connects quality to economics

### The eval flywheel: production traces → golden datasets → offline CI → online monitoring

1. **Start with production traces.** Use OpenTelemetry (OTEL) to instrument every tool call, LLM call, state change, and handoff. Collect structured traces from live traffic — these are your most representative test inputs.
2. **Build golden datasets from real failures.** Annotate traces where the agent failed or degraded. Tag each by failure mode (tool error, hallucination, loop, handoff failure). Grow a "silver" dataset from synthetic generation (LLM-generated edge cases), promote to gold via human review. Databricks and others now offer synthetic data pipelines specifically for agent eval datasets.
3. **Run offline evals in CI.** Before any deploy, run the agent against your golden dataset. Assert on task completion rate, grader scores, and operating envelope metrics. Gate on passing thresholds — do not let "it looks better" drive releases.
4. **Monitor online in production.** Track success rates, latency, cost, and error budgets on live traffic. Set alerts for regressions below threshold. Route edge cases and low-confidence outputs to human review queues.
5. **Close the loop.** Flag production failures, annotate the root cause, add to the golden dataset. Evals compound over time.

### Practical tooling choices

- **LLM-as-a-Judge** scales subjective evaluation. Use a grader model (ideally stronger than the agent model) to score trajectory quality. Calibrate with human-labeled samples first — LLM judges have known biases (position bias, verbosity bias). `agent-as-a-judge` (metauto-ai, 800+ GitHub stars) and AWS Labs' `llm-evaluation-system` (multi-judge jury scoring) are open-source approaches.
- **Specialized benchmarks** for specific domains: **WebArena** (web automation, best agents achieve ~60-72% vs 78% human baseline), **GAIA** (multi-step reasoning, 466 real-world tasks), **SWE-bench** (software engineering), **AgentBench** (multi-domain), **tau-bench** (policy-compliant tool use).
- **Observability platforms** with agent-specific trace support: LangSmith (LangChain ecosystem), Phoenix (Arize), OpenTelemetry + Grafana/Prometheus, Traceloop, Confident AI. Most new stacks standardize on OpenTelemetry as the transport and schema.
- **Framework support** for evaluation instrumentation: LangChain + LangGraph (built-in LangSmith), AutoGen 0.4 / AG2 (event-driven architecture with observability), CrewAI (role-based, lighter), Microsoft Agent Framework (AutoGen + Semantic Kernel unified), Claude Agent SDK (Anthropic's harness for building agents on top of Claude Code's execution model).

## Evidence

- **Anthropic Engineering Blog:** Published "Demystifying evals for AI agents" (Jan 2026) defining the core eval vocabulary — Task, Trial, Grader, Transcript, Outcome — and advocating for transcript-level inspection over end-to-end scoring. Stresses that evaluation value compounds over the agent lifecycle. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

- **Snorkel AI / ZenML LLMOps:** Built UNDERWRITE, an expert-annotated benchmark for AI agents in commercial insurance underwriting using LangGraph + MCP, evaluated by CPCUs. Found frontier model accuracy ranging from single digits to ~80% depending on provider. Tool use failures appeared in 36% of conversations; hallucinations from pretrained domain knowledge were a separate major error class. — https://snorkel.ai/blog/evaluating-ai-agents-for-insurance-underwriting/

- **Confident AI Blog:** Documents the two-level failure taxonomy for agents: (1) *End-to-end failures* — task never completed, infinite loops, unacceptable latency/cost; (2) *Component-level failures* — wrong tool selected, incorrect parameters, tool outputs unused, wrong handoffs, model claiming tool calls it never made. Stresses that "metric green, user red" is common when evaluating only at the outcome level. — https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide

- **Maxim AI / Benchmarking Agents:** Three-layer evaluation framework: System Efficiency (latency, tokens, tool calls) + Session-Level Outcomes (task success, trajectory quality) + Node-Level Precision (tool selection, step utility). Documents that 88% of AI agent pilots never reach production, with lack of evaluation/observability infrastructure as the primary blocker. — https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices/ and https://benchmarkingagents.com/agent-benchmarks/

- **Microsoft AI Agents for Beginners:** Advocates a mix of small "smoke test" cases for quick checks and larger evaluation sets for comprehensive metrics. Emphasizes that offline test sets go stale and must be continuously updated with real-world edge cases from production. — https://microsoft.github.io/ai-agents-for-beginners/10-ai-agents-production/

- **Databricks Blog:** Released synthetic data capabilities for agent evaluation (Dec 2024), enabling teams to generate evaluation datasets without waiting for SME labeling. Reports enterprises using agent systems are shifting from monolithic prompts to specialized agent pipelines requiring domain-specific evaluation. — https://www.databricks.com/blog/streamline-ai-agent-evaluation-with-new-synthetic-data-capabilities

## Gotchas

- **LLM judges have biases.** Position bias (preferring responses earlier in context), verbosity bias (preferring longer outputs), and self-preference bias (a model scoring higher on its own outputs) are well-documented. Always calibrate against a human-labeled subset before trusting automated scores at scale.
- **Stochasticity means single runs are unreliable.** Run multiple trials per task and aggregate. A single pass/fail is meaningless for a probabilistic system — Confident AI explicitly recommends re-running critical scenarios because "a flaky pass/fail would mislead."
- **Benchmarks measure proxies, not your workload.** WebArena at 72% doesn't tell you how your coding agent performs on your codebase. Build private evals with real inputs from your domain — public benchmarks are useful for architecture comparisons, not release gates.
- **Step budgets prevent silent cost explosions.** Set maximum token counts and step counts per task. Without them, a looping agent can accumulate thousands of dollars in charges before anyone notices.
- **"Metric green, user red" is the most dangerous failure mode.** End-to-end task success scores can look fine while users experience degraded quality in specific steps. Always combine outcome metrics with component-level grader assertions.
- **Human review is not optional for calibration — it's load-bearing.** LLM judges can catch regressions at scale, but they cannot replace human judgment for ambiguous cases, novel failure modes, or domain-specific quality standards. Budget human review as a calibration mechanism, not an afterthought.
