# S-2751 · The Agent Tool Shrine Stack — When Your Agent Can't Do Anything Without the Right Instruments

Your agent is trained on petabytes but helpless against a login form. It can reason about code but can't edit a file. It can draft an email but can't send one. You've built the brain but forgotten the hands. What tools — and how you wire them — determines whether your agent is a sophisticated autocomplete or an actual actor in the world.

## Forces

- **Browser automation is flexible but fragile.** A browser gives agents reach into any web UI, including legacy apps without APIs. But DOM parsing is brittle, CSS changes break selectors, and residential proxies + credential management add operational overhead that dwarfs the agent loop itself.
- **Terminal + filesystem agents are reliable but limited.** The StarShell paper (ServiceNow/Mila, April 2026) argues that API-driven terminal agents outperform browser agents on enterprise tasks where programmatic interfaces exist — because the API contract is stable, not the DOM. But 90% of the web has no API.
- **The agent loop is commoditized; the tool layer is where teams burn months.** Frontier models handle multi-step web reasoning. Cloud Chromium is a mature product. What's hard is credential management, session replay, scheduling, versioning, and the orchestration between tools. The loop is 20% of the problem.
- **MCP is real infrastructure now but introduces its own attack surface.** The Model Context Protocol has exploded from a dozen reference servers in late 2024 to hundreds in community registries by 2026. But MCP's STDIO transport runs local processes with full host access, and the HTTP+SSE transport uses bearer tokens with no standard authentication layer. Teams are building MCP security tooling specifically because the threat model wasn't designed in.
- **Browser-based tools token-burn compared to API calls.** Frigade's Show HN post (August 2026) explicitly cites browser-based "computer use" as "too brittle, slow, and burns a lot of tokens." Auto-generated MCP servers from reverse-engineered API calls offer a middle path: the reliability of structured APIs with the breadth of browser automation.

## The Move

Choose your tool paradigm based on interface availability, not convenience:

- **If a stable API exists → terminal/code-exec agent.** Give the agent a shell and a filesystem. Let it `curl`, `python`, or call SDKs directly. This is what the StarShell paper calls "terminal agents" — they externalize context into the environment through a REPL-style loop, interact with platform APIs directly, and avoid the brittleness of DOM parsing. Works for Slack, GitHub, Salesforce, internal microservices.

- **If no API exists but the app is browser-based → reverse-engineer the API calls first, then give the agent MCP.** This is Frigade's insight: watch the authenticated web app call its own APIs, auto-generate an MCP server from the traffic, and give that to the agent instead of a browser harness. This turns "no API" into "rich tool" with 85% success rate improvements over DOM-based approaches.

- **If the task genuinely requires visual understanding → browser with selective vision, not full computer use.** Use Playwright MCP servers or Browser Tools SDK for selective accessibility tree snapshots. Don't give the agent raw screenshots unless the UI is graphical (charts, PDFs, image-based CAPTCHAs).

- **For production browser agents, add the operational layer from day one:** credential manager (not hardcoded secrets), session replay (for debugging failed runs), scheduling, and per-tool observability. The agent library handles the loop; you build the operations plane.

- **For MCP servers: scope the permission model tightly.** MCP Security Suite (Show HN, 2026) specifically flags credential exfiltration and tool poisoning as risks. Treat MCP servers like you treat npm packages — audit permissions, sandbox the transport, and log every tool invocation.

- **Give agents a working scratchpad, not just tool results.** The agent's session scratchpad (working memory across turns) should persist state that tools produce but that fits nowhere in the tool schema. File writes, intermediate JSON blobs, URLs of created resources — surface these back to the agent so it can chain tools coherently.

## Evidence

- **Research paper:** Terminal Agents Suffice for Enterprise Automation — Bechard et al. (ServiceNow, Mila, Université de Montréal, arXiv:2604.00073, April 2026) — documents StarShell, a terminal-based coding agent that outperforms GUI-driven and tool-augmented agents on enterprise automation tasks by operating directly through platform APIs and a filesystem. — [arXiv:2604.00073v2](https://arxiv.org/html/2604.00073v2)

- **Show HN post:** Reverse-Engineering Web Apps into Agent Tools — Frigade (HN, August 2026, ~33 days ago) — demonstrates auto-generating MCP servers from observed API traffic in authenticated web apps, achieving significantly higher reliability than browser computer use, with live demos for Jira, Spotify, Hacker News, and Airbnb. — [HN #48847834](https://news.ycombinator.com/item?id=48847834)

- **Engineering blog:** The Browser Automation Stack in 2026 — Notte.cc (March 2026) — maps the landscape: agent libraries (Browser Use, Playwright MCP, Stealth), cloud browsers (Residential proxies, Browserbase), and the operational layer that production teams actually need. Key finding: "The agent loop is the easy part now. The operational layer is where teams still burn months." — [notte.cc/blog](https://www.notte.cc/blog/browser-agent-stack-2026)

## Gotchas

- **Adding more tools doesn't make agents smarter — it makes them noisier.** Each tool is a choice the model must consider. A 50-tool agent has worse tool selection than a 5-tool agent on the same task. Prune aggressively; consolidate related tools into single-purpose wrappers.
- **Browser agents fail silently on captchas, rate limits, and DOM mutations.** Build explicit failure modes: detect these conditions, surface them to the agent with a strategy hint, and log for post-mortem. Don't let the agent retry a broken selector 20 times.
- **MCP server version drift breaks agents.** When the upstream API changes, the MCP server's tool schema changes, and the agent's tool-calling assumptions break. Pin versions and test schema compatibility in CI.
- **Credential management for browser agents is an unsolved ops problem.** Many teams hardcode credentials or use weak session persistence. This is the #1 attack surface for production browser agents and the reason enterprise teams prefer API-first approaches.
