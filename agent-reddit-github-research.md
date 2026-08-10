# Agent Evaluation & Failure Handling: Reddit + GitHub Primary Source Research

**Research scope:** Real user complaints, community patterns, and open source tooling from Reddit communities (r/LocalLLaMA, r/LangChain, r/ChatGPT, r/artificial) and GitHub trending/active repositories.
**Compiled:** August 2026 | **Supplements:** agent-failure-handling-research.md, agent-evaluation-research.md

---

## PART 1: REAL USER COMPLAINTS FROM REDDIT

### 1.1 r/LocalLLaMA -- Agent Reliability Complaints

#### Complaint: Small Local Models + Agents = Hallucination Amplifier
**Thread:** Problems with agents (r/LocalLLaMA, ~3 years ago)
**Key quote:** Almost every time I use agents combined with custom tools, the agent tries to use all available tools. It also comes up with its own questions.
**Root cause:** Small local models (<13B params) are terrible at following instructions, leading to hallucinated tool calls and fabricated results.
**Example:** agent_executor.run("What is 7 multiplied by 7") -> model attempts multiple unrelated tools, hallucinates intermediate steps, returns wrong answer.
**Community consensus:** Agent reliability with local models requires either larger context windows, stronger instruction-following models (>=70B), or significant prompt engineering with explicit tool-use constraints.

#### Complaint: Agent Stalls and Infinite Loops in Local Setups
**Thread:** Any updates to the agents scene? (r/LocalLLaMA)
**Observation:** Local setups experience more frequent stalls and looping because: (a) no automatic timeout handling, (b) slower inference delays stuck detection, (c) weaker models struggle with completion detection.
**Community workaround:** Adding explicit max_iterations guards and tool_call_timeout parameters (5-10 second per-step minimum).

#### Open-Sourcing Latent Space Guardrails (wisent-guard)
**Post:** Open Sourcing Latent Space Guardrails that catch 43% of Hallucinations (r/LocalLLaMA, ~1 year ago, 686K members)
**Tool:** https://github.com/wisent-ai/wisent-guard
**Key claim:** Monitors LLM activation patterns at the latent space level to detect hallucinations before they become text output. On TruthfulQA, detects 43% of hallucinations on categories NOT in the training set.
**Community reaction:** Significant interest because it operates below the text level -- catches failures output-layer guardrails cannot see.

### 1.2 r/LangChain -- Production Guardrails and Runtime Patterns

#### Runtime Guardrails That Actually Work
**Thread:** What runtime guardrails actually work for agent/tool workflows? (r/LangChain, ~4 months ago)
**User (tech2biz):** Which guardrails have helped most? We are evaluating bounded retries, escalation thresholds, runtime budget ceilings, tool-level failover policies.

Community responses:

1. **Bounded retry + escalation:** Retry transient failures 2-3x with exponential backoff, then escalate. Do not retry indefinitely -- each retry costs tokens and agent state degrades.
2. **Tool-level failover policies:** If a tool fails (timeout, 5xx), do not halt the agent. Have a defined fallback for each tool category.
3. **Runtime budget ceilings:** Hard token limits per turn and per session. Budget exhaustion should trigger graceful degradation with partial results, not a silent hang.
4. **Escalation thresholds:** Define explicit conditions for human-in-the-loop: PII detected, confidence below threshold, tool failure count exceeded, cost exceeded. The system should define thresholds, not the agent.
5. **Structured output guards:** Pydantic schemas, JSON mode enforcement, and output validation at every tool boundary. Non-parseable outputs are a top source of cascading failures.

### 1.3 r/artificial -- Agent Failure Taxonomy from Users

#### Archive of Ways ChatGPT Fails
**Post:** Archive of ways ChatGPT fails (r/artificial, 1.4K+ upvotes)
**Community-curated failure modes:**
- Confidence without competence: Model produces confident wrong answers, especially in technical domains
- Arithmetic failures: Basic math done incorrectly in multi-step calculations
- Date/entity hallucination: Fictional citations, wrong dates, non-existent papers
- Instruction drift: Following a subtly modified version of the prompt rather than the original
- Context truncation: Forgetting information from earlier in the conversation, especially after 10+ turns

**User insight:** People who want to increase productivity using this tool will need to become familiar with its limitations -- actually problems you will face when trying to use the tool.

### The 72% Variance Problem
Even at temperature=0, LLMs show up to 72% variance across runs on agent tasks. Single-run benchmarks are misleading. Production sees thousands of runs. Community consensus: need statistical evaluation (confidence intervals, multiple runs, Wilson bounds) rather than single-shot pass/fail.

---

## PART 2: GITHUB OPEN SOURCE TOOLS

### 2.1 Evaluation Frameworks

