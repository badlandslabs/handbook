# S-1851 · The Heaviside Gate Stack: When Your Agent Proceeds Confidently from a State That Doesn't Exist

An agent that generates is not the same as one that knows its generation is true. Autoregressive decoding has no native mechanism to catch a false intermediate state before it poisons the next step. The Heaviside Gate closes that gap: execution advances only when independent verification confirms the current state is real.

## Situation

A code agent calls a function, reads back a return value, and uses that value in the next call — except the function threw an exception that the agent's exception handler silently swallowed. The agent "knows" the value is `42`. It is not. A research agent cites a paper it found in its context window. The paper title looks plausible. It does not exist. The agent has no signal to distinguish "plausible-sounding" from "actually there." A planning agent decomposes a task into seven steps, executes step 3, and begins step 4 based on the output of step 3 — which failed silently. The entire remainder of the plan is now grounded in a phantom state.

In each case the agent was fluent, confident, and wrong. The error wasn't in reasoning. It was in state: the agent treated a claim state (what the model generated) as equivalent to a reference state (what is actually true).

## Forces

- **Generators are not verifiers.** A model optimized to produce likely sequences cannot be trusted to confirm those sequences are correct. Confidence and correctness are decorrelated.
- **Errors compound downstream.** One false intermediate state doesn't just produce one wrong output — it poisons every downstream step that depends on it. The cost of error grows exponentially with plan depth.
- **Silent failures look like successes.** When a tool returns `null`, a non-existent file, or an empty list, the agent often fills the gap with a plausible interpolation and continues. The failure mode is invisible without a ground-truth check.
- **Latency pressure resists safety.** Wrapping every step in a synchronous verification pass doubles round-trips. The solution must be concurrent, not sequential.
- **Honest halts are better than confident corruption.** For weaker models, knowing you failed is worth more than proceeding incorrectly. The gate must convert failures to explicit halts, not pass them through.

## The move

**The Heaviside Gate** (from HCRC — *Heaviside Continuity of Rolling Coefficients*, Pitsane & Mogale, arXiv:2607.04562, Jul 2026) wraps inference as a predicate-gated state machine. The gate has only two states: `CONTINUE` or `HALT`. It advances only when a correctness predicate is satisfied. Crucially, the predicate is checked by an *independent* parallel worker — not by the proposing model.

### 1. The proposers-generators-gate architecture

```
┌─────────────┐     propose state     ┌─────────────┐
│  Proposer   │ ──────────────────▶  │ Heaviside   │
│  (primary)  │ ◄──────────────────  │    Gate     │
└─────────────┘     gate decision     └──────┬──────┘
       ▲                                       │
       │        ┌──────────────┐               │
       └────────│  Parallel    │◄──────────────┘
         verify │  Verifier    │
                │  (independent│
                └──────────────┘
```

Three roles:
- **Proposer**: the primary agent/model that generates the next state (tool call, reasoning step, plan fragment)
- **Verifiers**: one or more parallel independent workers that check whether the proposer's output satisfies the defined predicate
- **Heaviside Gate**: a deterministic function that reads all verifier signals and produces `{CONTINUE, HALT}` — no probabilistic tie-breaking, no model judgment

### 2. Define predicates for your execution type

The power of the gate comes from predicates that are specific to your domain. Generic predicates (e.g., "is the output a string?") add no safety. Good predicates are:

| Domain | Predicate | Verification method |
|--------|-----------|---------------------|
| Tool call | `file.exists(path)`, `http.status == 200`, `schema.validate(output)` | Direct system call or API check |
| Code execution | `test_suite.run(function, inputs) == expected` | Sandboxed subprocess with assertions |
| Knowledge retrieval | `vector_db.distance(claim_embedding, fact_embedding) < threshold` | Separate retrieval pass |
| Plan step | `preconditions_of_next_step ⊆ outputs_of_current_step` | Schema or type check |
| API response | `schema.validate(response)` + `status not in [4xx, 5xx]` | JSON schema validator |

The key insight: **predicates must be checkable against external ground truth, not against the proposer's own output**. Asking the model "is this correct?" is not a predicate — it's a second opinion from the same unreliable source.

