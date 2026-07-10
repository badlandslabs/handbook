# S-907 · The Tool Ecosystem Stack — When Your Agent Can Call Anything But Shouldn't

Your agent works beautifully in the demo. You gave it six tools, all well-documented, all returning clean structured output. Then you connect to MCP and suddenly it has access to 12,000 servers maintained by strangers. One of them exfiltrates credentials. Another poisons your tool descriptions at runtime. A third was written six months ago and hasn't been updated since a critical CVE landed. The agent can't tell the difference between your carefully curated toolset and a supply chain attack wearing a JSON-RPC wrapper.

This is the tool ecosystem problem: MCP made tool integration trivial, and triviality is now the attack surface.

## Forces

- **MCP made "give an agent a tool" a one-line config change.** The ecosystem exploded to 12,000+ servers in under two years — but ease of connection does not mean ease of vetting.
- **Tool poisoning doesn't require calling a bad tool.** An attacker modifies the tool description the server returns — the agent calls the right name, but with the wrong parameters, trusting poisoned schema metadata.
- **Code execution tools make every untrusted-input rule apply.** A code-generation agent's output is untrusted input. Running it without isolation puts host credentials, network access, and filesystem in the blast radius.
- **Browser automation agents face stale-state failures that look like model failures.** The model doesn't misunderstand the page — it's acting on a screenshot from three steps ago.
- **Security tooling hasn't caught up with deployment speed.** 30+ CVEs were filed against MCP implementations in a 60-day window. Organizations are connecting MCP servers without scanning them.

## The move

The move is to build a tool integration stack with the same rigor you'd apply to a third-party API — treating MCP servers as untrusted supply chain until proven otherwise, and scoping code execution to isolated sandboxes.

**For MCP tool integration:**
- Run `mcp-scan` (or equivalent) against every MCP server before connecting it. Treat this like `npm audit` for your agent's toolchain.
- Pin MCP server versions explicitly. Auto-update is a silent supply chain change.
- Enforce least-privilege tool access — if the agent only needs to read a database, don't give it write tools.
- Implement tool-description monitoring: if a server starts returning different schema metadata between calls, that's a poisoning signal.
- Use the OWASP MCP Top 10 as your threat taxonomy. The ten categories (MCP01–MCP10:2025) include model misbinding, context spoofing, intent flow subversion, and covert channel abuse — read the actual definitions at owasp.org/www-project-mcp-top-10.

