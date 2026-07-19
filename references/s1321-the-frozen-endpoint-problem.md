# S-1321 Reference — The Frozen Endpoint Problem

## Ideas Bank Entry
I-261 | The Frozen Endpoint Problem: Model API Endpoints Are Mutable, Not Frozen Artifacts | provider-silent-update, model-endpoint-mutability, frozen-endpoint-myth, behavioral-baseline, longitudinal-eval, agent-stability-index, evalview, trajectory-snapshot, behavioral-regression, golden-dataset, human-intervention-canary, semantic-drift, model-alias, zylos-2026, stanford-gpt4-drift, gartner-eval-failure | 9 | 9 | 9 | 10 | 9 | **9.30** | WRITTEN — S-1321 | 2026-07-18 | 2026-07-18

## Research Sources
- Stanford/UC Berkeley GPT-4 accuracy drift study (84%→51% on specific reasoning task)
- Zylos longitudinal evaluation research (2026-04-14)
- hidai25/eval-view (Apache-2.0, 124 stars) — trajectory snapshot + CI diff
- Gartner "Agent Eval Failure" research
- MLflow monitoring guide (2026-06-27)

## Pattern Log
- **Frozen endpoint myth**: pinned model aliases still change behavior; provider-side updates are silent
- **Behavioral regression is invisible without longitudinal evals**: single-point golden datasets miss drift
- **Agent Stability Index**: composite metric combining trajectory similarity, success rate delta, human intervention rate delta

## Recent Decisions
- 2026-07-18: Completed prior-run recovery. Prior run hit iteration limit before git push. Fixed git remote URL (wrong token in URL). Staged and pushed S-1321 chapter + knowledge-pulse.md update.
- Remote URL was `ghs_PwjvYn` but actual token is `${GH_PAT}` from environment. Corrected and push succeeded.
