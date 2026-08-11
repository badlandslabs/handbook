# S-2492 · The Evaluation Stack — When You Ship Blind and Wonder Why Production Breaks

When your agent works in dev but you have no way to know whether it's getting better or worse as you ship changes.

## Forces

- Agents are non-deterministic — the same input can produce different trajectories, so a single run is meaningless
- The final answer tells you almost nothing about whether the agent took a safe, efficient, or correct path to get there
- Human review doesn't scale to thousands of daily interactions, but automated metrics like BLEU/ROUGE miss real failure modes
- Public benchmarks don't translate to your specific tools, prompts, and retrieval setup — they measure model capability, not agent quality
- Lab benchmarks show a **37% performance gap** between curated scores and production outcomes, and **50x cost variation** for similar accuracy across agent configurations

## The move

**Start by defining success criteria as binary pass/fail, then build outward.**

1. **Define task success first.** Before measuring anything, define what "done" looks like per task type. Support agent: was the ticket resolved? Coding agent: did the tests pass and the build succeed? Without this, every metric you collect is noise.

2. **Eval the trajectory, not just the output.** The final answer is a small slice of what matters. A KAIST 2026 paper (arXiv:2510.02837) argues that evaluating reasoning trajectories — not just answers — captures efficiency, hallucination in intermediate steps, and adaptivity when tools fail. Agents with identical accuracy scores can have radically different reliability profiles.

3. **Run two eval modes.** Offline evals against curated datasets with known expected behavior during development; online evals against live production traces when monitoring for drift, regressions, and novel failure modes. Promoted cases (failing production traces) feed back into curated datasets.

4. **Use three grader types.** Deterministic assertions (did tool X receive the right parameter? did the output pass schema validation?), reference-based scoring (exact match or embedding similarity where ground truth exists), and LLM-as-judge for open-ended quality (alignment with policy, helpfulness, tone). LLM-as-judge is the industry's dominant approach: **53.3% of AI agent teams** use it, achieving **500x–5,000x cost reduction** over human review while maintaining ~80% human agreement on single-turn tasks.

5. **Track operational metrics as first-class targets.** Cost per task, latency per step, token efficiency, tool call success rate, and escalation frequency. These determine enterprise viability, not just quality.

6. **Look at the traces.** No amount of structured eval will replace manually inspecting agent traces to identify failure patterns, confusing prompts, or emergent behavioral issues. Evals narrow the search space; traces reveal what's actually happening.

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" (Jan 2026) establishes core vocabulary — task, trial, grader, transcript, outcome — and shows that offline dataset evals and online production monitoring require different grader types and data sources. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Industry survey:** InfoQ's "Evaluating AI Agents in Practice" (March 2026) reports hybrid evaluation combining automated scoring with human judgment is non-negotiable for production; standard NLP benchmarks fail because agents are systems, not models. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **Production case study:** A principal ML engineer's guide (Dec 2025) documents the real gap between "works in demo" and production: cost 3x budget, loops, contradictory outputs — and prescribes defining success criteria before writing any tests. — [ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide)

- **Research paper:** KAIST/Yonsei "TRACE" framework (arXiv:2510.02837, May 2026) demonstrates that evaluating reasoning trajectories — not just final answers — reveals efficiency, hallucination, and adaptivity gaps invisible to answer-matching benchmarks. — [arxiv.org/pdf/2510.02837](https://arxiv.org/pdf/2510.02837)

- **LLM-as-judge analysis:** Vadim's blog compiles empirical data: 53.3% production adoption, 500x–5,000x cost reduction vs. human review, ~80% human agreement on single-turn, ~65% on multi-turn. Documents known biases: verbosity preference (~70% for GPT-4), position bias (10–30% verdict flip when order swapped), and self-preference (Claude rates own outputs ~25% higher). — [vadim.blog/llm-as-judge](https://vadim.blog/llm-as-judge)

- **Framework:** DeepEval (GitHub, active OSS) provides agentic-specific metrics: Task Completion, Tool Correctness, Plan Quality — grounded in the G-Eval framework. — [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)

## Gotchas

- **LLM-as-judge has known biases.** Verbosity preference (GPT-4 prefers longer responses ~70% of the time), position bias (swapping output order flips verdict 10–30%), and self-preference (models rate their own outputs higher). Calibrate with human-annotated samples before trusting scores.
- **Public benchmarks measure model capability, not your agent.** SWE-bench, WebArena, and similar measure what the base model can do in isolation. They don't account for your specific tools, retrieval pipeline, prompt engineering, or session state management. Use them for model selection, not agent quality.
- **Evals go stale.** As agents evolve, eval datasets accumulate "known failures" that no longer reflect reality. Audit and trim eval suites regularly — ideally every sprint or on every significant prompt change.
- **A score by itself is just a number.** Eval results must change what ships — either by promoting failing traces to the dataset, triggering a prompt fix, or blocking a deploy. An eval that nobody looks at is worse than no eval.
