# S-2613 · The Agent Evaluation Stack

When your agent demo is flawless but production is quietly failing — wrong actions, subtle hallucinations, and cost overruns that nobody notices until the Monday post-mortem.

## Forces

- **Eval metrics differ fundamentally from LLM benchmarks** — task completion and tool-use correctness matter more than BLEU scores, but most teams port their old evals wholesale
- **Success looks identical to catastrophic failure** — a 200 OK HTTP response from a confident hallucination is indistinguishable from a real success without deep inspection
- **Pilot evals can't predict production behavior** — clean benchmarks against synthetic datasets miss the compounding errors and cascade failures that emerge in real workflows
- **Cost compounds silently** — a single misbehaving agent completing 10 steps per request at scale generates bills nobody is watching until month-end

## The Move

Production agent evaluation requires three distinct layers, each with different instrumentation:

**1. System Efficiency Layer (operational health)**
- Token throughput and latency per step
- Tool call frequency and duration
- Cost per session — track this weekly, not monthly

**2. Session-Level Outcomes Layer (did it work?)**
- Task completion rate (binary or graded pass/fail)
- Trajectory quality — was the shortest path chosen, or did the agent loop?
- Rate of successful vs. failed tool invocations

**3. Node-Level Precision Layer (step-by-step correctness)**
- Tool selection accuracy at each step
- Output groundedness — does the agent's action match the observed result?
- Premature termination (gave up too early) vs. over-iteration (looping)

**Core eval methods — combine all three:**

- **LLM-as-Judge**: Use a separate, stronger model to score responses for semantic quality, groundedness, and instruction-following. Scale with sampling; flag low-confidence scores for human review.
- **Golden dataset + automated assertions**: Build a curated eval set of real production inputs with known correct trajectories. Assert tool sequence, output schema, and end-state. Run on every deploy.
- **Shadow mode / canary traces**: Deploy agent in shadow mode alongside production for 1-2 weeks. Capture all traces without acting on outputs. Build your eval set from the real failure modes you observe, not imagined ones.
- **Human-in-the-loop sampling**: Route a random 2-5% of sessions to human reviewers. Use structured rubrics (not open-ended feedback). This is not optional for high-stakes domains — it is how you detect the failures that automated evals cannot see.

**Failure rate you should expect in production:**
- Tool calls fail 3–15% of the time per call (documented by Michael Hannecke across real deployments)
- In a 30-tool incident, a 95% per-call success rate gives only ~21% chance of a clean execution
- Chain that across a multi-agent workflow and you get compound failure probabilities that kill reliability

## Evidence

- **HN Ask HN (2025):** Practitioners running reliability audits before production deployment report that structured eval pipelines catch failure modes that dev testing misses entirely — specifically tool invocation sequences and context-collapse in multi-step tasks — [URL](https://news.ycombinator.com/item?id=47325105)
- **NVIDIA Technical Blog (May 2026):** Three-layer eval framework (System Efficiency → Session Outcomes → Node Precision) with LLM-as-Judge for semantic quality and observability-driven continuous dataset curation — [URL](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)
- **SoftwareSeni (April 2026):** Documented production case where a four-agent AI SRE system costs €8,500/month — 15x the cost of a simple LLM chat — with tool-call failure rates of 3–15% per invocation driving compounding unreliability. Explicitly notes vendor marketing overstates wins and underdiscloses failure rates — [URL](https://www.softwareseni.com/when-ai-sre-fails-production-reality-failure-modes-and-what-they-cost/)
- **Hypersense Software (Jan 2026):** ~88% of AI agent projects fail to reach production (industry research). By 2027, Gartner projects over 40% of AI projects cancelled due to unclear costs and ROI. Root cause: eval practices designed for pilots, not production, plus inability to measure what actually matters — [URL](https://hypersense-software.com/blog/why-88-percent-ai-agents-fail-production)
- **MachineLearningMastery (Feb 2026):** Production agents fail silently — confidently wrong outputs return HTTP 200. Real consequences: financial agents misinterpreting stock tickers, logistics agents shipping to wrong addresses. Automated structural checks catch runtime errors but miss semantic failures — [URL](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance/)
- **AgentReviews (2026):** LangSmith traces provide immutable records of agent decision chains, tool calls, and LLM responses — essential for compliance in regulated sectors. Audit trails are not optional; they are how you prove your recovery methods work — [URL](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)

## Gotchas

- **Pilot evals against synthetic data predict nothing** — build your eval set from shadow-mode traces of real production behavior. The failure modes you imagine are not the failure modes you will see.
- **HTTP 200 ≠ success** — instrument groundedness checks at every action boundary. A tool call that technically succeeded but returned semantically wrong data will propagate silently through the rest of the trajectory.
- **No cost monitoring = no eval** — if you aren't tracking cost per session and cost per tool call, you have no idea if your agent is economical. A verbose agent with a 50-step trajectory can bankrupt a use case that should cost $0.02 per request.
- **LLM-as-Judge has biases** — it systematically over-rewards verbose, confident responses and under-rewards terse, accurate ones. Calibrate against human-labeled samples before trusting scores at scale.
- **Evaluate trajectories, not just endpoints** — a correct final answer reached by a wrong reasoning path will fail on the next slightly-different input. Measure the path, not just the destination.
