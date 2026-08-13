# S-2592 · The Golden Dataset Stack — When Your Agent Leaves the Lab and Enters the Real World

{You built the agent. It works in the demo. Now you need to know if it works on a Tuesday at 11am with real users, real data, and real stakes.}

## Forces

- **The highest-signal test data lives in production, but you cannot test in production** — every regression you didn't anticipate lives in the wild, but deliberately injecting failures to catch them is not an option
- **Agents fail silently in ways unit tests cannot catch** — wrong tool selections, semantic search mismatches, context drift over multi-turn sessions, and non-deterministic outputs that pass a final-answer check but silently skip critical steps
- **The eval space moves faster than any single tool** — "very, very heterogeneous and fast moving" (HN, 2025); no gold standard has emerged, so teams that over-invest in a framework lock themselves into a moving target
- **Human review does not scale with model releases** — every time you swap models or retune prompts, a full human eval pass is too slow to be a release gate

## The Move

The core technique is a **production-failure flywheel**: every real incident becomes a regression test case, and every test case joins a versioned golden dataset that gates releases.

- **Capture full execution traces, not final answers.** When the agent fails, log the entire trajectory — every tool call, every intermediate result, every context window state. The final answer tells you what went wrong; the trace tells you why and where.
- **Build the golden dataset from reality, not imagination.** Start with 20 real cases from production logs or support escalations. Every production failure, bad-feedback session, or incident becomes a new entry. Real cases encode the weirdness of actual usage that synthetic data cannot replicate.
- **Run the dataset as a release gate in CI/CD.** On every prompt change, model swap, retrieval tweak, or tool update, run the full suite. The same failure cannot silently ship twice.
- **Score both outcome and trajectory.** Task-success metrics (did it complete correctly?) are necessary but not sufficient. Score the reasoning path too — did it call the right tools in the right order? Did it recover from errors or skip them?
- **Separate eval environment from production authority.** Give the harness read access to traces and tool mocks; never give an eval run the ability to modify live state. Use replay or sandboxed external tools.
- **Use LLM-as-judge for iteration speed, human review for stakes.** GPT-4 or Claude as evaluator gives fast signal during development. Human spot-checks on high-impact cases (financial, medical, legal outcomes) are the quality floor.
- **Pick one mature eval harness and commit.** The tool landscape is fragmented; bouncing between LangSmith, Arize Phoenix, Ragas, Braintrust, Langfuse, and Comet Opik wastes more time than any of them being wrong. Strands Agents Evals (AWS) works for build-time; LangSmith for LangGraph-native stacks; Phoenix for open-source-first teams.

## Evidence

- **AWS/Motorway case study:** A dealer stock search agent handling ~8,000 dealers and 2,500 vehicles daily reduced incorrect results from **1 in 8 queries to 1 in 50** after building a two-phase eval pipeline (build-time testing with strands-agents-evals + production monitoring with Bedrock AgentCore). Issue detection dropped from hours to minutes.
  — [AWS ML Blog — "Evaluating AI Agents: A production blueprint with Strands and AgentCore"](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-a-production-blueprint-with-strands-and-agentcore/)

- **Hacker News consensus:** An "Ask HN: How are people doing AI evals these days?" thread (~43 comments, 2025) found the space is described as "very, very heterogeneous and fast moving" with no established gold standard. Most teams treat evals as an afterthought. Prompt-model interactions are non-transferable — a prompt that works well on Claude may produce mediocre results on Gemini.
  — [Hacker News — "Ask HN: How are people doing AI evals these days?"](https://news.ycombinator.com/item?id=47319587)

- **LangChain State of AI Agents 2026:** 57% of organizations now have agents in production, with quality cited as the **top barrier to deployment by 32% of respondents**. The survey also found that single agents with well-designed tools outperform complex multi-agent setups for straightforward tasks.
  — [LangChain — State of AI Agents Report](https://www.langchain.com/stateofaiagents)

- **Enterprise adoption gap:** 85% of organizations are using GenAI in at least one function, but the majority of projects stall after pilot. Only a small fraction deploy agents in production. The gap is not a capability problem — it is an evaluation and reliability problem.
  — [Databricks Blog — "The key to production AI agents: Evaluations"](https://www.databricks.com/blog/key-production-ai-agents-evaluations)

## Gotchas

- **Unit tests are necessary but not sufficient.** Standard test suites cover cases you already thought of. Production surfaces the long tail of ambiguous phrasings, malformed inputs, and tool sequences you never anticipated. A regression dataset built from real incidents catches the failures your customers will actually hit.
- **Do not confuse repeatability with truth.** A deterministic eval environment is valuable for regression, but agents operating in the real world face non-determinism. Evaluate against the right outcome first; reproducibility is secondary.
- **Scoring final answers misses the real failure modes.** Agents fail through wrong tool calls, silent step skips, and context drift — none of which appear in the final output. You must evaluate the trajectory, not just the terminal response.
- **Golden datasets go stale.** A dataset that worked for your v1 agent will not cover the capabilities of v2. Treat the dataset as production infrastructure with a maintenance backlog, not a one-time artifact.
- **Over-engineering the eval harness before you have real failures is a trap.** Start with 20 real cases, a simple harness, and human-in-the-loop scoring. Add automation as failure patterns emerge. Teams that build elaborate multi-layer eval pipelines before having real production data end up with a system optimized for cases that don't happen.
