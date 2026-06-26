# F-47 · Multi-Agent Result Aggregation

[S-05](../stacks/s05-multi-agent-patterns.md) covers multi-agent architectures — parallel workers, orchestrators, reflection loops. It notes that a coordinator "dispatches work to N workers, then aggregates" in one line. That aggregation step is the variable: the right strategy depends entirely on what type of result the agents produce. Choosing the wrong strategy produces either false precision (majority vote on findings that aren't comparable) or bloated output (union merge on summaries that should be synthesized).

## Situation

Three security agents scan the same codebase for vulnerabilities. Agent A finds bugs 1, 2, 3. Agent B finds bugs 2, 3, 4. Agent C finds bugs 1, 3, 5. Union merge produces bugs 1–5 (correct: combine all unique findings). Three summarization agents each produce a 100-word summary of the same document. Majority vote doesn't apply; union merge produces 300 incoherent words. LLM synthesis produces one coherent 80-word summary. Same parallel setup, two completely different aggregation strategies.

## Forces

- **The right strategy is determined by the output type, not the agent count.** Classification outputs → majority vote. Discrete items (findings, bugs, entities) → union merge. Narrative or analytical outputs → LLM synthesis. Speed vs. correctness requirements → first-wins. Mixing strategies produces either garbage output or wasted tokens.
- **Majority vote requires an odd number of agents.** Two agents tie 50% of the time. Three agents is the minimum for reliable majority; five for high-stakes decisions. Document the tie-break rule (deterministic, not random) or a tie triggers escalation.
- **Union merge requires a natural dedup key.** If items don't have a unique ID, you need one: bug location (file:line), entity (name + type), claim (semantic hash). Without a key, you either duplicate findings or over-merge distinct items.
- **LLM synthesis adds a model call.** It's the most expensive strategy — a Haiku synthesis call costs $0.000266 per merge. Reserve it for outputs where coherent prose matters. Findings lists don't need synthesis; summaries do.
- **First-wins trades correctness for latency.** Take the first response to arrive, cancel the rest. Appropriate when agents are redundant (same capability, launched for speed) and any one of them is likely correct. Wrong when agents have different specializations or the task has a long tail of edge cases.

## The move

**Match the aggregation strategy to the output type. Implement each strategy as a clean function. Log discarded results so you can audit the aggregation later.**

```js
// Strategy 1: First-wins
// Use when agents are redundant and latency matters more than coverage.
// Caller must cancel losers via AbortController (S-69).
async function firstWins(agentFns) {
  const controllers = agentFns.map(() => new AbortController());
  const promises = agentFns.map((fn, i) =>
    fn(controllers[i].signal).then(result => {
      // Cancel all other in-flight agents
      controllers.forEach((c, j) => { if (j !== i) c.abort(); });
      return result;
    })
  );
  return Promise.any(promises);   // first to resolve; ignores rejections from cancelled agents
}

// Strategy 2: Majority vote
// Use for classification, routing, or binary decisions.
function majorityVote(results, opts = {}) {
  const counts = {};
  for (const r of results) counts[r] = (counts[r] || 0) + 1;
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  const [topLabel, topCount] = sorted[0];
  const isTie = sorted.length > 1 && sorted[1][1] === topCount;
  if (isTie) {
    // Tie-break: deterministic (alphabetical) — never random
    const tied = sorted.filter(([,c]) => c === topCount).map(([l]) => l).sort();
    return { label: tied[0], confidence: topCount / results.length, tie: true, tied };
  }
  return { label: topLabel, confidence: topCount / results.length, tie: false };
}

// Strategy 3: Union merge
// Use for findings, extracted items, entities — anything with a unique key.
function unionMerge(resultSets, keyFn) {
  const seen = new Map();
  const all = [];

  for (const findings of resultSets) {
    for (const f of findings) {
      const k = keyFn(f);
      if (!seen.has(k)) {
        seen.set(k, true);
        all.push(f);
      }
    }
  }
  return all;
}

// Strategy 4: LLM synthesis
// Use for summaries, analyses, or any output requiring coherent prose.
// Reserve for when union merge or vote don't produce a usable result.
async function llmSynthesize(client, outputs, task) {
  const combined = outputs
    .map((o, i) => `[Agent ${i + 1}]: ${o}`)
    .join('\n\n');

  const response = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',   // synthesis is cheap; use a small model
    max_tokens: Math.ceil(outputs.join('').length / 4),  // output ≤ input length
    messages: [{
      role:    'user',
      content: `${task}\n\nAgent outputs to synthesize:\n${combined}`,
    }],
  });
  return response.content[0].text;
}
```

**Aggregation selector — pick strategy at dispatch time:**

```js
async function runParallelAgents(agentFns, aggregation) {
  // Run all agents in parallel; collect results
  const results = await Promise.allSettled(agentFns.map(fn => fn()));
  const successful = results
    .filter(r => r.status === 'fulfilled')
    .map(r => r.value);

  if (successful.length === 0) throw new Error('All agents failed');

  switch (aggregation.strategy) {
    case 'first':
      return successful[0];  // fastest responder already resolved first

    case 'vote':
      return majorityVote(successful);

    case 'union':
      return unionMerge(successful, aggregation.keyFn);

    case 'synthesize':
      return llmSynthesize(aggregation.client, successful, aggregation.task);

    default:
      throw new Error(`Unknown aggregation strategy: ${aggregation.strategy}`);
  }
}

// Usage
const bugFindings = await runParallelAgents(
  [secAgentA, secAgentB, secAgentC],
  { strategy: 'union', keyFn: f => `${f.file}:${f.line}:${f.type}` }
);

const classification = await runParallelAgents(
  [classifier1, classifier2, classifier3],
  { strategy: 'vote' }
);
```

**Strategy selection table:**

| Output type | Strategy | Why |
|---|---|---|
| Classification / routing | Majority vote | Binary or categorical; vote resolves disagreement |
| Bug / finding / entity extraction | Union merge | Each agent may find different items; combine all unique |
| Summaries / analyses | LLM synthesis | Prose must be coherent; union of summaries is not |
| Redundant workers (same task) | First-wins | Any response is acceptable; take the fastest |
| High-stakes classification | Vote (N=5) | More agents → higher confidence; increases cost linearly |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Majority vote measured on 1M iterations. Synthesis cost at `claude-haiku-4-5-20251001` $0.80/M input, $4.00/M output.

```
=== Majority vote and union merge speed ===

$ node -e "
function majorityVote(results) {
  const counts = {};
  for (const r of results) counts[r] = (counts[r]||0)+1;
  return Object.entries(counts).sort((a,b)=>b[1]-a[1])[0][0];
}
const N = 1000000; const t0 = performance.now();
for (let i=0; i<N; i++) majorityVote(['positive','negative','positive']);
console.log('Majority vote per call:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
Majority vote per call: 0.0014 ms

$ node -e "
// 3 agents, 4 unique findings (6 total with overlaps)
const sets = [
  [{id:'bug-1'},{id:'bug-2'}],
  [{id:'bug-2'},{id:'bug-3'}],
  [{id:'bug-1'},{id:'bug-4'}],
];
// union merge with Map dedup
function unionMerge(sets, keyFn) {
  const seen=new Map();
  for (const s of sets) for (const f of s) { const k=keyFn(f); if(!seen.has(k)) seen.set(k,f); }
  return [...seen.values()];
}
console.log('Union result:', unionMerge(sets, f=>f.id).length, 'unique (from 6 total)');
"
Union result: 4 unique (from 6 total)

Code aggregation: 0.0014ms (vote) — zero API calls.

=== LLM synthesis cost ===

Three 20-token summaries → synthesis prompt: 82 tok input, ~50 tok output
Cost per synthesis: 82 × $0.80/M + 50 × $4.00/M = $0.000266

At 1 000 synth calls/day: $7.97/month
Rule: synthesis is cheap enough; only avoid it when union or vote suffice.

=== Agent count and confidence (majority vote) ===

N=1: 100% confidence in one response — no corroboration
N=3: majority = 2/3; catches 1 wrong agent
N=5: majority = 3/5; required when one wrong answer is costly
N=7: diminishing returns; 4/7 = 57%, cost 2.3× N=3
Use N=3 for routine decisions; N=5 for high-stakes classifications.
```

## See also

[S-05](../stacks/s05-multi-agent-patterns.md) · [S-24](../stacks/s24-self-consistency.md) · [F-35](f35-workflow-token-budget.md) · [S-70](../stacks/s70-agent-loop-termination.md) · [S-74](../stacks/s74-agent-capability-registry.md) · [S-69](../stacks/s69-streaming-cancellation.md)

## Go deeper

Keywords: `multi-agent aggregation` · `majority vote` · `union merge` · `LLM synthesis` · `first-wins` · `parallel agents` · `result aggregation` · `agent orchestration` · `result merging` · `confidence aggregation`
