# S-1625 · The Code-as-Tool-Definition Stack — When Your Agent Spends More Tokens Describing Its Tools Than Using Them

You connect your agent to 30 MCP tools. Before it can answer a single user question, it has already consumed 40,000 tokens just loading tool definitions. A two-hour meeting transcript through the context window adds another 50,000. The agent wasn't slow because the model was struggling — it was slow because you were paying to describe work instead of doing it. This is the token overhead tax: **the abstraction that connects agents to tools is more expensive than the work those tools perform**.

## Forces

- **MCP's lazy adoption created a hungry pattern.** Model Context Protocol (launched by Anthropic, November 2024) solved the integration fragmentation problem — implement once, connect everywhere. But the dominant client implementation loads all tool definitions upfront, so connecting 100 MCP servers means your agent starts every session processing a tool catalog longer than most prompts.
- **Tool result streaming destroys context budgets.** When an agent processes a 2-hour meeting transcript or a large document, the intermediate result flows through the model. Each step compounds the token cost. A workflow that should cost 2,000 tokens costs 150,000.
- **The model already knows how to write code.** LLMs are code generators. Giving an agent a code execution tool (Python sandbox, Node runtime) lets it write programs that call MCP servers directly — replacing dozens of pre-loaded tool definitions with one runtime that the agent programs as needed.
- **Token cost and latency are the same problem.** More tokens means more API cost and more round-trip latency. Cutting token overhead from tool loading and result streaming simultaneously improves both.

## The move

Anthropic published the canonical pattern in November 2025. The core idea: **stop loading tool definitions into context; give the agent a code execution environment that interacts with MCP servers programmatically**.

**The three techniques:**

- **Lazy tool discovery.** Instead of passing all MCP tool definitions upfront, give the agent a `list_tools()` function it can call on-demand. The agent discovers and uses only the tools it actually needs, when it needs them. One GitHub project (MCPGateway) calls this "progressive tool discovery" with 15 layers of token optimization.
- **Results stay in the execution environment.** Intermediate outputs (transcripts, file contents, API responses) stay in the sandbox. The agent receives summaries or targeted extracts, not raw data. The model sees a result, not a dump.
- **Complex logic in one agent step.** Rather than a 10-step orchestration where each tool call passes state through the model, the agent writes a single program that sequences tool calls in the sandbox. One model round-trip instead of ten.

**The token math (Anthropic's own numbers):** A tool-heavy workflow dropped from ~150,000 tokens to ~2,000 tokens — a 98.7% reduction. Third-party tests on the pattern show 78–99% input token reductions across different agent configurations.

## Evidence

- **Anthropic Engineering Blog:** "Code execution with MCP: building more efficient agents" (Nov 4, 2025) — the canonical source. Describes lazy loading, intermediate results staying in the execution environment, and complex logic batching in one step. Claims up to 98.7% token reduction on a workflow that previously consumed 150K tokens.
  — https://www.anthropic.com/engineering/code-execution-with-mcp

- **AI for Anything:** "Claude MCP Code Execution: Cut Agent Token Usage by 98% (Anthropic Pattern)" (June 8, 2026) — third-party walkthrough validating the pattern with step-by-step implementation guidance.
  — https://aiforanything.io/blog/claude-mcp-code-execution-token-efficient-agents-2026

- **GitHub:** MCPGateway project — open-source MCP gateway with progressive tool discovery, 15 token optimization layers, and multi-server aggregation. Implements the lazy loading and discovery pattern described in Anthropic's post.
  — https://github.com/abdullah1854/MCPGateway

- **GitHub:** `kkito/token-saver-mcp2skill` — replaces MCP tool definitions with CLI + Skill pattern, generating reusable skill definitions from MCP server specs to avoid passing full tool schemas in every call.
  — https://github.com/kkito/token-saver-mcp2skill

## Gotchas

- **Code execution is a privilege, not a default.** You need a sandboxed runtime (Docker, WebAssembly, ephemeral cloud function) that can execute untrusted agent-generated code safely. Without isolation, you've given the agent arbitrary code execution on your infrastructure.
- **The agent needs to be a good programmer.** This pattern only works when the model writes correct code that calls the right APIs in the right order. A model that hallucinates API calls or writes buggy Python will produce wrong results faster and cheaper — which is not the win it sounds like.
- **Tool caching is a local optimum.** OpenAI Agents SDK and other frameworks support `cache_tools_list=True` on MCP servers, which caches tool lists across calls. This helps with remote MCP servers that have high latency, but it doesn't solve the underlying token overhead from passing definitions in context. The code execution pattern addresses a different layer.
- **Not every workflow benefits.** Simple, linear tasks (one tool, one call) cost less in tokens than the overhead of setting up a code execution environment. The pattern shines for agents with 10+ tool calls, complex state management, or large intermediate data — not for a one-shot "fetch this URL" operation.