#### alepot55/agentrial | MIT | Python 3.11+ | 18 stars | 80 commits | 450 tests
**URL:** https://github.com/alepot55/agentrial
**Tagline:** The pytest for AI agents. Run your agent 100 times, get confidence intervals instead of anecdotes.

Core thesis: Single-run benchmarks are misleading because LLMs show up to 72% variance across runs even at temperature=0.

Key features:
- Wilson confidence intervals for pass rates (accurate at 0%, 100%, small N -- unlike normal approximation)
- Bootstrap resampling (500 iterations) for cost/latency CIs
- Benjamini-Hochberg correction for multiple comparisons (reduces false positives in large test suites)
- Multi-agent evaluation: delegation accuracy, handoff fidelity, redundancy rate, cascade failure depth, communication efficiency
- Local FastAPI dashboard for browsing results, comparing runs, tracking trends
- Eval packs: domain-specific evaluation packages via Python entry points
- VS Code extension for browsing test suites, running evaluations, viewing flame graphs, comparing snapshots
- Publish results as verifiable benchmark files with SHA-256 integrity checksums

Quick start:
  pip install agentrial
  agentrial init
  agentrial run
  agentrial dashboard
  agentrial packs list

---

#### awslabs/agent-evaluation | Apache-2.0 | 370 stars | 276 commits
**URL:** https://github.com/awslabs/agent-evaluation
**Overview:** A generative AI-powered framework for testing virtual agents. An LLM evaluator (agent) orchestrates conversations with the target agent and evaluates responses during the conversation.
- Evaluator is itself an LLM agent, making it flexible across agent architectures
- Tests virtual agents in realistic conversation scenarios
- Suitable for benchmarking and regression testing
- Actively maintained since March 2024, published on PyPI, Python 3.10+

---

#### simaba/agent-eval | MIT | 31 commits
**URL:** https://github.com/simaba/agent-eval
**Overview:** Practitioner framework for measuring AI-agent performance, safety, reliability, and governance. Built with NIST AI RMF alignment.
Evaluation dimensions: performance benchmarking, safety evaluation, reliability metrics, governance and compliance gates.
Structure: docs/, examples/, schemas/, templates/, tests/, tools/.

---

#### dyronrh/awesome-agentops-landscape
**URL:** https://github.com/dyronrh/awesome-agentops-landscape
**Overview:** Curated AgentOps tools landscape 2026 -- observability, tracing, evaluation, cost monitoring, and guardrails.

Key failure modes addressed:
- Non-determinism: same input -> different outputs across runs
- Autonomy risk: unintended tool selection or unsafe actions
- Complex pipelines: multi-agent orchestration with cascading failures
- Continuous evolution: agents that self-adapt through feedback
- Cost visibility: token-level spend tracking across long sessions

Top OSS tools cataloged (by stars):
| Tool | Stars | Category |
|------|-------|----------|
| LiteLLM | 52.6k | Unified LLM API + observability |
| Langfuse | 30.4k | Tracing and evaluation |
| Promptfoo | 22.9k | LLM evaluation and testing |

Primary reference: Dong, Lu and Zhu -- AgentOps: Enabling Observability of LLM Agents (arXiv:2411.05285, CSIRO 2024)

---

#### Vchitect/Evaluation-Agent | arXiv:2412.09645
**URL:** https://github.com/Vchitect/Evaluation-Agent
**Paper:** Evaluation-Agent: Towards Printable Evaluation via Closed-Loop Design
**Innovation:** Existing evaluation methods assess models by sampling from a fixed benchmark. Evaluation-Agent uses an agent that dynamically adapts its evaluation strategy -- generates, executes, and refines evaluation tasks.

### 2.2 Failure Detection and Recovery Tools

#### NassimRahimi/agent-failure-recovery | MIT License
**URL:** https://github.com/NassimRahimi/agent-failure-recovery
**Tagline:** Runtime controls for agentic AI -- failure detection, recovery patterns, rollback, and runtime controls.
**Key innovation:** Deterministic simulation requiring NO LLM API key -- the control pattern is the focus.

Demonstrates:
1. Scanner with attribution: Detect unsafe output and trace back to exact agent + tool call that produced it
2. Quarantine bad state: Isolate corrupted agent state without halting the whole workflow
3. Rollback to known-good snapshot: Restore to a previous checkpoint when failure is detected
4. Validate restored state: Confirm the recovered state is actually safe before continuing

Governance questions answered:
| Question | How Addressed |
|----------|---------------|
| Was it caught? | Scanner with attribution |
| Who/what produced it? | Traceback to exact agent + tool call |
| Was it contained? | Quarantine + rollback |
| Is it fixed? | Post-recovery validation |

---

#### agent0ai/agent-zero -- Stuck Loop Issue #1011
**URL:** https://github.com/agent0ai/agent-zero/issues/1011 | Status: closed (completed)

