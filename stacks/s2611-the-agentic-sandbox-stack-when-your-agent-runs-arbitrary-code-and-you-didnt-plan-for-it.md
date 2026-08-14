# S-2611 · The Agentic Sandbox Stack — When Your Agent Runs Arbitrary Code and You Didn't Plan for It

Your agent just wrote and executed 200 lines of Python against your production database. It was working fine in testing. In production, a hallucinated import statement tried to pull in a typosquatted package, the agent's tool-following drifted, and now there is an unvetted script running inside your network with your credentials. This is what "agent autonomy" looks like when sandboxing is an afterthought.

## Forces

- **Gartner estimates 30% of enterprises will have deployed AI agents capable of autonomous code execution by end of 2026** — up from less than 3% in 2024. That is a compressed, industry-wide security and infrastructure challenge with no established playbook.
- **Traditional container isolation was designed for code you control.** Docker shares the host kernel. That was fine when containers ran vetted builds from trusted engineers. AI agents generate new code at runtime, often in unexpected ways, with no peer review.
- **The blast radius of a sandbox failure is not a bad response — it is an unauthorized action.** Hallucinated tool parameters, prompt injection, emergent behavior from multi-agent systems: these can produce code that individual components would never have generated alone.
- **Permission fatigue creates its own danger.** Constant per-action approval prompts (read file Y/N, execute command Y/N) cause users to stop paying attention. Anthropic measured that sandboxing reduces permission prompts by 84% — paradoxically making agents both more useful and safer.

## The Move

The sandbox is not a nice-to-have around the agent. It is the foundational security boundary that makes autonomous code execution survivable in production.

**Choose your isolation primitive by risk tolerance:**

| Primitive | Cold Start | Security | Best For |
|-----------|-----------|----------|----------|
| Hardened containers | <90ms | Moderate | Low-risk internal tools, read-only operations |
| gVisor (user-space kernel) | Container startup | Strong | General-purpose agent workloads |
| MicroVMs | ~150–200ms | Strongest | High-privilege operations, external network access |

**Define boundaries before autonomy:**
- Set filesystem isolation first — which directories can the agent read/write, never prompt per file.
- Set network boundaries second — which services and external endpoints can it reach.
- Define scope before launching, not during execution.

**Code execution pattern (Anthropic's MCP approach):**
- Agents write code that calls tools, rather than making individual tool calls directly.
- This amortizes token cost and reduces the number of decisions the model makes at runtime.
- Tool definitions stay in the MCP server; intermediate results flow through a code execution buffer.
- Agents scale better because fewer per-step decisions mean fewer opportunities for drift.

**Defense-in-depth for the AI attack surface:**
- Intercept Linux syscalls (gVisor intercepts ~200+) rather than relying on model behavior.
- Resource limits: CPU time, memory, network egress, filesystem writes.
- No credentials in the sandbox environment — agents get scoped tokens.
- Audit every execution: log inputs, outputs, duration, and termination reason.
- Human-in-the-loop at credential boundaries — not for every action.

**Tool design for agents (Anthropic's cookbook):**
- Write tools as contracts between deterministic systems and non-deterministic agents — tools must be designed for agents, not other developers.
- Tools that are most ergonomic for agents end up being surprisingly intuitive for humans too.
- Test tools with realistic evaluation tasks — dozens of multi-step calls, not toy examples.
- Use the agent to evaluate and improve its own tools: run evaluation tasks, analyze failures, regenerate.

## Evidence

- **Anthropic Engineering Blog:** Claude Code sandboxing reduces permission prompts by 84% while increasing safety. Uses two isolation boundaries: filesystem and network. Filesystem isolation prevents prompt-injected paths; network isolation limits lateral movement. — [anthropic.com/engineering/claude-code-sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- **Zylos Research:** 2026 landscape converges on three isolation primitives. MicroVMs offer ~5MB RAM overhead with the strongest security; gVisor intercepts 200+ Linux syscalls in user space; hardened containers start in <90ms. AI agents produce emergent code that no individual component would generate — this requires isolation that assumes adversarial intent from the generated code itself. — [zylos.ai/zh/research/2026-02-21-ai-agent-sandbox-execution-isolation](https://zylos.ai/zh/research/2026-02-21-ai-agent-sandbox-execution-isolation)
- **Martin Fowler (Korny Sietsma, Oct 2025):** The fundamental security weakness of LLMs is that there is no rigorous way to separate instructions from data. Containers should be used for sandboxing LLM applications. Simons Willison's "Lethal Trifecta" — sensitive data + model access + tool use — is the exact configuration of most production agentic systems. — [martinfowler.com/articles/agentic-ai-security.html](https://martinfowler.com/articles/agentic-ai-security.html)
- **Anthropic Engineering Blog:** Tool design is a distinct discipline from API design. Agents respond to tool descriptions as instructions, not documentation. Anthropic uses Claude to optimize its own Slack MCP server, generating evaluation tasks and improving tool accuracy from a 53% baseline to 97%+ on held-out test sets. — [anthropic.com/engineering/writing-tools-for-agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **Engipulse:** Gartner projects 30% enterprise deployment of code-execution agents by end of 2026. AI-specific attack vectors include prompt injection, hallucinated dependencies (typosquatted packages), and emergent behaviors. Azure Container Apps Sandboxes represents a major cloud-native step toward hardware-isolated sandboxing. — [engipulse.com/cloud-devops/sandboxing-ai-agent-code-in-production-a-devops-architecture-guide-for-2026](https://engipulse.com/cloud-devops/sandboxing-ai-agent-code-in-production-a-devops-architecture-guide-for-2026)
- **MMC Ventures (Nov 2025):** Surveyed 30+ European agentic AI founders. Most blockers are organizational (workflow integration, employee trust, data privacy), but data privacy is directly addressable through sandbox isolation — production agents that can operate on sensitive data without credentials in the sandbox environment sidestep the privacy concern rather than solving it upstream. — [mmc.vc/research/state-of-agentic-ai-founders-edition/](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)

## Gotchas

- **Don't put credentials in the sandbox.** Give agents scoped, short-lived tokens. If the sandbox is compromised, the blast radius should not include production credentials.
- **MicroVMs have latency costs.** The 150–200ms cold start matters for interactive agents. Profile your actual latency budget before choosing strongest isolation.
- **Sandbox without observability is theater.** Log every execution with inputs, outputs, and termination reason. A sandbox that nobody watches is a black box failure waiting to become a news story.
- **Tool descriptions are not API docs.** Anthropic's data: a Slack MCP server went from 53% to 97%+ tool-call accuracy through description optimization alone. The agent learns from descriptions, not from the system prompt.
- **Don't confuse permission fatigue with trust.** Cutting prompts because users ignore them is not the same as the agent being trustworthy. Sandbox first, then reduce prompts as a reward for having a defensible boundary.