### 3. Run verification concurrently

Verification must not block the critical path. Use a parallel worker architecture:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def execute_with_gate(proposer, predicates, timeout=5.0):
    # Launch proposer and all verifiers concurrently
    propose_task = asyncio.create_task(proposer.propose())

    verifiers = [
        asyncio.create_task(check(predicate, timeout))
        for predicate in predicates
    ]

    # Race: proposer output vs. all verifiers
    done, pending = await asyncio.wait(
        [propose_task] + verifiers,
        return_when=asyncio.FIRST_COMPLETED
    )

    # Cancel pending work
    for t in pending:
        t.cancel()

    proposer's_output = propose_task.result()
    results = [v.result() for v in verifiers if v.done() and not v.cancelled()]

    # Heaviside gate: ALL predicates must pass
    if all(results) and len(results) == len(predicates):
        return {"decision": "CONTINUE", "output": proposer's_output}
    else:
        return {"decision": "HALT",
                "reason": f"Predicates failed: {[p for p, r in zip(predicates, results) if not r]}"}
```

The proposer generates while verifiers run in parallel. If the gate closes before the proposer finishes, you saved a round-trip. If the proposer finishes first and verifiers confirm, you advance. If any verifier fails, you halt — regardless of how confident the proposer was.

### 4. Handle the three failure modes

The gate has a three-state output, not two:

- **`CONTINUE`**: all predicates satisfied. Proceed.
- **`HALT(CORRUPT)`**: predicates failed — proposer's state is wrong. Do not use the output. Revert or surface to operator.
- **`HALT(UNKNOWN)`**: verifiers timed out — state is unconfirmed. This is the honest halt. It is not an error; it is uncertainty made explicit.

For weaker models, the gate shifts the failure mode from *confident corruption* to *honest uncertainty*. On capable proposers, HCRC reduces **False Completion Rate (FCR)** from 4–7% to **0%** while remaining latency-competitive.

### 5. Design the proposer's continuation contract

When the gate halts, the proposer must know how to respond. Define a continuation contract:

```python
GATE_RESPONSE = {
    "CONTINUE": proposer.continue_with(output),
    "HALT(CORRUPT)": [
        proposer.revise(feedback=verifier.reason),
        proposer.alternative_approach(),
        operator.alert("Unrecoverable state divergence")
    ],
    "HALT(UNKNOWN)": [
        proposer.request_confirmation(),
        operator.alert("State unconfirmed after timeout")
    ]
}
```

Without this contract, a halt just produces a cryptic error. With it, the gate becomes a recovery trigger.

## Receipt

> Verified 2026-07-30 — Source: arXiv:2607.04562v1 (Pitsane & Mogale, Jul 6 2026). Key claims: FCR reduction from 4–7% to 0% on software-engineering and reasoning tasks across 13 proposers from 4 providers; honest halts replace silent corruption for weaker models. Architecture verified against the propositional HCRC framework. Latency claim (gate competitive with unwrapped model) validated against the concurrent evaluation design. No production deployment case studies in the paper beyond "operated for months as part of [internal] pipeline" — receipt reflects framework design, not production validation. Tradeoff: predicate design requires domain expertise and is the actual bottleneck; the gate architecture is straightforward by comparison.

## See also

- [S-976 — The Verification Layer](/stacks/s976-the-verification-layer-when-your-agent-cant-distinguish-right-from-almost-right.md): the broader verification landscape and LLM-as-judge approaches. HCRC is the execution-layer special case of that pattern.
- [S-1671 — The Reasoning Trap Stack](/stacks/s1671-the-reasoning-trap-stack-when-enhancing-reasoning-makes-tool-hallucination-worse.md): the problem HCRC is solving — epistemic entropy from unverified intermediate states.
- [S-1239 — The Runtime Verification Loop](/stacks/s1239-the-runtime-verification-loop-when-inline-verification-is-the-difference-between-correct-and-confident.md): production-scale inline verification patterns; complementary to the Heaviside Gate's specific concurrent predicate architecture.
