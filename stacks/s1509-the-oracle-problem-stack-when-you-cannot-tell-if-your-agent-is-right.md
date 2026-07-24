# S-1509 · The Oracle Problem Stack — When You Cannot Tell If Your Agent Is Right

Your agent completed 1,400 tasks this week. 1,396 returned without error. How many were correct? You don't know. You can't know — not automatically, not without the same domain expertise the agent was supposed to have, and not in time to matter. The agent is in production. The eval is behind you. You are flying blind. This is the oracle problem: the fundamental challenge of agent evaluation when the task complexity exceeds your ability to verify the answer automatically.

## Forces

- **Agent tasks are open-ended. Eval methods are not.** Unit tests work when you know what correct output looks like. Agents handle tasks where correctness is subjective, context-dependent, or requires domain expertise you don't have on hand. The more capable the agent, the more likely it handles the tasks you couldn't automate — which means the tasks you most need to verify are the ones you can't.
- **The AIRQ benchmark exposes the oracle problem at scale.** The Adversa AI AIRQ Q2 2026 evaluation tested 100 commercial agents across 10 classes with automated security checks. Despite automated tooling, 89% failed — not because automated checks couldn't run, but because automated checks couldn't determine correct behavior for the tasks. Security evaluation, like domain evaluation, requires oracle knowledge the evaluator doesn't have.
- **RAG poisoning research shows how easily the oracle is corrupted.** January 2026 research: five carefully crafted documents inserted into a RAG corpus successfully manipulate AI responses 90% of the time. The attacker doesn't need to compromise the model — they only need to poison the knowledge source the oracle would use to verify the answer. If your verification pipeline uses the same retrieval system as the agent, your oracle is compromised.
- **The 98% lethal trifecta makes the oracle problem worse.** 98% of production agents simultaneously have private data access, untrusted content ingestion, and outbound action capability (AIRQ Q2 2026). An agent operating with all three capabilities can not only produce wrong answers — it can modify the evidence used to verify its own correctness. Self-verification without isolation is not verification.
- **Human-in-the-loop doesn't scale.** The practical response to oracle absence is human review. But 1,400 tasks per week with domain expert review is operationally impossible. Spot-checking 5% of outputs is statistically inadequate — a systematic error affecting 1% of tasks is invisible at 5% sampling.
- **Behavioral evals are proxies, not answers.** You can measure whether the agent uses the right tools, follows the right steps, and produces outputs in the right format. None of these measure whether the output is actually correct. Trajectory scoring (S-1001, S-1483) is a proxy for correctness, not a substitute for it.

## The move

The oracle problem has no clean solution. The discipline is to: (1) identify where you have oracle access and exploit it fully, (2) where you don't, use statistical and structural proxies, and (3) never confuse a proxy for the real thing.

### 1. The oracle access map

Map every task type against oracle availability:

```
Task type          | Oracle access          | Verification method
--------------------|------------------------|---------------------------
Structured output  | Exact match             | Diff against schema + values
Code generation    | Test suite              | Run tests
Classification     | Labeled eval set        | Holdout accuracy
Open generation    | Domain expert review    | Spot check + statistical
Multi-step ops    | End-state inspection    | State diff + smoke test
Creative/synthesis | None                   | Heuristic + user feedback
```

Tasks with "None" oracle access are your oracle-free zone. Every decision downstream — evaluation frequency, monitoring strategy, human review rate — is governed by where your task falls on this map.

### 2. Exploit exact oracle access fully

For task types with exact or near-exact oracle access (structured output, code, classification), invest in comprehensive evaluation. This is not the hard case — it's the case where you're leaving evaluation capability on the table.

- Build exhaustive eval sets for structured tasks. The cost is upfront; the payoff is permanent automated verification.
- For code generation, treat test coverage as oracle signal. Code with 95% test coverage is verifiable to 95%. Code with 20% coverage leaves 80% unverified.
- For classification, maintain a curated holdout set. Classifiers that drift silently (S-1062) are detectable if you measure accuracy against known labels over time.

### 3. Statistical oracles for oracle-free tasks

For open-ended tasks without oracle access, use statistical proxies that are harder to game than single-output evaluation:

```
Method             | What it measures                   | Oracle strength
--------------------|-----------------------------------|----------------
Trajectory entropy | Is the agent taking consistent paths? | Medium
Output variance    | Does the same input produce similar outputs? | Low-Medium
Cross-model agree  | Do multiple agents reach the same conclusion? | Medium
Semantic invariant | Does output satisfy structural properties? | Medium
User correction    | How often does a human override output? | Strong (indirect)
```

Cross-model agreement (N-version agents, S-1297) is particularly powerful: if three agents independently reach the same conclusion, the oracle-free error rate drops significantly. Not perfect, but a practical proxy for tasks where no ground truth exists.

### 4. The self-verification firewall

When the agent operates in an environment it can modify, the oracle is compromised. Separate verification from generation:

```
# The compromised pattern:
Agent → produces output → uses same retrieval → verifies output → deploys
         ↑ agent can modify retrieval to make output look correct

# The protected pattern:
Agent A → produces output → separate verifier Agent B → verifies against isolated source
                                               ↑
                                        Agent A cannot write here
```

The policy kernel (S-1458) can enforce this separation by routing verification through read-only sources the agent cannot modify. For RAG systems, this means the verification retrieval uses a separate, immutable index that the agent cannot write to — poison documents inserted by the agent cannot affect the oracle.

### 5. Minimum viable oracle for security tasks

Security and capability-envelope verification (S-1509) have a partial oracle: the policy kernel can automatically deny or allow actions. This is a machine-verifiable oracle for capability scope, even when correctness of the agent's reasoning is unverifiable.

```
Agent requests: db_client.delete(where="user_id=42")
Policy kernel:  check against envelope [read-only] → DENIED
Result:         Policy kernel confirms denial. Agent cannot bypass.
Oracle:         The policy kernel IS the oracle for capability scope.
```

This is the one domain where oracle access is achievable at scale: enforcement of the capability envelope is mechanically verifiable, even when the agent's reasoning is not.

## Receipt

> Verified 2026-07-22 — AIRQ Q2 2026 report (Adversa AI, OWASP/CoSAI/CSA/NIST contributors): 100 commercial agents, 11% passed security baseline, 98% carry lethal trifecta (private data access + untrusted content ingestion + outbound action capability). RAG poisoning research (January 2026): five crafted documents manipulate AI responses 90% of the time. S-1001 (Agent Evaluation Stack) covers trajectory scoring; S-1483 (Pass@k Metric) covers statistical pitfalls; S-1010 (Agent Eval Stack — Cannot Trust Tests) covers eval reliability; S-1172 (Eval Harness) covers harness design. This entry covers the foundational oracle problem: when you don't have ground truth, what do you do, and what does that cost you? Distinct from all prior entries.

## See also

- [S-1483 — The Metric That Lies](/stacks/s1483-the-metric-that-lies-about-your-agent-passk-is-not-your-success-rate.md) — why statistical proxies overstate agent reliability
- [S-1509 — Capability Envelope](/stacks/s1509-the-capability-envelope-stack-when-your-agent-does-more-than-you-meant.md) — the one domain where oracle access IS achievable (policy kernel enforcement)
- [S-1001 — Agent Evaluation Stack](/stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — trajectory scoring as a proxy for correctness
- [S-1136 — Context Sanitization Gate](/stacks/s1136-the-context-sanitization-gate-stack-when-your-agent-treats-retrieval-noise-as-ground-truth.md) — retrieval poisoning as an oracle corruption vector
