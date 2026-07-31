# S-1925 · The Eval Gap Stack — The Percentage of Teams That Watch Their Agents But Don't Measure Them

The problem surfaces when you're confident about something that isn't true: your monitoring shows green, your traces look reasonable, but you have no idea whether your agent is actually completing tasks correctly. 89% of teams have observability. Only 52% run offline evals. You are probably in the gap.

## Forces

- **Observability ≠ evaluation.** You can see what your agent *did* — every tool call, every turn, every token — without any way to judge whether it *should* have done those things.
- **Correct answers hide broken paths.** An agent that calls the wrong tool, loops twice on retrieval, and then stumbles into the right answer will pass a simple output check every time. Until the path breaks in production.
- **LLM non-determinism compounds.** Unlike deterministic code, agents produce different trajectories on identical inputs. A passing eval today is no guarantee of a passing eval tomorrow — and you won't know until you track it.
- **The eval tooling lagged the agent tooling.** Teams built agents in 2024. The eval frameworks to judge them properly didn't mature until late 2024–2025.

## The move

Separate *observation* (what happened) from *evaluation* (was it right) by building an eval harness that scores trajectories, not just outputs.

**The core eval architecture** — grounded in Anthropic's January 2026 framework:

- **Task** = a single test case with defined inputs and success criteria
- **Trial** = one execution of a task (run multiple times; LLM variance is real)
- **Grader** = logic (often an LLM) scoring whether the agent's behavior met the criteria
- **Transcript** (trace/trajectory) = the complete record: all tool calls, intermediate outputs, reasoning steps
- **Outcome** = the final state in the environment — not what the agent *said* it did, but whether it actually happened (e.g., "reservation exists in DB" vs. "agent reported booking")
- **Evaluation harness** = infrastructure that runs the full loop: execute task → collect trace → score with grader → aggregate results

**Layer your eval targets:**

1. **Reasoning layer** — Is the LLM making the right planning decisions? Does it decompose the task correctly? Choose the right tools? This layer is scored separately from execution so you can pinpoint regressions to the model or the prompt, not the tool infrastructure.
2. **Action layer** — Are tool calls correctly formatted, with correct arguments, calling the right endpoints? ToolCorrectnessMetric and ArgumentCorrectnessMetric (DeepEval) exist specifically for this.

**Pick your evaluation method by what you can measure:**

- **Outcome-based (strongest when available):** Check the final state. Reservation in the DB. Email sent. File created. This is unambiguous and requires no LLM-as-judge overhead.
- **Trajectory-based:** Check the path. Did the agent follow the expected steps? Were intermediate results interpreted correctly? This is where agents most often silently fail.
- **LLM-as-judge (G-Eval):** Use a separate LLM to score on multi-dimensional rubrics. Chain-of-thought scoring (generate reasoning → produce score) outperforms direct scoring. Calibrate judges against human annotations — run Spearman correlation to check alignment before trusting results.
- **Reference-free (RAGAS / faithfulness metrics):** When ground-truth answers aren't available. Checks whether the response is grounded in the retrieved context.

**Run evals at the right cadence:**

- **Offline (pre-deploy, pre-release):** Test suites on curated datasets — runs on every PR, gates deployment. DeepEval's pytest-native approach (`@pytest.mark.parametrize`, `assert_test()`) makes this frictionless for existing CI/CD pipelines.
- **Shadow mode (production sampling):** Run production inputs through the eval harness without acting on results. Catch regressions before they affect users.
- **Online (live monitoring):** Score a percentage of live interactions automatically. Langfuse and Arize Phoenix both support automated trajectory scoring on production traces.

**Pick the right benchmark for the agent type:**

- **AgentBench** (8 environments: OS, DB, KG, Digital Card Game, Householding, WebShop, WebBrowsing, Lateral Thinking Puzzles) — broad capability assessment, cross-model comparison. Leaderboard at llmbench.ai/agent.
- **BFCL** (Berkeley Function Calling Leaderboard) — tool-calling accuracy, API interaction quality.
- **GAIA** (General AI Assistants benchmark) — real-world web tasks requiring multi-step reasoning and tool use.
- **API-Bank** — agent interaction with external APIs.
- **MINT** — multi-hop reasoning via tool use.

## Evidence

- **LangChain State of Agent Engineering Survey (1,340 practitioners, Nov–Dec 2025):** 57.3% have agents in production (up from 51%). 89% have observability instrumented. Only 52% run offline evals. Only 37% run online evals. Quality is the top blocker at 32%, followed by security at 24%. — [LangChain State of Agent Engineering](https://www.langchain.com/state-of-agent-engineering)
- **Anthropic Engineering — "Demystifying Evals for AI Agents" (Jan 9, 2026):** Framework defining Task/Trial/Grader/Transcript/Outcome/Harness as the vocabulary for agent evaluation. Key insight: evaluate outcomes (environment state), behaviors (trajectory properties), and regressions (test suites) as distinct concerns. — [Anthropic Engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **HN Discussion — "Principles for Production AI Agents" (July 2025, 128 points):** Practitioner thread on eval practices. Key quote: "Evals are a core part of any up to date LLM team. If some team was just winging it without robust eval practices they're not to be trusted." Thread discusses starting with hundreds of evals then narrowing to specific features, and finding LLMs are "not good critics" of their own output — requiring calibrated human-in-the-loop or stronger judge models. — [Hacker News](https://news.ycombinator.com/item?id=44712315)
- **LangChain Agent Evals Resource (2026):** 89% observability vs. 52% offline eval / 37% online eval gap documented. Notes that standard output-only checks miss path fragility — agents can reach correct answers via broken execution routes that fail under distribution shift. — [LangChain Agent Evals](https://www.langchain.com/resources/agent-evals)

## Gotchas

- **Checking the final output is not evaluating the agent.** A correct answer via a wrong path is a ticking failure. You need trajectory checks, not just outcome assertions.
- **LLM-as-judge needs its own evaluation.** Judges hallucinate too. Run correlation against human-annotated samples before deploying judges in production gates.
- **Eval datasets drift.** The test set you built in January reflects your agent's world in January. As your product, user base, and context change, your eval dataset needs refreshes — otherwise you're testing against a ghost.
- **Single-trial runs are noise, not signal.** LLM outputs vary across identical inputs. Run at least 3–5 trials per task and track variance, not just pass/fail.
- **Observability and evaluation are complementary, not interchangeable.** Traces tell you what happened. Evals tell you whether what happened was right. You need both.
