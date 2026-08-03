# Agentic Security Patterns — Evidence Bank
*Last updated: 2026-08-03*

## Primary Sources

### 1. Microsoft Security Blog — RCE via Prompt Injection (May 7, 2026)
**URL:** https://www.microsoft.com/en-us/security/blog/2026/05/07/prompts-become-shells-rce-vulnerabilities-ai-agent-frameworks/
- Two critical RCE vulnerabilities in Microsoft Semantic Kernel
- Single prompt → calc.exe on host device, no browser exploit or memory corruption
- Model behaved correctly; vulnerability in framework/tool data trust
- CVEs in source

### 2. OWASP Top 10 for Agentic Applications (December 9, 2025)
**URL:** https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- Peer-reviewed by NIST, Microsoft AI Red Team, AWS
- 100+ industry experts contributing
- Ten categories: ASI01–ASI10 covering goal hijack, tool misuse, identity confusion, overreliance, supply chain, memory poisoning, planning exploitation, DoS, memory exhaustion, data leakage
- FinBot CTF platform for training

### 3. Cloud Security Alliance — Hugging Face Autonomous Agent Breach (July 20, 2026)
**URL:** https://labs.cloudsecurityalliance.org/research/csa-research-note-huggingface-autonomous-agent-breach-202607/
**PDF:** https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/07/CSA_research_note_huggingface_autonomous_agent_breach_20260720-csa-styled.pdf
- Disclosed July 16, 2026
- 17,000+ logged attacker actions over single weekend
- Agent drove intrusion end-to-end: initial access → lateral movement across internal clusters
- Model not bound by commercial safety guardrails

### 4. Zylos Research — Agentic AI Security Defense Stack (May 16, 2026)
**URL:** https://zylos.ai/en/research/2026-05-16-agentic-ai-security-prompt-injection-defense-stack
- 73% of production AI deployments experienced prompt injection (2025)
- 91,403 attack sessions targeting LLM endpoints (GreyNoise, 2025–2026)
- 29% of organizations prepared to secure agentic AI
- 32% increase in malicious prompt injection payloads (Google, Nov 2025–Feb 2026)

### 5. Digital Applied — AI Agent Sandboxing Patterns (May 17, 2026)
**URL:** https://www.digitalapplied.com/blog/ai-agent-sandboxing-isolation-patterns-2026
- Five isolation tiers: OS process → user-space kernel → dev container → microVM → full VM
- Vercel Sandbox GA January 2026 uses Firecracker
- Claude Code 1.3 ships process-level sandboxing by default
- E2B uses Firecracker

### 6. Microsoft Security Blog — Least Privilege for AI Agents (July 16, 2026)
**URL:** https://www.microsoft.com/en-us/security/blog/2026/07/16/least-privilege-for-ai-agents-identity-access-and-tool-binding/
- Entra Agent ID for per-agent identity
- Scoped authorization and tool-binding
- Automated revocation controls

### 7. OWASP AI Agent Security Cheat Sheet
**URL:** https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
- 12 identified risk categories
- Best practices: per-tool permission scoping, separate tool sets by trust level, explicit authorization for sensitive operations

## Stack Entries Covering This Topic
- S-2076 (this cycle): Agentic blast radius / prompt injection → RCE / defense-in-depth
