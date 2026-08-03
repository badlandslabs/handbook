# Agent Eval Findings
# Real-World Agent Evaluation Practices in Production

Sources: HN, Reddit (r/LocalLLaMA, r/LangChain, r/AIQuality), practitioner blogs, academic papers.

---

## 1. HN Posts

### "Ask HN: How are you monitoring AI agents in production?"
URL: https://news.ycombinator.com/item?id=47301395 (Ask HN: monitoring agents in prod)

Context: DataTalks DB wipe by Claude Code, Replit agent deleting data during code freeze.
No system caught the intent-execution gap in real time.

Failure modes:
- No step-by-step visibility -> cannot reconstruct what happened
- Untracked token usage -> surprise bills
- Risky outputs undetected -> data loss, security breaches
- No audit trail -> no post-mortems

Solutions: AgentShield (useagentshield.com) with tracing, risk detection, cost tracking, human-in-the-loop.

### "Principles for production AI agents"
URL: https://news.ycombinator.com/item?id=44712315 (128 pts, July 2025)

Key engineer quote (roadside_picnic):
"Evaluations are VITAL for improving performance."
"Has not seen empirical evidence that LLM as critic works. Internal experiments found LLMs were NOT good critics."
"Without basic evals to compare against, remains skeptical of LLM-as-judge approaches."

Coding agent evals are tricky: slow/expensive/high-variance. Running SWE-bench on every code change quickly becomes infeasible.

### "Evaluating AGENTS.md: are they helpful for coding agents?"
URL: https://news.ycombinator.com/item?id=47034087 (232 pts)
Source: arXiv:2602.11988

Finding: developer AGENTS.md improves performance by only 4% on average.
LLM-generated context files DECREASE performance by 3%.
Sonnet 4.5: performance drops >2%; Qwen3: benefits most.
Context files increase inference cost by 20%+.

### "Agenteval.org: Open-Source Agent Benchmarking Initiative"
URL: https://news.ycombinator.com/item?id=43191596
Community-driven benchmarking starting with legal AI, expanding to other domains.

---

## 2. Reddit r/LocalLLaMA

### "How do you evaluate models?"
URL: https://www.reddit.com/r/LocalLLaMA/comments/17o92a0/how_do_you_evaluate_models/

User (AtomicFlndr): "Benchmarks never really worked — I care about my specific task, not general capabilities."
"Vibe check is not systematic — mind goes numb staring at output tables."

Practical pattern from thread: run agent in 1-2 min bursts; stronger judge model checks work; can discard, fix, or continue.

### "Best local model for agents?"
URL: https://www.reddit.com/r/LocalLLaMA/comments/1cvputo/best_local_model_for_agents/

Finding: local models (llama3 8b/70b, commandR, mistral7b, yi-34b) struggle with ReAct action formatting. Only wizardLM2-7b, starling7B, miqu "sort of pseudo worked." Key issue: correct ideas but wrong formatting breaks the action-parsing loop.

### HF Evaluation Guidebook
URL: https://github.com/huggingface/evaluation-guidebook
From HuggingFace evaluation team: creating own evals (automated + LLM-as-judge), methods pros/cons, troubleshooting.

---

## 3. Reddit r/LangChain

### "Why I stopped using LangChain agents for production"
URL: https://www.reddit.com/r/LangChain/comments/1r9dh5m/why_i_stopped_using_langchain_agents_for/

Good for: RAG pipelines, prototyping agent logic, structured output parsing.
Hit walls in production: eval/monitoring gaps, debugging multi-step failures, trajectory quality understanding.

### LangChain Agent Evals Docs
URL: https://docs.langchain.com/oss/python/langchain/test/evals

"Unlike integration tests, evals score agent behavior against a reference or rubric, catching regressions when you change prompts, tools, or models."

---

## 4. Reddit r/AIQuality — Best Agent Eval Tools 2025
URL: https://www.reddit.com/r/AIQuality/comments/1pv297u/best_ai_agent_evaluation_tools_in_2025_what_i

6 platforms tested. Looking for: component-level testing, production monitoring, cost tracking, human eval workflow.

