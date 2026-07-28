# [S-1779] · The Agent Longevity Stack

Your AI agent scored 85% on its evaluation suite. You deployed it on Monday. By Friday, it was hallucinating tool calls. By the following Monday, your on-call engineer had manually intervened six times. By day 14, accuracy had dropped to 60%, and nobody could explain why.

The model has not changed. The prompt has not changed. The agent has.

This is the **agent longevity problem** — the single most underreported failure mode in production AI deployments. Unlike model degradation (which is the provider's problem), agent longevity failure is caused by the operating environment slowly poisoning agent behavior across multi-day runs.

## Forces

- Staging environments are curated. Production users invent inputs no fixture ever anticipated, and they do it simultaneously at scale.
- A point-in-time benchmark answers "how good is the agent today?" — it is blind to the more consequential question: "is the agent as good as it was last Tuesday?"
- Agent sessions in production are measured in hours to weeks, not minutes. Time is the variable eval suites never account for.
- Context window bloat, memory corruption, credential invalidation, and input distribution shift compound non-linearly — each accelerates the next.
- Classic software SLOs (uptime, latency) measure whether the system runs. They do not measure whether the system's behavior is degrading.

## The move

### The Four Decay Mechanisms

**1. Tool-call error accumulation.** Each tool call in a session can introduce an error — a missing parameter, a wrong ID, an API timeout. Long sessions accumulate error surface. Without session-scoped state validation, the agent's internal model of "what tool X returned last time" drifts from reality. The agent then makes subsequent tool calls based on corrupted state. This compounds because tool outputs feed into the next reasoning step.

**2. Context-window bloat.** The agent's working context fills with session history. Critical system instructions (the preamble, tool descriptions, guardrails) are pushed further from the model's attention window. The agent starts ignoring instructions it would have followed on day one. This is invisible from outside — the agent produces output, just not the right output.

**3. Prompt drift from real users.** Test fixtures use clean, structured inputs. Real users type typos, ask non sequiturs, switch languages mid-session, and send inputs that are valid but out-of-distribution. Each edge-case interaction subtly reshapes the agent's in-session behavior. After hundreds of real user interactions, the agent's effective behavior has diverged from the prompt's intent without any explicit change.

**4. Rate-limit back-pressure.** Under concurrent load, retrieval systems degrade. Vector search returns stale results, RAG pipelines timeout, and memory lookups return partial data. The agent compensates by reasoning from incomplete information. The degradation is silent — the agent still produces confident outputs, but from impoverished context.

### The Longitudinal Eval Loop

The structural fix is treating agent quality as a time-series, not a point-in-time measurement:

```
Deploy ──► Daily spot-check eval ──► Weekly full eval ──► Alert on regression ──► Retrain / reset
```

- **Daily spot-check**: Run a 20-case eval on production-traffic-sampled inputs each morning. Track the pass rate trend, not just the absolute value.
- **Weekly full eval**: Full regression suite against golden datasets. Compare trajectory quality (did the agent use the right tools in the right order?) not just output quality.
- **Regression alert threshold**: Alert when daily spot-check drops >5pp from the 7-day rolling average. Do not wait for the SLO to trigger — by then, hundreds of users have received degraded output.
- **Scheduled session reset**: For long-running agents, architect for stateless session resumption. Reset the working context to a known-good baseline at defined intervals (every N interactions, every 24 hours, or on error threshold). Treat the session state as ephemeral infrastructure, not durable memory.

### Detecting the Decay Before It Hurts

```python
# Longitudinal quality tracking — spot-check eval on production traffic samples
import json
from datetime import datetime, timedelta

def daily_spot_check(agent, production_samples, eval_cases, regression_threshold=0.05):
    """
    agent: the deployed agent function
    production_samples: recent production inputs (for input-distribution drift)
    eval_cases: curated golden cases
    regression_threshold: alert if drop exceeds this fraction
    """
    today_score = evaluate_agent(agent, eval_cases)
    yesterday_score = get_previous_score()  # from metrics store

    # Detect score regression
    score_delta = today_score - yesterday_score
    if score_delta < -regression_threshold:
        alert_oncall(
            subject="Agent regression detected",
            body=f"Quality dropped {abs(score_delta):.1%} in 24h. "
                 f"Yesterday: {yesterday_score:.1%}, Today: {today_score:.1%}. "
                 f"Review recent production interactions for decay pattern.",
            severity="warning" if score_delta > -0.10 else "critical"
        )

    # Detect input distribution shift (new failure mode class)
    production_distribution = classify_production_inputs(production_samples)
    eval_distribution = get_eval_input_distribution()
    distribution_shift = js_divergence(production_distribution, eval_distribution)
    if distribution_shift > 0.15:
        alert_oncall(
            subject="Production input distribution shift detected",
            body=f"Production inputs have diverged {distribution_shift:.2f} "
                 f"(Kullback-Leibler) from eval baseline. "
                 f"Eval suite may no longer represent real traffic.",
            severity="info"
        )

    return {"score": today_score, "delta": score_delta, "dist_shift": distribution_shift}
```

### Architectural: Stateless Session Resumption

```python
# Session state as ephemeral infrastructure — resumable, resettable
class AgentSession:
    def __init__(self, agent, session_id=None, reset_policy="interval"):
        self.agent = agent
        self.session_id = session_id or uuid4()
        self.interaction_count = 0
        self.reset_policy = reset_policy  # "interval", "error_threshold", "manual"

        # Working memory is reconstructed from durable facts, not accumulated
        self.facts = self._load_facts()      # external knowledge base
        self.turns = []                        # short sliding window only
        self.tool_state = ToolState()         # validated on every read

    def step(self, user_input):
        # Validate tool state before every turn
        self.tool_state.validate()  # re-fetch if stale

        # Sliding window: keep last 20 turns max
        if len(self.turns) >= 20:
            self.turns = self.turns[-20:]

        response = self.agent(
            input=user_input,
            facts=self.facts,        # always from source of truth
            turns=self.turns,        # short window only
            tool_state=self.tool_state
        )

        self.turns.append({"role": "user", "content": user_input})
        self.turns.append({"role": "assistant", "content": response})
        self.interaction_count += 1

        # Reset on policy
        if self._should_reset():
            self._reset()

        return response

    def _should_reset(self):
        if self.reset_policy == "interval":
            return self.interaction_count >= 500
        elif self.reset_policy == "error_threshold":
            return self.tool_state.error_rate > 0.05
        return False

    def _reset(self):
        """Reset to known-good baseline — facts stay, context clears"""
        self.turns = []
        self.tool_state = ToolState()
        log_event("session_reset", session_id=self.session_id, reason=self.reset_policy)
```

## Receipt

> Verified 2026-07-28 — Research synthesis from AgentMarketCap (Apr 2026), Zylos Research (Apr 2026), Iron Mind (May 2026), arXiv:2601.04170 (Abhishek Rath, Jan 2026). Pattern: agents scoring 85% at deploy reaching 60% accuracy by day 14, with four documented decay mechanisms. Longitudinal eval loop concept and session reset pattern are architectural best practices confirmed across multiple sources. Code examples are representative architectures — not run against a live system. Receipt pending for production measurement.

## See also

- [S-1764 · The Production Eval Gap Stack](stacks/s1764-the-production-eval-gap-stack-when-your-benchmark-says-95-percent-and-production-says-nothing.md) — benchmark vs. production score divergence
- [S-1581 · The SLO Blind Spot Stack](stacks/s1581-the-slo-blind-spot-stack-when-your-agent-score-is-87-percent-and-nobody-can-tell-you-why.md) — why your agent score means less than you think
- [S-1773 · The Context Hygiene Stack](stacks/s1773-the-context-hygiene-stack-when-your-agents-remember-things-that-never-happened.md) — cross-session memory contamination
- [S-1775 · The Operational Memory Stack](stacks/s1775-the-operational-memory-stack-when-your-agent-forgets-what-it-was-doing-halfway-through.md) — agent forgetting mid-session state
