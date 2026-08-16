# S-2730 · The CodeAct Stack — When Your Agent Has a Dozen Tools But Can't Decide Which One to Use

You gave your agent twelve tools: search_web, get_stats, generate_chart, write_file, read_file, send_email, query_db, format_json, calculate, validate_schema, retry, log. It uses search_web to read files, queries the database instead of calculating in-memory, and calls validate_schema on the result of the very tool it should have used instead. The tool catalog grew faster than the agent's ability to choose. This is the fine-grained tool-calling ceiling: more tools create more decision surface, and agents still pick wrong.

The CodeAct pattern inverts this. Instead of giving the agent a large set of narrow tools, give it one tool: write and execute Python code. The agent composes its own actions from a unified, expressive action space — the entire standard library plus whatever packages you pre-install.

## Forces

- **Fine-grained tools create decision overhead.** Every additional tool is another choice the agent must make correctly before it can act. A tool for every operation means the agent spends tokens deciding what to call and parameters to use.
- **Code is already compositional.** The reason you needed ten tools is that each one represented a composable operation: search + calculate + format + write. Python does all four in one expression. The tool wasn't the bottleneck — the action space was.
- **Execution results close the loop.** When an agent calls `search_web("weather")`, it gets back a string. When it executes `weather = requests.get(...)`, it gets back typed, structured data it can immediately act on in the next line.
- **State persists across the session.** Variables in the Python session survive across turns. The agent builds up data structures, intermediate results, and state without needing separate memory management. This eliminates a class of "forgot what I computed earlier" failures.
- **Sandboxing makes it safe.** Running agent-generated code in an isolated execution environment (container, subprocess, E2B sandbox) contains damage. The agent can write and run anything it wants; it cannot reach beyond the sandbox boundary.

## The Move

The CodeAct pattern replaces a large tool catalog with a single code-execution tool. The agent writes Python (or JavaScript) to accomplish tasks, sees the result, revises, and continues until the goal is met.

**The minimal tool surface:**
- One tool: `exec_python(code: str)` — takes Python code, executes it, returns stdout/stderr/traced output
- Optional guardrails: pre-defined imports and packages available in the sandbox; explicit blocklist for `os.system`, `subprocess`, `eval`, `exec` on dangerous paths
- No tool descriptions, no tool schemas, no parameter validation for domain-specific operations

**What the agent gets that it didn't with tools:**
- The full expressiveness of Python's stdlib — arithmetic, string manipulation, file I/O, HTTP, JSON, datetime, regex, collections
- Composable operations — chain `df.groupby().agg().plot()` instead of calling three separate tools
- Typed intermediate state — variables persist in the execution session
- Direct feedback — a traceback tells the agent exactly where it went wrong, line by line

**What the human provides:**
- A curated environment: pre-installed packages (pandas, matplotlib, requests, numpy) and a sandbox with appropriate permissions
- A task prompt that describes the goal, not the method
- Execution limits: max output tokens, max runtime, max memory

**Multi-agent variant:** Letta's benchmarks showed a plain filesystem scores 74% on memory tasks, beating specialized vector-store memory libraries. CodeAct agents can interact with external services via API calls inside the code — no need to wire up individual tool integrations for each service.

**CodeAgent vs ToolCallingAgent:** Hugging Face's smolagents implements both. `CodeAgent` writes Python code as actions (CodeAct); `ToolCallingAgent` uses traditional JSON tool calls. The trade-off: CodeAct agents are more expressive and self-composing, but require a safe execution environment. ToolCalling agents are more predictable but require exhaustive tool definitions.

## Evidence

- **Research paper:** "Executable Code Actions Elicit Better LLM Agents" (ICML 2024) — CodeAct outperforms ReAct-style fine-grained tool calling by up to 20% higher success rate on API-Bank and a new benchmark, using a unified Python execution action space instead of per-task tools — [https://arxiv.org/html/2402.01030v4](https://arxiv.org/html/2402.01030v4)
- **Production implementation:** Manus AI agent architecture — operates as a wrapper around Claude 3.5/3.7 and Qwen with full cloud-based virtual computing environment. Uses CodeAct as its core action mechanism: agents write executable Python to perform complex autonomous operations, with browser access, shell commands, and code execution all composable from code — [https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf](https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf)
- **Framework:** Hugging Face smolagents — 28,816 stars, core `agents.py` under 1,000 lines. Implements `CodeAgent` as first-class citizen with `<turn>`, `<code>`, `<return>` tags; variables persist across code cells; multi-agent hierarchies; MCP server and Hub tool imports — [https://github.com/huggingface/smolagents](https://github.com/huggingface/smolagents)
- **Survey finding:** December 2025 survey paper on agentic memory — filesystem-based agents score 74% on memory tasks vs specialized vector-store libraries, suggesting simpler composable primitives outperform complex tool-catalog approaches — [https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)
- **Engineering post:** Anthropic's multi-agent research system uses agents that write code to interact with tools — each subagent operates autonomously in a loop, executing code to call web search, Google Workspace, and MCP integrations — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

## Gotchas

- **Sandbox escape is a real risk.** Agent-written code can attempt `import os; os.system('rm -rf /')`. You need either a hardened sandbox (E2B, Cage, or container with seccomp + seccomp-filter) or a strict pre-execution guard that intercepts dangerous calls before they reach the interpreter. The smolagents README explicitly notes: "It applies some restrictions but can be bypassed and must not be used as a security boundary."
- **Long-running code burns budget with no visibility.** If the agent writes a tight loop, you get no intermediate feedback until the timeout fires. Set a per-turn execution limit and instrument the environment to stream output back incrementally.
- **Not all LLMs handle code generation equally.** CodeAct's benefits depend heavily on the model's ability to write correct Python. A model that hallucinates function names or misindents will spend its execution budget on tracebacks. Test your specific model with code generation before committing to CodeAct.
- **Debugging agent-generated code is harder than debugging agent tool calls.** A tool call either succeeds or fails with a structured error. Python code can produce subtly wrong results — a dataframe operation that silently returns the wrong aggregation, a loop that almost-but-doesn't-converge. You need end-to-end output validation even when execution doesn't error.
- **The sandbox environment becomes part of your interface contract.** Pin your base image, pre-installed packages, and resource limits. When you upgrade the environment, the agent's code may break silently because `requests` changed behavior or `pandas` renamed a method. Treat the sandbox like a versioned API.
