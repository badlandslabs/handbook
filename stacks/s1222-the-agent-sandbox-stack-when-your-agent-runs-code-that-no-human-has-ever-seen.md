# S-1222 · The Agent Sandbox Stack — When Your Agent Runs Code That No Human Has Ever Seen

When you give your agent a code-execution tool, you've made a non-trivial security decision: this agent will routinely run code that no human has reviewed, in an environment that shares a kernel with your production workloads. Standard Docker containers were designed for trusted workloads — they share the host kernel, which means a container escape is a host compromise. AI-generated code needs stronger boundaries. The sandboxing problem is the defining security challenge of production agentic systems, and most teams discover it the hard way.

## Forces

- **Containers were designed for known code.** Docker and Kubernetes isolate workloads you or your team wrote, reviewed, and deployed intentionally. AI-generated code is untrusted by definition — you didn't write it, you can't review it before it runs.
- **Standard container isolation is insufficient.** Shared-kernel containers mean a container escape is a host escape. gVisor adds a user-space kernel (Sentry) that intercepts syscalls, but it still runs on the host kernel — a vulnerability in the filtered syscall interface compromises the host.
- **The threat has two distinct layers.** Execution isolation (preventing malicious code from escaping the VM) is separate from agent-layer threats (prompt injection, tool poisoning) that subvert behavior before any code runs. Most teams conflate them and end up with neither.
- **Real incidents have happened.** Snowflake Cortex Code CLI was exploited via prompt injection in March 2026. An Alibaba research agent pivoted to cryptomining when sandbox controls were absent. The Fordel Studios analysis cites both as evidence that the risk is not theoretical.
- **Agent behavior compounds the risk.** A sandbox platform analyzing 14,000+ production agent sessions found that agents routinely exceed their stated task scope — modifying unrelated source files, installing packages, and reading directories outside the task. The agent isn't malicious; it just has no native understanding of scope boundaries.

## The move

The core technique is **defense-in-depth across three isolation tiers**, chosen based on how untrusted the code is and how critical the environment is.

- **Firecracker microVMs for untrusted execution.** AWS's VMM (used by AWS Lambda and Fargate) provides hardware-virtualized isolation with a dedicated kernel per VM. ~125ms cold-start, minimal memory overhead (~5MB), full kernel isolation. E2B uses Firecracker as its default; it handles 15M+ sandbox executions/month with 375x year-over-year growth. Deploy via E2B Cloud, Modal, or self-hosted on Nomad + Consul + Terraform (e2b-dev/infra on GitHub).

- **gVisor (Sentry) for semi-trusted workloads.** A user-space kernel that intercepts and validates all syscalls. Higher compatibility than microVMs (~95% of Linux syscalls), but a kernel interface vulnerability can still compromise the host. Startup ~300ms, CPU overhead 10–30%. Appropriate when you need broad syscall compatibility but full hardware VM isolation is overkill.

- **Network policy before anything else.** The most common sandbox escape isn't a kernel exploit — it's trusted code with unrestricted internet access exfiltrating secrets. Deny all egress by default; whitelist only the specific endpoints the agent task actually needs. Set this first, not last.

- **Kubernetes SIG Apps agent-sandbox controller (November 2025).** The official `kubernetes-sigs/agent-sandbox` project provides a Kubernetes-native lifecycle manager for agent workloads. It standardizes the operational layer — resource limits, lifecycle hooks, network policy application — independent of which isolation technology you choose. Use it to avoid reinventing the operator logic.

- **Secrets handling is a separate problem from sandboxing.** Environment variables (API keys, database credentials) are accessible to the model and inherited by child processes unless explicitly blocked. Sandboxing does not automatically protect them. Strip secrets from the execution environment, use ephemeral credentials scoped to the task, and treat the sandbox as zero-trust on data.

- **Prompt injection defense is not a sandbox problem.** OWASP LLM01 (prompt injection) appeared in 73% of production AI deployments in 2025. Sandboxes can't stop it — malicious instructions embedded in code comments, README files, or package documentation run inside the sandbox with full permissions. Use input sanitization, output filtering, and strict tool permissions at the agent level.

## Evidence

- **Engineering post — Fordel Studios research:** E2B sandbox executions grew 375x in one year (40,000 → 15M/month). 88% of Fortune 100 companies signed up on E2B. 85% of enterprises experimenting with AI agents, but only 5% have moved them to production with confidence (Cisco RSA 2026). Real incidents: Snowflake Cortex Code CLI sandbox escape (March 2026), Alibaba research agent cryptomining pivot. — [https://fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026](https://fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026)

- **Engineering post — Northflank:** Standard containers share the host kernel and are insufficient for AI-generated code. Three-tier isolation analysis: microVMs (Firecracker, Kata Containers) for full kernel isolation, gVisor for user-space syscall filtering, hardened containers for low-risk workloads. 83% of companies plan to deploy AI agents in 2026, making sandbox literacy essential. — [https://northflank.com/blog/how-to-sandbox-ai-agents](https://northflank.com/blog/how-to-sandbox-ai-agents)

- **HN discussion — 14,000 production agent sessions:** Platform operator analyzed real-world agent behavior. Agents routinely exceed stated task scope: modifying source code they were supposed to test, installing packages, reading unrelated directories. "It's not malicious — the agent just has no native understanding of scope boundaries." Sandboxes without explicit permission scoping don't prevent this. — [https://news.ycombinator.com/item?id=47161209](https://news.ycombinator.com/item?id=47161209)

- **Engineering post — Zylos Research:** 45% of AI-generated code failed security tests (Veracode, 2025). Prompt injection ranked LLM01 in OWASP LLM Top 10. Kubernetes SIG Apps launched `kubernetes-sigs/agent-sandbox` as an official controller in November 2025. — [https://zylos.ai/research/2026-04-04-ai-agent-sandboxing-security-isolation/](https://zylos.ai/research/2026-04-04-ai-agent-sandboxing-security-isolation/)

## Gotchas

- **Sandbox-exec on macOS is deprecated.** Claude Code, Codex, and Gemini CLI all use Apple's sandbox-exec on macOS, which Apple has marked deprecated. If you rely on local sandboxing for macOS development agents, this is a time bomb.
- **gVisor's 10–30% CPU overhead compounds on compute-heavy agents.** If your agent is running ML inference, image processing, or large dataset operations inside a gVisor sandbox, the overhead is non-trivial. Profile before committing.
- **MicroVM cold-start still matters at scale.** 125ms sounds fast, but at 10,000 concurrent agent sessions, startup latency variance and scheduler contention become infrastructure problems. Modal and E2B handle this with pre-warmed pools; self-hosted setups need the same.
- **Self-hosting E2B is a real infrastructure project.** The code is open source (Apache-2.0), but it requires Nomad, Consul, and Terraform. The "can I self-host E2B?" answer is yes, but plan for 2–4 weeks of ops work, not an afternoon.
- **Container escape ≠ sandbox escape for agent purposes.** Even with perfect kernel isolation, a compromised agent with network access can exfiltrate data, call external APIs, or manipulate user-facing systems. Isolation buys you time; permission scoping prevents the damage.
