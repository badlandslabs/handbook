# S-2110 · The Measured Agent Stack

When you ship on Monday, the agent passes its demo. You ship on Tuesday. By Friday you're getting bug reports nobody can reproduce, cost bills nobody predicted, and a growing pile of vague user complaints. Nobody measured anything. You have no baseline, no signal, no idea if Friday's change made things better or worse. Shipping without evaluation is flying blind with a pretty cockpit.

## Forces

- **Benchmarks lie to you.** Public benchmarks (SWE-bench, GAIA, WebArena) measure narrow, curated capabilities. They tell you if your agent is better than average at toy tasks — not whether it reliably does the thing your users pay for.
- **Agents are non-deterministic.** Unlike traditional software, the same input can produce different outputs. A single test run proves nothing. You need distribution over trials, and that multiplies cost and complexity fast.
- **Outcome ≠ reasoning quality.** An agent can get the right answer through the wrong chain of thought and fail spectacularly on the next edge case. Task success rate alone is a liar.
- **Evals are the hardest part.** Practitioners consistently report that writing good evaluations is harder than building the agent itself. The benchmark toy is fun; the eval craft is the real work.
- **LLM-as-judge has a taste problem.** Judges can score surface quality reliably but can't assess whether the agent had good judgment — whether it refused appropriately, recovered cleanly, or handled ambiguity with appropriate caution.

## The move

Stop treating evaluation as a gate between development and production. Build it as a continuous loop that feeds back into design.

- **Define success by the observable outcome, not the agent's self-report.** The transcript says "refund processed" — but did the database actually update? Verify the world changed, not just the chat bubble.
- **Run multiple trials per task.** Agents are stochastic. Report distributions, not point estimates. A 70% pass rate over 10 runs is meaningfully different from 70% on a single run.
- **Layer your metrics.** Task success (did it finish correctly), error recovery (did it bail gracefully or spiral), latency/cost (p95 step time, tokens per task), and user satisfaction (completion rate, thumbs-up density) together give a picture no single metric captures.
- **Build private evals from production traces.** Curate failing and edge-case production interactions into golden datasets. These are the test cases that matter — not the ones in a public benchmark.
- **Use LLM-as-judge as a signal amplifier, not a verdict.** Train a calibrated judge on your domain's criteria. Target 0.80+ Spearman correlation with human judgment before trusting it. A raw judge without calibration gives you confident wrong answers.
- **Wire evals into CI/CD.** Run evaluation suites on every commit, on a schedule, and on release candidates. A test that runs only when you remember to run it is not a test.

## Evidence

- **Anthropic engineering post:** Claude Code's development started with fast iteration from user feedback, then added evals — first for narrow areas like concision and file edits, then for complex behaviors like over-engineering. Evals helped identify issues, guide improvements, and focus research-product collaboration. Key finding: "Absent evals, debugging is reactive." — [Anthropic / Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), Jan 2026
- **State Farm engineering post:** Deployed LLM-as-judge at scale to cover thousands of daily interactions that manual review couldn't touch (<1% coverage). Built a grader LLM that receives the interaction transcript plus plain-English evaluation criteria, then returns a score and explanation. Key finding: BLEU/ROUGE require reference answers and can't assess semantic correctness; a judge LLM can evaluate meaning, not just wording. — [State Farm Engineering / Grading the Machine](https://engineering.statefarm.com/grading-the-machine-using-llm-as-a-judge-to-monitor-ai-agents-in-production-25a071db9c50), Jun 2026
- **YC Launch — ZeroEval:** Built calibrated LLM judges that improve over time by learning from production data and incorrect samples. Current static judges lack context on how they fail — a calibrated judge that sees more of the failure distribution becomes more reliable. — [Y Combinator Launch / ZeroEval](https://www.ycombinator.com/launches/OEC-zeroeval-build-self-improving-agents), ~12 months ago

## Gotchas

- **Public benchmark scores are marketing, not measurement.** Don't let a high SWE-bench score convince you the agent is production-ready. It means the agent is good at SWE-bench problems.
- **A passing eval proves capability, not reliability.** One clean run against a golden dataset doesn't tell you the probability of failure on the next run. You need trial distributions.
- **LLM judges hallucinate too.** An uncalibrated judge can give a high score to a subtly wrong answer. Always validate judge scores against human judgment on a sample before trusting the full automated pipeline.
- **Cost and latency tracking gets dropped.** Evals focused purely on quality ignore that a "perfect" agent that costs $4 per task and takes 3 minutes per step isn't deployable. Make operational constraints first-class evaluation targets.
- **Reproducibility failure is invisible.** If your eval environment doesn't match production (different tool versions, different API responses, different timing), passing evals mean nothing. The harness itself must be validated.