**Bug:** When a tool call hangs (e.g., code execution tool timeout), Agent0 enters a repeat loop and stops responding. Only server restart clears it -- wiping state.

**Root cause in agent.py (~lines 470-491):**
  if (self.loop_data.last_response == agent_response):
      # Only add warning - NO tool execution!
      self.hist_add_warning(message=warning_msg)
  else:
      tools_result = await self.process_tools(agent_response)

When a tool hangs and returns same response -> repeat detection fires -> tools skipped -> same response -> repeat -> infinite loop.

**Fix:** Add a flag to force tool execution even during repeat detection.
  is_repeat = self.loop_data.last_response == agent_response
  if is_repeat and not self.loop_data.loop_break_flag:
      # Force continue with tool execution, not just warning

Linked PR #1781 addresses the tool hang recovery path.

---

### 2.3 Guardrails and Safety Tools

#### wisent-ai/wisent-guard
**URL:** https://github.com/wisent-ai/wisent-guard
**Approach:** Latent space guardrails -- monitors activation patterns inside the LLM to detect unwanted outputs BEFORE they are generated as text.
**Key claim:** 43% detection of hallucinations on TruthfulQA on categories NOT in the training set -- it generalizes beyond seen patterns.
**Why it matters:** Operates at the activation level, catching failures output-layer guardrails cannot see.

---

## PART 3: COMMUNITY-DERIVED PATTERNS

### Pattern A: The Three-Layer Evaluation Stack

| Layer | What It Scores | Failure Mode If Missing |
|-------|---------------|------------------------|
| Final-answer | Last message against expected result | Answer can be right while path was wrong |
| Trajectory | Sequence of steps, tool calls, retries, recovery | Correct answer in 20 steps with two policy violations scores 100% |
| Behavioral | Guardrail compliance, tool access patterns, escalation rates | Agents that work but violate policies ship to production |

From agentpatterns.ai: The signal that improves an agent lives in layers two and three, on real traffic -- not on the held-out set.

### Pattern B: Progressive Failure Hierarchy

Self-Correct -> Fallback -> Degrade Gracefully -> Escalate
(Most errors)    (Repeated)    (Last resort)       (Human)

- Self-correct: Agent retries same step with a refined approach
- Fallback: Switch to a simpler or alternative tool or strategy
- Degrade gracefully: Return partial results with clear indication of what is missing
- Escalate: Hand off to human reviewer or abort with structured error

Circuit breaker: If a tool fails N times in a row -> mark tool as degraded -> route around it.

### Pattern C: The Budget Guardrails Triangle

Three hard limits every production agent needs:
1. Iteration budget -- maximum tool-call rounds (prevents infinite loops)
2. Token budget -- maximum tokens per turn and per session (prevents cost overruns)
3. Time budget -- maximum wall-clock time per step and per session (prevents hangs)

