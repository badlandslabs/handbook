# S-987 · The Agent Evaluation Stack — When You Can't Tell If Your Agent Is Actually Working

You shipped the agent. The demo worked. Production traffic flows through it. Now you have no idea whether it's doing the right thing 60% of the time or 99.9%, whether it's hallucinating answers at 2 AM, or whether it silently stopped using the right tool three weeks ago. You are flying blind.

Agent evaluation is the layer most teams skip until the first public failure. Unlike LLM benchmarking, agent eval must cover **tool use correctness, multi-step trajectory quality, and end-to-end task completion** — not just output fluency. Without it, you cannot safely improve, cannot catch regressions, and cannot convince anyone to trust the system.

## Forces

- **Agents are probabilistic trajectories, not single responses** — you need to evaluate a full run (all tool calls, decisions, and outputs), not just the final answer
- **Synthetic test data doesn't predict production behavior** — real user inputs surface failure modes that curated eval sets miss
- **The judge model drifts** — LLM-as-judge is powerful but can flip its verdicts as model versions change, making historical comparisons unreliable
- **Eval cost compounds at scale** — running full traces through large models per commit is expensive; teams cut corners and lose coverage
- **Pass rate is misleading without consequence weighting** — a 95% pass rate means nothing if the 5% failures include unauthorized refunds, data leaks, or policy violations

## The Move

Build an evaluation system with four interlocking layers:

- **Offline eval harness as regression gate** — define tasks with inputs + success criteria; run trials across multiple seeds; score with programmatic checkers (not just LLM judgment). Integrate into CI so any behavior-changing change must clear the same evidence gate as code. This is the baseline: no agent ships without a failing eval that proves it passed.

- **Milestone-based trajectory scoring** — break multi-step tasks into sub-goals with weighted importance. Track what fraction of milestones the agent reaches, not just whether the final answer looks right. This gives you partial credit and surfaces *where* in a trajectory the agent consistently drops the thread.

- **LLM-as-judge with calibration** — use a judge LLM (typically GPT-4o or Claude 3.7 Sonnet for high-stakes, or a distilled small judge like Patronus Lynx 8B for inline high-throughput checks) to score quality dimensions the harness can't detect. Calibrate with Cohen's kappa against human labels on a golden set. Without calibration, the judge's own drift makes historical scores incomparable.

- **Runtime quality gates for production** — for deployed agents, run sampling-based eval on live traffic (e.g., 5% shadow mode, 100% with rollback triggers). Gate on consequence-weighted thresholds: low-stakes tasks can pass at 90%; high-stakes tasks (refunds, data writes, policy decisions) require near-100% on critical assertions.

- **Synthetic + real data duality** — build eval datasets from both curated synthetic cases (for coverage of known edge cases) and sampled production traces (for discovering unknown failure modes). The two sets serve different purposes and both are required.

## Evidence

- **Anthropic engineering blog** defines the core taxonomy: task (inputs + success criteria), trial (single attempt), grader (scoring logic), transcript (full trajectory), outcome (final state). Their framework for building agent evals emphasizes that eval quality compounds — each run makes regressions visible before users see them. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Datadog's Bits AI SRE agent** (autonomous incident investigation, deployed in production alongside their observability platform) runs eval grounded in real production telemetry — not synthetic benchmarks. Their team reports that evaluation with actual production data reveals failure modes synthetic tests never surface, and that causal reasoning over multi-component distributed systems requires domain-specific eval criteria beyond generic task completion. — [https://www.zenml.io/llmops-database/scaling-ai-agents-in-production-building-and-operating-hundreds-of-autonomous-agents](https://www.zenml.io/llmops-database/scaling-ai-agents-in-production-building-and-operating-hundreds-of-autonomous-agents)

- **GitHub agent-eval-harness** (open-source, MIT) implements Cohen's kappa calibration for LLM-as-judge, drift monitoring across eval runs, and a CI regression gate that blocks merges on quality degradation. The README explicitly frames the problem: most agent repos prove "I can build it" — this proves "I can tell when it's broken and stop it from shipping." Runs offline with a deterministic mock LLM for zero-dependency CI. — [https://github.com/ashishlandiwal/agent-eval-harness](https://github.com/ashishlandiwal/agent-eval-harness)

- **Zylos Research (2026)** surveys LLM-as-judge in production: six distinct patterns (offline eval, runtime verifier, self-consistency, Reflexion, constitutional AI/RLAIF, inference-time reward models). Reports that small distilled judges (3B–8B parameter) achieve 0.88–0.95 accuracy versus GPT-4-based evaluation at 97% cost reduction — making inline runtime checking economically viable. Notes that intrinsic self-correction (asking the agent to verify its own output) is unreliable without an external judge. — [https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

## Gotchas

- **Clean test sets only cover happy paths** — if your eval only includes cases you expect to work, failures arrive first in production, not in your harness
- **Drifting judges invalidate historical comparisons** — a judge LLM's behavior shifts across versions; Cohen's kappa calibration against a fixed golden set is the mitigation, but it requires maintaining that set
- **Pass rate masks consequence distribution** — a 99% pass rate with 1% of failures being catastrophic is worse than a 95% pass rate with only minor failures; weight eval assertions by impact
- **Agent looping is the top production failure mode in 2026** — eval harnesses that measure output quality miss loops entirely; track token budget per trial and instrument loop detection in the harness, not just the agent
