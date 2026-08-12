# S-2472 · The Browser-Use Benchmark Gap Stack — When WebArena Scores 78% but Production Books 22%

Your browser agent scores 78% on WebArena. It handles checkout, login, and navigation tasks reliably in the eval harness. In production, it books 22% of shopping carts, gets stuck on captchas nobody told it about, and sends form submissions to fields that moved between renders. The drop is not a model regression. It is the gap between a frozen benchmark and a live page. Every team that ships a browser agent discovers this gap the same way: through a P0 incident at 2 AM.

## Forces

- **Benchmarks freeze what production renders fresh.** WebArena uses self-hosted snapshots of Reddit, GitLab, and e-commerce sites — static HTML at a fixed point in time. Production pages are dynamic: A/B tests rotate layouts, CDNs serve different assets per region, and JavaScript frameworks render content client-side after the initial HTML loads. The DOM the agent was evaluated against is structurally different from the DOM it encounters live.
- **Session state doesn't survive benchmarking.** Public benchmarks initialize agents with clean sessions. Production agents must handle existing cookies, stored payment methods, expired auth tokens, and shopping carts with items that are now out of stock. The eval assumes a blank slate; production hands the agent a messy, stateful world.
- **Production failure modes are adversarial to automation.** Captchas, rate-limit walls, modal overlays, cookie consent banners, and JavaScript-rendered buttons exist specifically to gate automated access. Benchmarks either don't include them or include them as edge cases. In production, they are the rule, not the exception.
- **Happy-path benchmarks measure the wrong thing.** WebAren's completion rate measures whether the agent can reach the goal state on a frozen page with a clean session. What it doesn't measure is how often the agent recovers gracefully from the six failure modes that occur in production — and graceful recovery, not raw completion rate, determines whether a browser agent earns its compute cost.
- **The agent's observation modality is fragile.** Screen recordings and DOM snapshots are brittle observation channels. A single pixel change in a CSS class, a shifted `z-index`, or a JavaScript-rendered overlay can make the agent's selector or screenshot understanding wrong — even though the model "sees" the right thing, it reasons about it based on stale structural priors.

## The move

### The Six Production Failure Modes

Evaluate browser agents on recovery rate per failure mode, not aggregate completion rate.

**1. DOM selector drift.** Live pages diverge from benchmark snapshots. Fix: Use semantic selectors (ARIA roles, accessible names, structural relationships) over CSS/XPath selectors, and validate selector stability with a DOM-diff pipeline before each deployment.

**2. Screenshot ambiguity.** Visual layouts differ from frozen eval environments (dynamic fonts, responsive breakpoints, dark mode). Fix: Use a multi-modal evaluation that compares trajectory-level outcomes, not pixel-perfect screenshot matching.

**3. Login state persistence.** Auth tokens expire, sessions time out, and 2FA challenges interrupt multi-step workflows mid-execution. Fix: Implement session continuity checkpoints — save session state at each step boundary so the agent can resume rather than restart.

**4. Modal interruptions.** Cookie banners, subscription popups, and chat widgets overlay the primary workflow without warning. Fix: Classify modal types and implement a modal-handling policy — which to dismiss, which to pause for, which to abort on.

**5. Rate-limit cliffs.** Browsers, APIs, and web applications all impose rate limits. A production agent that hits a rate limit mid-checkout leaves the cart in an indeterminate state. Fix: Add idempotency keys to every agent action, and implement a rate-limit-aware stepper that backs off before the cliff rather than after.

**6. Irreversibility risk.** Benchmark completions can be replayed indefinitely. Production actions — form submissions, purchase confirmations, email sends — are often irreversible. Fix: Enforce a human-in-the-loop gate for irreversible actions, with a dry-run mode that executes all steps except the final commit.

### Eval Harness Design

```
# Trajectory-level scoring (not pass/fail)
class BrowserAgentEval:
    def score(self, agent, task, environment):
        trajectory = agent.run(task, environment)
        failure_modes = self.classify(trajectory)

        recovery_score = sum(
            1.0 for fm in failure_modes
            if fm.recovered  # agent handled it gracefully
        ) / len(failure_modes)

        # Penalize irreversible mistakes
        irreversible_harm = sum(
            fm.severity for fm in failure_modes
            if fm.irreversible and not fm.halted_before
        )

        return TrajectoryScore(
            recovery_rate=recovery_score,
            irreversible_harm=irreversible_harm,
            failure_modes=failure_modes,
        )
```

Score each agent by **recovery rate** (how many of the six failure modes it handled gracefully) and **irreversible harm** (how many irreversible actions it executed without a pre-commit gate). An agent with 60% recovery and zero irreversible harm is more production-ready than one with 85% completion and two order confirmations sent to wrong addresses.

### Production Deployment Checklist

Before shipping a browser agent:
1. Run against a live staging environment (not snapshot) for 200+ tasks
2. Measure recovery rate on each of the six failure modes individually
3. Validate selectors with a DOM-diff checker on weekly page renders
4. Implement session checkpoints at every step boundary
5. Add human-in-the-loop gates for irreversible actions
6. Monitor per-session cost — browser agents are 10–50× more expensive per task than API agents

## See also
- [S-998 · The Capability Ceiling Stack](/stacks/s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — eval design failure that ships wrong capability targets
- [S-1019 · The Three-Pillar Observability Stack](/stacks/s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — tracing framework for multi-step agent trajectories
- [S-1056 · The Tool Arsenal Stack](/stacks/s1056-the-tool-arsenal-stack-when-your-agent-has-400-tools-and-cant-pick-one.md) — tool overload in multi-capability agents
