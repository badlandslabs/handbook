# S-1377 · The LLM-as-Judge Stack: When Your Eval Is Biased in Favor of Itself

You have automated agent quality checks. You run LLM-as-judge evaluations on every commit. The scores look healthy. Then you notice your Claude-judge keeps ranking Claude-agent outputs higher, your GPT-judge favors GPT-agent outputs, and verbose agents always score higher than concise ones regardless of correctness. Your eval is lying to you.

## Forces

- **Judge models have measurable self-preference bias.** GPT-4 consistently assigns higher scores to its own outputs over equally-good outputs from other models — the bias is statistically significant and persists across domains (Wataoka et al., NeurIPS 2024).
- **LLM judges favor longer responses.** Verbosity bias means judges trained on human preference data reward thoroughness over correctness — a broken agent that over-explains its mistakes can outscore a correct but terse one.
- **You need judgment for open-ended tasks, but judgment is biased.** Deterministic checks catch exact tool names and API errors. Everything else — did the plan make sense? was the response helpful? — requires a judge, and that judge has preferences.
- **Cross-model evaluation amplifies bias.** Using a proprietary judge (GPT-4o) to evaluate open-source agents creates an inherent asymmetry: the judge optimizes for outputs that resemble its own training distribution.

## The move

Use LLM-as-judge at the right level of the stack, with safeguards against its documented failure modes.

- **Segment eval types by determinism.** Use exact-match, regex, and JSON-schema checks for tool names, API response codes, and structured outputs — these never need a judge. Reserve LLM-judge for answer quality, plan coherence, and multi-turn conversational appropriateness.
- **Calibrate the judge against human ground truth.** Before running production evals, give your judge a set of 20-50 human-labeled examples and measure agreement rate. A judge that disagrees with humans on calibration data will disagree on everything else.
- **Use pairwise comparisons with balanced position swapping.** When comparing agent A vs. agent B, evaluate each pair twice: A-first then B-first. Average the scores. This eliminates order-preference bias (a known LLM failure mode in pairwise ranking).
- **Distill a small judge model for latency-sensitive use cases.** Large proprietary judges (GPT-4o, Claude 3.7 Sonnet) are used for high-stakes verification. For inline CI checks, distilling a smaller model (e.g., Llama-3.1-8B-Instruct) on your specific rubric cuts latency from seconds to milliseconds with acceptable accuracy loss.
- **Isolate the judge model from the agent model.** Never use the same model family as both agent and judge. A Claude-judge evaluating a Claude-agent will systematically inflate scores. Cross-family evaluation (e.g., GPT-judge evaluating Claude-agent) reduces self-preference bias measurably.
- **Run trace-level scoring, not just output scoring.** Evaluate the full trajectory: did the agent call the right tools in the right order? Did it recover from errors? An agent that reaches the correct answer via a broken plan is still a failure even if its final answer is right.

## Evidence

- **Research paper (arXiv):** GPT-4 exhibits the highest self-preference bias among evaluated LLMs, followed by Vicuna-13b. The bias is measurable via demographic-parity metrics and confounds pairwise comparison evaluations unless controlled. — [Self-Preference Bias in LLM-as-a-Judge (Wataoka et al., arXiv:2410.21819)](https://arxiv.org/html/2410.21819v2)
- **HN discussion:** A practitioner building production AI systems observes that LLM-as-critic evaluations are "vital for improving performance" but lacks "empirical evidence" in the community — calls for trace-based eval loops where context data becomes training data and eval traces become labeled test sets. — [Hacker News, comment on "Principles for production AI agents" (HN id 44715163)](https://news.ycombinator.com/item?id=44715163)
- **Framework documentation (LangChain):** LangSmith's AgentEvals provides deterministic matching (exact tool names, regex) alongside LLM-as-judge evaluators. The docs explicitly recommend using both in combination — deterministic checks for "did it call the right tool?" and judge-based for "did it call the tool correctly given the context?" — [LangChain Agent Evals documentation](https://docs.langchain.com/oss/python/langchain/test/evals)
- **Framework comparison (Technspire 2026):** Three evaluation frameworks dominate production teams: DeepEval (pytest-native, open-source, strong for agent-trace evals), Promptfoo (YAML-first, language-agnostic CI integration), and LangSmith (observability-first, hosted). Each targets a different team composition — Python-first CI teams use DeepEval; cross-language teams use Promptfoo; trace-heavy teams use LangSmith. — [Technspire: Agent Evaluation in 2026: DeepEval vs Promptfoo vs LangSmith](https://technspire.com/en/blog/agent-evaluation-2026-deepeval-promptfoo-langsmith)
- **Engineering blog (data scientist):** The "evals as test data" mental model: collect agent traces from production, manually label failure cases, and build a golden dataset. Context data → in-context learning; eval traces → test dataset. This mirrors traditional ML where training data and test data are separate. — [Hacker News, "The revenge of the data scientist" thread (HN id 47606451)](https://news.ycombinator.com/item?id=47606451)

## Gotchas

- **Do not use LLM-as-judge to evaluate a judge.** Using GPT-4o to evaluate whether your GPT-judge is calibrated compounds bias. Calibrate against human-labeled data, not another model.
- **Single-judge evaluations are not sufficient for high-stakes agents.** A 2026 emergentmind survey found that over half of production agent teams use a judge LLM at runtime for quality gating, but those same teams report that offline eval scores diverge from production behavior by 15-25% on average. Always supplement with canary deployment and human spot-checks.
- **Prompt the judge differently than you prompt the agent.** The judge's rubric should be explicit and structured (e.g., score 1-5 on criteria X, Y, Z with definitions). Open-ended judge prompts inherit the same verbosity bias they are meant to correct. Use few-shot examples in judge prompts to anchor criteria.
- **Do not conflate trajectory length with trajectory quality.** An agent that takes 20 tool calls and lands on the correct answer is worse than one that takes 3 — for the same reason code with extra steps is worse than code that directly solves the problem. Include step-count efficiency in your eval rubric.
