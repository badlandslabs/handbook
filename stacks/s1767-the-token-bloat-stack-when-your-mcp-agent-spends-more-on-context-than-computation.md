# S-1767 · The Token Bloat Stack — When Your MCP Agent Spends More on Context Than Computation

When you connect an AI agent to a Model Context Protocol server and watch it burn 15,000 input tokens to call a single tool that returns 3 numbers, you have a token bloat problem. The agent's context window — the most expensive real estate in your system — is being consumed by tool definitions, not reasoning. The agent works, but the cost is 4–5x higher than it needs to be. This is not a model problem. It is an architectural one: the naive approach to MCP tool definition passes too much metadata through the context window.

## Forces

- **MCP's native pattern loads everything upfront.** Most MCP clients register all available tools at initialization and include their full definitions in every model call. With dozens of servers and hundreds of tools, this alone can consume 10,000+ tokens before the agent says a word.
- **Tool results are also passed through context.** Raw tool outputs — database query results, file contents, API responses — flow back through the model as input tokens. A single file read can add 5,000 tokens to the next call.
- **Scaling multiplies the problem.** More tools, more servers, more concurrent agents all compound the token cost linearly. The demo that worked with 5 tools becomes expensive with 50.
- **Reducing tokens feels like reducing capability.** The obvious fix — fewer tools — feels like a regression. The actual solution is architectural, not a tool count tradeoff.

## The Move

The MCP code-execution pattern (published by Anthropic, November 2025) rethinks how agents interact with tools. Instead of passing tool definitions and results through the model's context, the agent writes executable code that calls tools directly, and intermediate results stay in the code layer — never touching the model's memory.

- **Agents write code, not tool calls.** The model generates Python that invokes MCP tools, receives results into local variables, and continues. Only the final answer returns to the model.
- **Tool discovery happens at runtime, not registration time.** Instead of 200 tool definitions in context, the agent writes code that dynamically finds and calls the specific tool it needs for this specific task.
- **Intermediate data lives in code, not prompts.** A pipeline that reads a file, queries a database, and formats output keeps all three intermediate results as Python variables — zero additional tokens.
- **Context only carries intent and answer.** The model's context window carries the user's request and the final response. Tool definitions, schemas, and raw data stay external.
- **Verification: measure input token reduction.** The pattern's benchmark shows 78.5% fewer input tokens with identical success rates. Latency increases ~7% — a worthwhile trade at scale.

## Evidence

- **Engineering blog (Anthropic):** Code execution with MCP reduces input tokens from ~15,400 to ~3,300 per task while maintaining 100% success rate. Published November 2025. — https://www.anthropic.com/engineering/code-execution-with-mcp
- **Independent benchmark (AIMultiple):** Tested regular MCP vs. code-execution MCP across multiple tasks. Confirmed 78.5% input token reduction, 77.4% total token reduction, +7% latency. — https://aimultiple.com/code-execution-with-mcp
- **ArXiv empirical study (Queen's University):** Analyzed 1,899 MCP servers. Found MCP ecosystem growing rapidly (8M+ SDK downloads/week), but 7.2% contain vulnerabilities, 66% have code smells, and 5.5% show MCP-specific tool poisoning risks — independent evidence that the naive direct-call pattern introduces attack surface. — https://arxiv.org/html/2506.13538v2

## Gotchas

- **The code-execution pattern requires a sandboxed execution environment.** You cannot emit and run arbitrary code unless your agent runtime supports it. Claude Code, OpenAI Agents SDK, and cloud-based agent platforms support this; a basic LangChain chain does not.
- **Debugging becomes two layers.** Tool behavior lives in the generated code, not the model's visible reasoning. You need observability into both the LLM's decision logic and the code it emitted.
- **Security surfaces shift, not shrink.** Moving tool calls into code doesn't eliminate injection risk — it moves it into the code-generation step. A poisoned tool definition can now cause the agent to emit malicious code, not just return bad data. Sandboxing remains essential.
