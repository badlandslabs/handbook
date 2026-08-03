# Agent Evaluation: Engineering Posts, Tools and Use Cases

## 1. Anthropic Engineering Posts

### Demystifying Evals for AI Agents
URL: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
Published: January 9, 2026

Core thesis: Good evaluations help teams ship AI agents more confidently. Without them, teams get stuck in reactive loops catching issues only in production.

Key concepts:
- An eval = test for an AI system: give an input, apply grading logic, measure success
- Single-turn evals: prompt, response, grading
- Multi-turn evals: agent produces intermediate outputs, grading logic evaluates full trajectory
- Agents call tools, modify state, adapt based on intermediate results

Grading approaches (3 types):
1. Code-based graders: deterministic checks (regex, JSON validation) - fast, cheap, deterministic
2. Model-graded graders: use an LLM judge - higher quality, flexible, handles ambiguity
3. Human graders: golden standard for subjective quality - expensive and slow

Eval lifecycle: Write eval -> Run -> Identify failures -> Diagnose -> Fix -> Re-run
Teams that run this loop weekly improve faster than quarterly.

### Effective Harnesses for Long-Running Agents
URL: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
Published: November 26, 2025

Two failure patterns: (1) One-shotting - agent exhausts context mid-implementation; (2) Premature victory - later instances see existing progress and declare complete.
Solution: Two-Fold Agent Architecture - Initializer Agent + Coding Agent that leaves artifacts for next session.


## 2. OpenAI Engineering Posts

### Testing Agent Skills Systematically with Evals
URL: https://developers.openai.com/blog/eval-skills

Core pattern: prompt -> captured run (trace + artifacts) -> small set of checks -> score
Check categories: Outcome goals / Quality criteria / Convention checks / Side effects.

### Evaluate Agent Workflows
URL: https://developers.openai.com/api/docs/guides/agent-evals

Two-phase approach:
1. Trace grading (debugging): trace = end-to-end record of model calls, tool calls, guardrails, handoffs. Use when: did agent pick right tool? did handoff happen? did workflow violate policy?
2. Datasets + Eval runs (repeatability): benchmarking, comparing prompts, larger-scale evaluations.

### OpenAI Evals (Open-Source Framework)
URL: https://github.com/openai/evals
Stars: 19084 | Forks: 3043 | MIT License | Created: January 23, 2023

Framework to evaluate LLMs plus open-source registry of benchmarks. Run existing evals or create custom ones using datasets to generate prompts, measure quality, compare across models. Now also configurable directly in OpenAI Dashboard.


## 3. Google / DeepMind Engineering

### DeepMind Evals Page
URL: https://deepmind.google/research/evals/

Benchmarks:
- SimpleQA Verified: 1000-prompt benchmark for short-form factuality
- FACTS Grounding: long-form factuality against provided context (up to 32K tokens) - GitHub: https://github.com/google-deepmind/long-form-factuality
- MLE-bench: 75 Kaggle competitions for ML engineering agents - https://arxiv.org/abs/2410.07095
- ASIMOV-Agentic: robotics safety benchmark for safe robot control agents

### Google Cloud: Evaluate Agent Performance
URL: https://cloud.google.com/blog/products/data-analytics/evaluate-agent-performance

Quote: "We run a fixed benchmark, calculate a score, and declare progress. In doing so, we hand our agents a pass/fail exam when what we actually need is a map of the agent capabilities."

### Google Agent Factory: Agent Evaluation
URL: https://cloud.google.com/blog/topics/developers-practitioners/agent-factory-recap-a-deep-dive-into-agent-evaluation-practical-tooling-and-multi-agent-systems

5-Step Agent Evaluation Loop with ADK: Define criteria -> Create test cases -> Run eval -> Analyze results -> Iterate.
Most common failure cause: orchestration/evaluation layer, not the LLM. Traditional model-testing suites ignore multi-turn context, tool-use, and policy compliance.


## 4. GitHub Repos: Evaluation Tools and Frameworks

### AWS Labs: agent-evaluation
URL: https://github.com/awslabs/agent-evaluation
Stars: 369 | Forks: 50 | Apache-2.0 | Created: March 2024
Generative AI-powered framework for testing virtual agents. Uses generator LLM to produce diverse test scenarios, reducing manual test case creation.

### RAGAS (Retrieval-Augmented Generation Assessment)
URL: https://github.com/explodinggradients/ragas
Stars: 15084 | Forks: 1598 | Apache-2.0 | Created: May 2023
Paper: https://arxiv.org/abs/2309.15217 | Presented at EACL 2024
Reference-free evaluation of RAG pipelines - no ground truth human annotations needed.
Metrics: Faithfulness, Answer Relevancy, Context Precision, Context Recall, Context Entity Recall, Response Noise.
Usage: 5+ million evaluations per month for AWS, Microsoft, Databricks, Moodys.
Install: pip install ragas

### DeepEval
URL: https://github.com/confident-ai/deepeval
Stars: 17327 | Forks: 1745 | Apache-2.0 | Created: August 2023
Like Pytest but specialized for LLM applications. LLM-as-judge runs locally on your machine.
Supports AI agents, RAG pipelines, chatbots. Works with LangChain, OpenAI, or any framework.
Agent-specific metrics: Task Completion, Tool Call Accuracy, Agentic Reasoning Depth, Cost Efficiency.
Tracing via @observe decorator on agent functions.

### UpTrain
URL: https://github.com/uptrain-ai/uptrain
Apache-2.0 | ~2700 stars
Open-source unified platform for evaluating and improving GenAI apps.
20+ pre-configured checks covering language, code, embedding use cases.
Root cause analysis on failure cases. Self-hostable with dashboard.
pip install uptrain

### Promptfoo
URL: https://github.com/promptfoo/promptfoo
~12000 stars | Highly active OSS prompt testing tool
Agent evaluation capabilities: Evaluate Coding Agents (OpenAI Codex SDK, Claude Agent SDK, etc.), Evaluate LangGraph (red-teaming stateful multi-agent graphs), LLM-as-judge assertions for agent output quality.


## 5. Commercial Evaluation Tools
