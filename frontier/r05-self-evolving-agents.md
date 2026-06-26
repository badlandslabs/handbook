# R-05 · Self-Evolving Agents

The research frontier of agents that get *better* at their job over time — not just agents that do the job. Today almost every deployed agent is frozen after launch; this is where that changes.

## Forces
- Most agents are static: fixed prompts, fixed tools, frozen at deploy — they repeat the same mistakes forever
- Letting an agent change itself risks it evolving in the *wrong* direction, silently
- Learning from experience needs memory that compounds, which is its own unsolved problem ([S-09](../stacks/s09-memory-systems.md))
- The powerful forms (runtime self-modification) are the least proven and the hardest to make safe

## The move

- **Name the divide.** "An agent that does tasks" vs. "an agent that gets better at tasks." Be clear which one you're building — most production systems are, and should be, the first.
- **Know what can evolve.** One survey frames four targets: System Inputs, the Agent System (prompts / tools / workflow), the Environment, and the Optimiser that drives the change. Improvement gets stored as memory in three shapes — episodic (what happened), semantic (facts learned), procedural (skills).
- **Ship the safe loop today.** The usable form is *offline*: collect real interaction traces, mine them for failures and lessons, edit the prompt/tools/examples, re-deploy. That's disciplined iteration — see [F-07](../forward-deployed/f07-evaluation-driven-development.md) — not magic, and it's most of the value.
- **Treat runtime self-rewrite as research.** Agents that rewrite their own logic mid-run (Gödel-machine style) are powerful and unproven. Don't put them near production yet.
- **Gate every change behind evals.** Whatever the mechanism, an evolution step only ships if it beats the current version on your eval suite, with a human rollback path. Self-improvement without a quality gate is just drift.

## Receipt
> Framing and the four-component model from ["A Comprehensive Survey of Self-Evolving AI Agents"](https://arxiv.org/abs/2508.07407) (arXiv 2508.07407) and ["A Survey of Self-Evolving Agents"](https://arxiv.org/abs/2507.21046) (arXiv 2507.21046, What/When/How/Where to Evolve). Runtime self-modification (Gödel-machine / HyperAgents, arXiv 2603.19461) is recent and research-grade — cited as a direction, not a recommendation. This is an emerging field as of mid-2026, not production practice; treat specific techniques as starting points for your own research. Verified 2026-06-25; not independently reproduced here.

## See also
[F-07](../forward-deployed/f07-evaluation-driven-development.md) · [S-09](../stacks/s09-memory-systems.md) · [R-04](r04-small-language-models.md) · [S-05](../stacks/s05-multi-agent-patterns.md) · [F-05](../forward-deployed/f05-agent-failure-taxonomy.md)

## Go deeper
Keywords: `self-evolving agents` · `self-improving agents` · `Gödel machine` · `lifelong learning` · `episodic memory` · `procedural memory` · `test-time memory evolution` · `experience replay` · `arXiv 2508.07407`
