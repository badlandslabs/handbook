# S-2721 · The Agent Evaluation Stack — When You Ship Your Agent and Cross Your Fingers

[Your agent passed the demo. Your team signed off. You shipped it. Three weeks later you're fielding support tickets about outputs that look correct but aren't — a wrong address sent to a vendor, a tool called with inverted parameters, a planning agent that loops forever on edge cases. Nobody caught it because nobody had a way to catch it. The evaluation problem: agents break in ways traditional tests can't detect, and accuracy alone tells you almost nothing about production reliability.]

## Forces

- **Accuracy is a lie for agents.** The CLEAR framework (arXiv:2511.14136) found accuracy-only metrics correlate with production success at ρ = 0.41 — barely better than a coin flip. Cost, latency, assurance, and reliability together score ρ = 0.83. Yet most teams still measure "did it get the right answer?"
- **The math compounds against you.** At 95% reliability per step — optimistic for current LLMs — a 20-step task succeeds only 36% of the time. A 10-step workflow has a 60% failure rate before you've even introduced an edge case. The failure surface grows exponentially with trajectory length.
- **Trajectories matter more than outputs.** A wrong answer reached via a correct reasoning chain reveals a different problem than a right answer reached via a flawed plan. Testing outputs alone hides which part of the agent broke.
- **17% of multi-step failures are step repetitions.** 14% are reasoning-action mismatches — the agent decides on one thing and does another. Neither failure mode appears in output tests. (arXiv, 2025)
- **Evaluation can't be one-time.** The agent changes without you changing it — model updates, RAG index changes, tool modifications by other teams — all silently shift behavior. A static test suite becomes stale the moment you deploy.

## The move

Build a layered evaluation harness that gates the agent at every stage of the SDLC, measures trajectories not just outputs, and runs continuously.

### 1. Decompose into architectural layers with isolated assertion slices

Don't test end-to-end pass rates — they mask where regressions occur. Instead, decompose the agent into layers (speech act, routing, decomposition, safety, knowledge, memory, personalization) and run isolated assertions per layer in CI on every PR. One production ordering agent used 23 architectural slices; 19 were covered with deterministic, no-LLM assertions. The four uncovered slices (including tool routing) required a separate evaluation strategy. (arXiv:2606.11686)

### 2. Score across six dimensions, not one

The evaluation consensus from 2025–2026 production deployments: score trajectory on correctness, efficiency (step count vs optimal), safety (tool permissions, escalation decisions), tool selection accuracy, error recovery, and hallucination/groundedness. Golden datasets with expected trajectories let you assert against any of these dimensions.

### 3. Build a golden dataset from production traces, not hand-crafted examples

Start with 50 traces harvested from production traffic — real user inputs, real tool calls, real failure paths. Grow weekly through structured review. Hand-crafted examples miss the distributional patterns that appear in production. (GitHub fr3kchy/agent-eval-harness-demo; Thinking Inc. evaluation practice)

### 4. Gate releases with three non-negotiable checkpoints

1. **Regression block** in CI — golden dataset assertions must pass before merge. Treat this like any other test suite.
2. **Cost gate** — if average cost per task exceeds threshold (a 4.4–10.8x cost difference exists between accuracy-equivalent agent configurations), fail the gate.
3. **Shadow evaluation** — run new version in parallel against production traces before canary rollout. Compare trajectories, not just outcomes.

### 5. Use LLM-as-judge for scale, human review for high-stakes paths

Sample 5–10% of outputs for human review at 15–20 minutes per review. Use LLM-as-judge to cover the remaining 90%. Budget USD 5,000–20,000 for evaluation infrastructure — 10–25% of typical agent operating costs. Teams that skip this investment typically spend 3–5x more on incident response and remediation. (McKinsey Digital, 2025; Thinking Inc.)

## Evidence

- **arXiv (primary research):** CLEAR framework study — accuracy-only metrics correlate with production success at ρ = 0.41; CLEAR metrics (Cost, Latency, Efficacy, Assurance, Reliability) score ρ = 0.83. Also found a 37% lab-to-production performance gap. — [https://arxiv.org/html/2511.14136v1](https://arxiv.org/html/2511.14136v1)

- **arXiv (primary research):** Layer-isolated evaluation paper — 23-layer decomposition of a production ordering agent with deterministic, no-LLM test slices. Key finding: aggregate end-to-end pass-rates mask where regressions occur; per-layer slices localize faults. Four layers (including L2_routing) required separate coverage strategies. — [https://arxiv.org/pdf/2606.11686v1](https://arxiv.org/pdf/2606.11686v1)

- **Production engineering blog:** 17.14% of multi-step agent failures are step repetitions; 13.98% are reasoning-action mismatches. 95% reliability × 20 steps = 36% success rate. 32% of organizations cite quality as the top barrier to deploying agents. — [https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)

- **GitHub (open-source):** Agent eval harness demo — golden dataset format with expected outputs, categories, and tags; LLM-as-judge scoring with CI/CD regression gates. — [https://github.com/fr3kchy/agent-eval-harness-demo](https://github.com/fr3kchy/agent-eval-harness-demo)

- **Enterprise evaluation practice:** Evaluation infrastructure costs USD 5,000–20,000, representing 10–25% of agent operating costs. Organizations skipping evaluation investment spend 3–5x more on incident response. — [https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)

## Gotchas

- **Golden datasets rot.** A dataset created at launch is stale within weeks as production traffic shifts. Build a weekly review ritual to add production traces and retire examples that no longer represent real distribution.
- **LLM-as-judge has a conflict of interest.** Using the same model as judge and agent introduces bias — the judge tends to rate the agent it shares architecture with more generously. Use a different model family for judgment, or use deterministic assertion slices where possible.
- **Per-test pass rates hide step-level failures.** An 80% pass rate tells you nothing about whether safety checks or escalation logic regressed. Layer isolation is the only way to catch regressions in specific subsystems.
- **Cost gates catch what accuracy gates miss.** Two agent configurations can achieve identical accuracy while costing 4–10x different per task. Without a cost gate, you're silently choosing the expensive option every time.
- **Stateful agents need per-pass isolation in the test harness.** Test fixtures that carry state between test runs will invent off-diagonal coupling that doesn't exist in production. Each assertion slice must reset to a clean state.
