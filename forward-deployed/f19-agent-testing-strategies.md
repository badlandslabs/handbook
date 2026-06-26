# F-19 · Agent Testing Strategies

Software tests assume a deterministic function: same input, same output, predictable failure. An agent is not that. The same prompt produces different surface phrasings across runs; the same tool call can return structurally correct but factually wrong results. "Exact match" tests collapse immediately. The fix is not to abandon testing — it is to test the right layer: structure and behavior, not surface form.

## Situation

Your agent passes manual checks but breaks in production. Or you changed a prompt and don't know if anything regressed. Or you've been putting off testing because "how do you unit-test a language model?" The discomfort is real, but testing an agent is tractable — it just requires a different target than classical software testing.

## Forces

- LLM outputs have surface variation by design: the same correct answer can be phrased a hundred ways. A test that checks the exact string will fail 2 of 3 correct outputs ([S-04](../stacks/s04-structured-output.md) reduces this; it doesn't eliminate it).
- Tool calls *are* deterministic in structure: the agent either calls the right function with valid arguments or it doesn't. This layer is fully unit-testable without model uncertainty.
- End-to-end behavioral correctness is probabilistic: you must run n times and measure what fraction pass, not run once and assume. This is pass@k — the right metric for agentic reliability ([F-11](f11-agent-reliability.md)).
- [F-02](f02-evaluation-at-scale.md) is for *production monitoring* — knowing if a deployed system is degrading across thousands of live outputs. This is *dev-time testing* — knowing before you ship. They use the same infrastructure but answer different questions.
- Every dollar of testing cost finds bugs before production; every unfound bug finds you after. The ratio is 5–10× in classical software; for agents, where production failures are harder to trace, it is at least that.

## The move

**Three layers, in order of cost. Run lower layers on every change; upper layers on every merge.**

**Layer 1 — Tool-call unit tests (deterministic, instant, no model needed).**
Test that the agent selects the right tool and passes structurally valid arguments. This is fully deterministic because tool choice is a structured output you log. Mock the tool's return value; assert on the call.

```js
// Assert: lookup_price is called with a well-formed SKU
assert(call.tool === "lookup_price");
assert(typeof call.args.sku === "string");
assert(call.args.sku.startsWith("SKU-"));
// Does NOT assert on the reply text — that's a higher layer
```

**Layer 2 — Property tests on outputs (robust to surface variation).**
Test that the output satisfies a semantic constraint — not that it matches a string. Pick the most specific constraint that still allows all valid phrasings.

```js
// Correct: tests the fact, not the phrasing
assert(output.includes("29.99"));

// Wrong: tests surface form, rejects "SKU-A44 is currently priced at $29.99."
assert(output === "The price of SKU-A44 is $29.99.");
```

Schema validation ([S-04](../stacks/s04-structured-output.md)), value-range checks, and presence of required fields all belong here. Layer 1 tests *structure*; Layer 2 tests *content*.

**Layer 3 — Behavioral tests with pass@k.**
Run the full agent loop n times on a fixed task and measure the pass rate. Set k from your reliability target: if the agent passes 80% of runs and you need 95% confidence of at least one correct answer, you need pass@2. This is expensive (n model calls per test), so reserve it for critical paths and run it nightly, not on every commit.

```
pass_rate = passing_runs / n
k = ceil(log(1 - target) / log(1 - pass_rate))
```

**Freeze inputs; vary only what you're testing.** Use a fixed, versioned set of test cases — not live production inputs, not randomly sampled. A test suite that changes on every run can't detect regressions.

**Test regressions, not just new features.** Every bug found in production becomes a test case. An agent that wandered into a loop, called the wrong tool, or produced a malformed output — that specific trace is your cheapest regression test, and it costs nothing but logging.

**Log tool calls in production; replay them in tests.** If you log every tool call with its input, you have a free integration-test suite: replay the input through a new agent version and assert the call structure matches. This is snapshot testing adapted for agents.

## Receipt

> Verified 2026-06-26 — Node. No model in the loop by design: the receipt tests the *testing framework*, not the model. Three realistic correct outputs (surface variation of the same fact) and three wrong outputs (wrong tool, malformed SKU, stale value) are used as the fixture set.

```
Test        │ correct outputs (all 3 should pass) │ wrong outputs (all 3 should fail)
────────────┼─────────────────────────────────────┼──────────────────────────────────
exact-match │ ✓ ✗ ✗                               │ ✓ ✓ ✓
tool-call   │ ✓ ✓ ✓                               │ ✓ ✓ ✗
property    │ ✓ ✓ ✓                               │ ✓ ✓ ✓
```

**What the receipt shows:**

- **Exact-match** rejects 2 of 3 correct outputs — both phrasings of the right answer that differ from the golden string. It would block a correct agent from shipping. This is the wrong layer.
- **Tool-call unit test** passes all 3 correct outputs and catches 2 of 3 wrong ones — but misses wrong output 3 (correct tool, correct SKU, stale value $19.99 instead of $29.99). The tool-call layer tests *structure*, not values. Correct: it is not this layer's job to catch value errors.
- **Property test** passes all 3 correct outputs and rejects all 3 wrong ones. It is the only layer that catches the stale-value error, because it checks the specific fact (`includes("29.99")`), not the structure or the exact form.

The three layers are not substitutes — they catch different failure modes. A production agent needs all three: tool-call for structure, property for correctness, pass@k for reliability under repetition.

```
Pass@k demo: 8/10 runs pass (rate=0.8)
  → need pass@2 to be 95% confident of at least one correct answer
```

## See also

[F-02](f02-evaluation-at-scale.md) · [F-07](f07-evaluation-driven-development.md) · [S-30](../stacks/s30-code-test-fix-loop.md) · [S-32](../stacks/s32-verifiability-divider.md) · [F-11](f11-agent-reliability.md)

## Go deeper

Keywords: `agent testing` · `pass@k` · `tool call unit test` · `property test` · `behavioral test` · `snapshot testing` · `regression suite` · `non-deterministic testing` · `eval harness` · `test pyramid`