Real failure case (agent-zero #1011): Tool hangs -> repeat detection -> tools skipped -> same response -> infinite loop. Fix required all three: iteration counter + time budget + explicit tool-level timeout enforcement.

### Pattern D: Stuck-Loop Recovery Ladder
**Source:** https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md

Once detection flags a stuck loop, climb a bounded recovery ladder:
1. Nudge -- inject a reminder about the goal
2. Replan -- clear recent context, ask agent to produce a new plan
3. Escalate -- reduce agent autonomy, increase scaffolding
4. Reset -- clear conversation history, restart from initial state
5. Hand off -- surface to human with full trajectory context

Stuck states come in three shapes:
- Repeater: Agent outputs same thing repeatedly -> nudge/replan helps
- Wanderer: Agent changes output but makes no progress -> reset/hand off
- Hoverer: Agent alternates between two states -> escalate threshold

Wrong-shape recovery makes things worse: Telling a wanderer to try a different approach sends it further off-goal.

### Pattern E: Semantic Validation Beyond Exceptions

From Preporato: Traditional try-catch blocks do not protect against agentic AI failure modes.

In agentic AI systems, errors include:
- Hallucinations that return HTTP 200
- Tool calls that succeed technically but fail semantically
- Reasoning chains that produce confident nonsense

Recovery strategy: Semantic validation -- an LLM-as-judge or classifier that evaluates whether the output is correct, not just whether it parsed successfully.

---

## PART 4: REDDIT COMMUNITY PROFILES

### r/LocalLLaMA (~686K members, ~3 years old)
- Tone: Highly technical, skeptical of hype, practical deployment focus
- Top failure complaints: Tool hallucinations, instruction-following failures, infinite loops, cost overruns
- Notable: HN commenters describe as really high quality people and surprisingly collaborative
- Strong interest in: Latent space guardrails, open source evaluation tools, local-friendly agent frameworks

### r/LangChain
- Tone: Developer-focused, framework-specific, production-oriented
- Top failure complaints: LangGraph state management issues, tool binding errors, guardrail implementation complexity
- Community interest: Runtime guardrails, retry/fallback combinations, human-in-the-loop escalation

### r/artificial / r/ChatGPT
- Tone: Mixed technical/non-technical, broader audience
- Top failure complaints: Hallucinations, arithmetic errors, context truncation, confidence without competence
- Community value: Curated failure taxonomies, real-world user impact stories

---

## PART 5: BIBLIOGRAPHY OF NEW SOURCES

1. r/LocalLLaMA -- Problems with agents thread (~3 years ago)
   https://www.reddit.com/r/LocalLLaMA/comments/17aqb76/problems_with_agents/

2. r/LocalLLaMA -- Any updates to the agents scene? thread
   https://www.reddit.com/r/LocalLLaMA/comments/1d5hnqk/any_updates_to_the_agents_scene/

3. r/LocalLLaMA -- Open Sourcing Latent Space Guardrails (~1 year ago)
   https://www.redditmedia.com/r/LocalLLaMA/comments/1jqawj1/open_sourcing_latent_space_guardrails_that_catch

4. r/LangChain -- What runtime guardrails actually work for agent/tool workflows? (~4 months ago)
   https://www.reddit.com/r/LangChain/comments/1rcn3yn/what_runtime_guardrails_actually_work_for

5. r/LangChain -- Implementing Guardrails thread
   https://www.reddit.com/r/LangChain/comments/1mtvu2b/implementing_guardrails

6. r/artificial -- Archive of ways ChatGPT fails
   https://www.reddit.com/r/artificial/comments/102bbl5/archive_of_ways_chatgpt_fails/

7. alepot55/agentrial -- Statistical evaluation framework for AI agents
   https://github.com/alepot55/agentrial

8. awslabs/agent-evaluation -- AWS Labs agent evaluation framework
   https://github.com/awslabs/agent-evaluation

9. NassimRahimi/agent-failure-recovery -- Failure detection and rollback patterns
   https://github.com/NassimRahimi/agent-failure-recovery

10. agent0ai/agent-zero -- GitHub Issue #1011 (stuck loop after tool hang)
    https://github.com/agent0ai/agent-zero/issues/1011

11. dyronrh/awesome-agentops-landscape -- Curated AgentOps tools landscape 2026
    https://github.com/dyronrh/awesome-agentops-landscape

12. wisent-ai/wisent-guard -- Latent space hallucination guardrails
    https://github.com/wisent-ai/wisent-guard

13. simaba/agent-eval -- NIST-aligned AI agent evaluation framework
    https://github.com/simaba/agent-eval

14. agentpatterns.ai -- Exception handling and recovery patterns for AI coding agents
    https://agentpatterns.ai/patterns/agent-design/exception-handling-recovery-patterns/

15. agentpatterns.ai loop-engineering -- Stuck-loop recovery playbook
    https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md

16. Neel Mishra -- Agent Error Handling: Retries and Fallbacks
    https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

17. Preporato -- Error Handling in AI Agents: Circuit Breakers, Retry and Recovery
    https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems

18. Zylos Research -- AI Agent Self-Healing: Automated Recovery and Resilience Patterns
    https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns

19. MorphLLM -- AI Agent Evaluation (2026): Metrics, Frameworks, and Production Failures
    https://www.morphllm.com/ai-agent-evaluation

20. Vchitect/Evaluation-Agent -- arXiv:2412.09645
    https://github.com/Vchitect/Evaluation-Agent

---

## ADDENDUM: WHAT THIS FILE ADDS TO EXISTING RESEARCH

This document adds the following to agent-failure-handling-research.md and agent-evaluation-research.md:

| Content | Existing Coverage | New in This File |
|---------|-----------------|-----------------|
| Reddit r/LocalLLaMA user complaints | HN/blog sources | r/LocalLLaMA threads, real user quotes |
| Reddit r/LangChain runtime guardrail discussion | Framework docs referenced | Real user discussion of what works |
| Reddit r/artificial failure taxonomy | Not covered | Curated community failure list |
| agentrial (statistical eval) | Not covered | Full README analysis |
| awslabs/agent-evaluation | Not covered | Full README analysis |
| awesome-agentops-landscape | Not covered | Comprehensive OSS tool landscape |
| agent-failure-recovery (NassimRahimi) | Partially | Expanded with README detail |
| agent-zero #1011 stuck loop bug | Partially | Full root cause + fix analysis |
| wisent-guard (latent space guardrails) | Not covered | New approach from Reddit release |
| agentpatterns.ai patterns | Partially | Full pattern documentation |
| Three-layer evaluation taxonomy | HN/blog sources | Reddit community validation |
| Progressive failure hierarchy | Partially | Full ladder with stuck-loop shapes |
| Budget guardrails triangle | Partially | Synthesized from multiple sources |