**For code execution tools:**
- Treat all LLM-generated code as untrusted input. The AgentList analysis documents a real 2025 incident where `os.system("curl ...")` inside a code-gen agent exfiltrated MinIO credentials from a container.
- Default to sandboxed execution. Docker with `privileged: true` and `/var/run/docker.sock` mounts give the agent root on the host — they are not acceptable defaults.
- SWE-ReX (swe-agent's execution framework) provides mass-parallel sandboxed execution via Docker, AWS Fargate, or Modal — used in production for automated code review and SWE-bench agent tasks.
- Choose the isolation level that matches the risk: process-level `setrlimit` for low-risk tasks, full microVMs (Firecracker) for untrusted multi-tenant workloads, containerized execution for everything in between.

**For browser automation tools:**
- Prefer freeze-then-capture architectures (Agent Browser Protocol, agent-browser from Vercel Labs) over polling-based screenshot approaches. After each agent action, freeze JS execution, capture the resulting DOM state, and return it — eliminating stale-state failures that cause agents to click on elements that have moved.
- Use accessibility-tree output over pixel screenshots for agent context efficiency. The agent reads structured DOM data, not image blobs — fewer tokens, more precision.
- Log every action-and-state pair for replay debugging. Browser agent failures are hard to reproduce; recording the full freeze-capture cycle enables it.

**For tool schema design:**
- Keep tool descriptions specific and deterministic. Vague descriptions ("search the web for anything") give the agent too much latitude and increase poisoning surface.
- Parameterize everything. Avoid shell execution inside tools; use parameterized command APIs.
- Return typed, structured output. The agent should be able to validate tool responses against a schema before acting on them.

## Evidence

- **NSA Cybersecurity Report (May 2026):** Documents that MCP's rapid proliferation has outpaced its security model. The protocol reverses the client-server interaction pattern — servers can query and execute actions for clients — creating attack paths that weren't well-traced until public research released vulnerable implementations. — [NSA CSI_MCP_SECURITY.pdf](https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf)

- **OWASP MCP Top 10 + Cycode analysis (2026):** 30+ CVEs filed against MCP implementations in 60 days (Jan–Feb 2026). Palo Alto Unit 42 measured a 78.3% attack success rate when five MCP servers connect to a single agent. 84.2% tool poisoning success rate with auto-approval enabled. 34% of 2,614 MCP implementations expose APIs susceptible to command injection; 67% expose code injection APIs. — [owasp.org/www-project-mcp-top-10](https://owasp.org/www-project-mcp-top-10/) / [Cycode OWASP MCP Top 10](https://cycode.com/blog/owasp-mcp-top-10/)

- **Paperclipped.de CVE deep-dive (2026):** Three CVEs in Anthropic's official Git MCP server: CVE-2025-68143 (CVSS 8.8) allowed writing to `/etc/cron.d/` via arbitrary filesystem path in `git_init`; CVE-2025-68145 bypassed repository boundary enforcement; CVE-2025-68144 enabled argument injection via `--config` flag. The `git_init` tool was removed entirely in the fix. — [MCP Security Vulnerabilities & Tool Poisoning Explained](https://www.paperclipped.de/en/blog/mcp-security-vulnerabilities-tool-poisoning)

- **SWE-ReX GitHub (swe-agent, MIT license):** Sandboxed code execution framework used by SWE-agent for automated code repair tasks. Supports Docker, AWS Fargate, and Modal backends with configurable resource limits and parallel execution. — [github.com/swe-agent/SWE-ReX](https://github.com/swe-agent/SWE-ReX)

- **Agent Browser Protocol Show HN (2025):** Open-source Chromium fork with freeze-then-capture architecture. Freezes JS + rendering after each agent action, compiles notable events (navigation, file pickers, permission prompts, alerts), returns fresh screenshot + structured state. Addresses the root cause of browser-agent failures: stale state, not model misunderstanding. — [news.ycombinator.com/item?id=47336171](https://news.ycombinator.com/item?id=47336171)

- **AgentList Sandbox Decision Matrix (Jun 2026):** Documents the March 2025 production incident where an LLM-generated `curl | bash` inside a code-generation agent exfiltrated container credentials. Compares five sandbox technologies (Docker, E2B, Modal, Firecracker, gVisor) on latency, security, and operational cost. — [AgentList: Sandboxing Code Execution in AI Agents](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice)

- **Zuplo State of MCP (2025–2026):** 12,000+ MCP servers across directories, registries, and indexes. PulseMCP is the largest directory. The protocol was donated to the Linux Foundation's Agentic AI Foundation (AAIF) in late 2025. Enterprise adoption is accelerating as organizations recognize MCP as the standard agent tool-integration layer. — [ooty.io/blog/state-of-mcp-ecosystem-2026](https://ooty.io/blog/state-of-mcp-ecosystem-2026)

## Gotchas

- **Auto-approval is the tool poisoning enabler.** If your agent approves tool calls without human review, tool poisoning succeeds 84% of the time. Require approval for tools that touch external networks, filesystems, or credential stores.
- **MCP server version pinning is not optional.** Unlike npm packages, MCP servers don't have a canonical registry with semantic versioning enforcement. A server that was secure last month may have a CVE today.
- **Docker is not a sandbox.** Default Docker isolation gives the container network access and (with most Compose setups) shares the host Docker socket. A privileged container or a mounted socket is equivalent to giving the agent root on the host.
- **The "freeze-then-capture" approach is architecturally different from screenshot-and-click.** Most browser automation libraries take periodic screenshots and let the agent decide. ABP-style freezing eliminates the race condition entirely — but requires a Chromium fork, not a Playwright wrapper.
- **Tool description poisoning doesn't call a different tool — it corrupts the right one.** The agent calls `send_email`, but the poisoned description changes the `to` parameter to an attacker-controlled address. The call succeeds; the damage is done. You need schema validation at the agent's tool-calling layer, not just at the MCP server.
