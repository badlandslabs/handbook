# S-2227 · The Permission Architecture Stack — When Your Agent Can Do Anything But Shouldn't

Your AI coding agent just deleted your production database. Not because it was malicious — because it was trying to help. The shell tool said yes. Nobody was watching. Permission architecture is the discipline that prevents this: classifying every action by blast radius, gating the consequential ones, and making the rest flow freely. Without it, your agent is a loaded weapon with no safety.

## Forces

- **Approval fatigue vs. blast radius.** Every permission prompt trains users to click yes. But unconstrained agents can send real emails, mutate production systems, and authorize payments. The wrong gate placement kills both usability and safety.
- **Lab metrics vs. adversarial reality.** Anthropic reports a 0.4% false positive rate and 17% false negative rate for Claude Code's auto mode on production traffic. Independent researchers at HKUST and ETH found 81% false negative rate under targeted scope-escalation stress-testing — the classifier was never adversarially hardened at deployment.
- **Implicit trust leaks.** When Tier 2 (in-project edits) bypasses the classifier in Claude Code's architecture, the implicit assumption is that "in-project" implies "safe." It doesn't. A malicious or hallucinating agent can compound damage through in-project mutations before any gate fires.
- **Reversibility asymmetry.** Read operations and soft deletes are cheap to over-approve. Database writes, email sends, and money movements are expensive to under-approve. Most agents treat all errors symmetrically; permission architecture treats them by irreversibility.

## The move

**Classify every tool call by blast radius, then gate proportionally.** The pattern that emerged across Claude Code, the AEGIS instrumentation framework, and production approval gate implementations uses a three-tier model:

- **Tier 1 — Safe and reversible.** Auto-approve: read-only file operations, local documentation lookups, linting, type-checking, test runs. Zero gate friction. These are the 90% of calls that should never interrupt a flow.
- **Tier 2 — Policy-gated.** Route through a policy engine (not a human): in-project file writes, configuration changes, package installations. The policy engine evaluates scope (which repo? which branch?), prior approval history, and declared intent. Reject → return reason to agent so it can retry with a safer approach. Approve → dispatch and log.
- **Tier 3 — Human-gated.** Anything with scope beyond the project boundary, irreversible operations, or calls to external systems (APIs, webhooks, email, cloud APIs). Block and escalate. Human approves with explicit context, not rubber-stamp.

**Enforce gates architecturally, not via prompt.** The strongest behavior in Claude Code comes from hooks that intercept pre/post-tool execution, sandboxing at the OS level, and subagent isolation — not from instruction text in the system prompt. Prompts can be jailbroken; architecture cannot.

**Close the feedback loop with structured rejection.** When a gate denies a call, return: (1) the specific rule triggered, (2) what the agent should change to pass, (3) whether retry is allowed. Claude Code's auto mode returns the reason so the model can reformulate a safer approach rather than looping.

**Add safety backstops.** Three consecutive denials or 20 total denials in a session should escalate to human review and pause the agent loop. Track denial patterns — repeated rejections on the same tool type signal either a misconfigured policy or an agent in a confused state.

## Evidence

- **Academic research (arXiv:2604.04978):** HKUST and ETH researchers performed the first independent stress-test of Claude Code's auto mode permission system on deliberately ambiguous authorization scenarios. Found that 36.8% of state-changing actions (Tier 2 in-project edits) route through a gap in the classifier and are never evaluated. Under targeted scope-escalation testing, the false negative rate reached 81.0% — vs Anthropic's reported 17% on production traffic. — [arXiv:2604.04978v2](https://arxiv.org/html/2604.04978v2)
- **Primary source — Claude Code architecture:** Claude Code's governance is implemented through five distinct layers: agent loop (task decomposition), context and memory (what Claude knows now and across sessions), hooks (pre/post-tool interception that can deny or defer), skills (specialized behaviors), and MCP (external tool interfaces). The permission system runs as Sonnet 4.6 as a dedicated classifier evaluating every tool call before execution. Safety backstops: 3 consecutive denials or 20 total denials stop the session and escalate. — [Penligent Architecture Analysis](https://www.penligent.ai/hackinglabs/inside-claude-code-the-architecture-behind-tools-memory-hooks-and-mcp/)
- **Primary source — Production approval gate pattern:** GitHub gist from renezander030 (MIT-licensed reference implementation at github.com/renezander030/agent-approval-gate) formalizes the five-stage pipeline: `draft → validate → approve → dispatch → audit`. Schema validation of proposed actions before queueing; policy or human review gates on consequential operations; deterministic dispatch; full audit log with ApprovalRecord and ActionRecord for compliance. — [GitHub Gist: Agent Approval Gates](https://gist.github.com/renezander030/9069db775e494ffd2cdd5a09adf83add)

## Gotchas

- **The "in-project" assumption is a gap, not a guarantee.** A 36.8% bypass rate on Tier 2 calls means most state-changing mutations in Claude Code never see the classifier. Treat "in-project" as a scope hint, not a safety signal.
- **Stress-test your classifier adversarially, not statistically.** Anthropic's reported 0.4% false positive and 17% false negative rates were measured on representative production traffic. The HKUST/ETH researchers found 81% false negative rate on deliberately adversarial inputs. Your classifier's real false negative rate is a function of how hard you tried to break it.
- **Audit logs are useless without reversibility tracking.** An approval gate that logs every decision but doesn't track whether the approved action was actually reversible (and at what cost) can't drive future policy. Track blast radius: how many records would this write affect? How many recipients would this email reach? Would this command require a rollback procedure to undo?
- **Policy updates require re-eval of past approvals.** A policy change that restricts what Tier 2 can do doesn't retroactively revoke already-approved actions. If the agent has already dispatched the operation, the gate is behind the fact, not in front of it.