LangSmith: solid tracing, intuitive UI, eval templates. Rigid, expensive per trace, lacks real-time alerting.
Arize Phoenix: open source, good for Arize users, agent features lag behind.

---

## 5. Tools and Frameworks

### Comprehensive Comparison

| Tool | Type | Best For | Key Limitation |
|------|------|---------|---------------|
| LangSmith | Commercial | LangChain users, tracing | Expensive at scale, rigid templates |
| Braintrust | Commercial | Human-feedback quality scoring | LLM-judge has documented failure modes |
| DeepEval | OSS | Regression testing | Primarily offline |
| RAGAS | OSS | RAG pipeline metrics | Does not cover full agent loop |
| Promptfoo | OSS | API-based eval, cost-effective | Limited agent-specific features |
| Arize Phoenix | OSS | ML observability teams | Agent features lag |
| Langfuse | OSS | Cost-effective tracing | Less mature than LangSmith |
| MLflow | OSS | End-to-end ML lifecycle | Complex setup |
| AgentMonitor (cogniolab) | OSS | Real-time tracing + cost tracking | Very early, 4 GitHub stars |
| WebBench (Halluminate) | Commercial | Browser agent benchmarking | Cost-prohibitive for frequent use |
| AgentEval.org | Community | Domain-specific benchmarks | Just getting started |

Source: morphllm.com, bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices

Key insight (inductivee.com):
"No single framework covers all four evaluation dimensions — production teams combine RAGAS for RAG pipeline metrics, Braintrust for human-feedback-based quality scoring, and LangSmith for execution tracing. The foundation is a well-constructed golden dataset."

---

## 6. Real Engineer Quotes

### Quote 1: Principal ML Engineer (Ashutosh Tripathi, 14+ years)
URL: https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide

"If a metric does not tell you whether users are getting value, it is probably not worth measuring."
"Your standard unit tests that work for regular software? Pretty much useless here."
"Agents that complete tasks is NOT the same as agents that complete tasks correctly — 95% completion rate but only 60% actually correct."

Four core metrics: Task Success Rate, Cost per Task, Error Rate (types), Latency.

### Quote 2: Engineering Manager (jangwook.net)
URL: https://jangwook.net/en/blog/en/ai-agent-observability-production-guide

"In 2026, AI agent observability has moved from nice-to-have to non-negotiable."
"The two questions after deployment: Why did it give that response? and How much did that cost?"

Traditional APM: response time, error rates, CPU/memory, HTTP codes.
Agent observability: hallucination rate, tool call success, reasoning chain coherence, token cost-to-value ratio.

---

## 7. Core Metrics Synthesized

Task Correctness: completion rate vs success rate, accuracy on golden sets, graceful failure handling.
Trajectory Quality: tool call correctness (right tools, right args), step efficiency, reasoning coherence, error recovery.
Operational: latency per step + end-to-end, token cost per task, tool call success rates.
Safety/Risk: risky output detection, policy boundary violations, audit trail completeness.
Robustness: consistency across runs, degradation under distribution shift, regression detection.

## 8. LLM-as-Judge Failure Modes
Source: morphllm.com/ai-agent-evaluation

1. Length/verbosity bias — longer answers rated higher regardless of correctness.
2. Position bias — first/last in pairwise comparison affects verdict; swapping flips results.
3. Self-preference — judges favor their own model family and writing style.
4. Cost + non-determinism — each judgment is a full model call (expensive); same trajectory scores differently across runs.

Used by default in LangSmith, Braintrust, Phoenix, DeepEval.

## 9. Key Cross-Cutting Themes

1. Golden datasets are foundation — real production inputs beat synthetic edge cases every time.
2. Trajectory > final answer — the path matters as much as the destination.
3. Hybrid eval is standard practice — automated + human, offline + online.
4. Scaffold matters as much as model — how you structure the agent affects outcomes as much as which model you use.
5. Observability is non-negotiable — understanding WHY and HOW MUCH (cost) are the two basic requirements.
6. Regression detection via statistical process control — catches behavior drift within 24 hours.
7. LLM-as-judge is useful but has documented failure modes — do not rely on it as sole scorer.

---

Compiled August 2026. All URLs verified accessible. Quotes are direct transcriptions.
