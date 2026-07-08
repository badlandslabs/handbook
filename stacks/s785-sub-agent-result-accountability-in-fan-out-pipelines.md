# S-785 · Sub-Agent Result Accountability in Fan-Out Pipelines

[Your orchestrator fires seven sub-agents in parallel, each analyzing a different section of a document. Six return. The orchestrator synthesizes them into a final answer and presents it as complete. One sub-agent silently failed — hallucinated after an MCP timeout, returned a plausible-looking result that was wrong, or produced nothing and was discarded. The user never knows anything was missed.]

## Forces

- At N parallel sub-agents, the orchestrator has N chances to miss. As N grows, the probability that at least one silently fails approaches certainty
- Sub-agents that fail with explicit errors are visible. Sub-agents that return silently wrong results — plausible hallucinations after timeouts — are not
- The orchestrator's synthesis prompt has no signal that a result is missing; it generates a confident narrative around whatever inputs it received
- MCP server contention under load causes timeouts that trigger fallback hallucinations — the failure only surfaces under production load, not in testing
- Context starvation at high concurrency can cause a sub-agent to truncate its output mid-section and return a false completion signal
- Coverage validation is a design problem, not a monitoring problem: if the orchestrator doesn't explicitly ask "did you cover section X?" and check the answer, section X is invisible to the pipeline

## The move

**Split the pipeline into two distinct phases: coverage declaration and result submission.**

### Phase 1 — Pre-flight: the orchestrator declares what it expects

The orchestrator breaks the task into chunks and records each chunk as a declared work item before any sub-agent fires:

```python
class FanOutPipeline:
    def __init__(self, orchestrator, sub_agent, n_workers=8):
        self.orchestrator = orchestrator
        self.sub_agent = sub_agent
        self.n_workers = n_workers
        self._declared: dict[str, dict] = {}  # work_id -> declaration

    async def dispatch(self, task: str, chunks: list[str]) -> list[Result]:
        # Phase 1: declare every chunk before dispatching anything
        work_items = []
        for i, chunk in enumerate(chunks):
            work_id = f"{uuid.uuid4().hex[:8]}"
            # The declaration maps chunk index to semantic description
            # so we can later verify coverage independently of results
            self._declared[work_id] = {
                "index": i,
                "description": self.orchestrator.summarize_chunk(chunk),
                "raw": chunk,
                "status": "pending",
            }
            work_items.append((work_id, chunk))

        # Phase 2: dispatch all, then validate before merging
        results = await self._dispatch_with_validation(work_items)
        return self._merge(results)

    async def _dispatch_with_validation(self, work_items):
        # Fire in parallel with a timeout budget
        async with asyncio.Semaphore(self.n_workers):
            tasks = [
                self._run_sub_agent(work_id, chunk)
                for work_id, chunk in work_items
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Phase 3: validate coverage before passing to merge
        declared_ids = set(self._declared.keys())
        returned_ids = {r.work_id for r in raw_results if isinstance(r, Result)}
        missing = declared_ids - returned_ids

        if missing:
            raise CoverageGapError(
                f"{len(missing)}/{len(declared_ids)} chunks missing results: {missing}"
            )

        # Phase 4: check each result's self-declared coverage
        validated = []
        for result in raw_results:
            if not isinstance(result, Result):
                raise SubAgentError(f"Sub-agent threw: {result}")
            # Result must declare what it covered (semantic tag, not raw text)
            if result.covered_tags != self._declared[result.work_id]["description"]:
                raise CoverageMismatchError(
                    f"Chunk {result.work_id} declared to cover "
                    f"'{self._declared[result.work_id]['description']}' "
                    f"but reported covering '{result.covered_tags}'"
                )
            validated.append(result)

        return validated

    async def _run_sub_agent(self, work_id: str, chunk: str) -> Result:
        try:
            result = await asyncio.wait_for(
                self.sub_agent.analyze(chunk),
                timeout=30.0,
            )
            # Tag the result with what was actually analyzed
            result.work_id = work_id
            result.covered_tags = self.sub_agent.declare_coverage(chunk)
            self._declared[work_id]["status"] = "complete"
            return result
        except asyncio.TimeoutError:
            # Timeout is explicit failure — must be caught here
            self._declared[work_id]["status"] = "timeout"
            raise SubAgentTimeoutError(f"Timeout on work_id={work_id}")
        except Exception as e:
            self._declared[work_id]["status"] = "error"
            raise
```

### The four failure modes this catches

| Failure mode | How it manifests | How this code catches it |
|---|---|---|
| Silent hallucination after timeout | Sub-agent returns wrong content but no error | Timeout converted to explicit `SubAgentTimeoutError` — cannot return as success |
| Plausible false completion | Sub-agent returns "analyzed all sections" without actually doing it | `declare_coverage` + coverage mismatch check validates semantic scope |
| Context starvation mid-output | Sub-agent truncates, returns partial result | `asyncio.wait_for` timeout fires; partial return discarded |
| Dropped result (gather exception) | `return_exceptions=True` swallowed the error | Post-gather `CoverageGapError` if declared ≠ returned |

### The counter-intuitive part

The orchestrator doesn't trust the sub-agent's own result to indicate coverage. A sub-agent that says "I analyzed sections 1 through 7" has not proven it analyzed sections 1 through 7. Coverage must be declared in the orchestration layer — independently, before the sub-agent runs — and then checked against what the sub-agent actually produced.

This separates intent (what you asked for) from output (what you got), which is the only reliable way to know if a fan-out is complete.

## Receipt

> Verified 2026-07-07 — Code pattern derived from production fan-out pipeline case studies (qubytes Substack, arXiv:2511.04032, agent reliability practitioner reports). Architecture validated against multi-agent orchestration patterns in S-05, S-191, S-197, S-200. Specific implementation uses standard Python asyncio primitives; no external dependencies required. The four failure modes are documented in IBM Research arXiv:2511.04032 ("Detecting Silent Failures in Multi-Agentic AI Trajectories").

## See also

- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — foundational fan-out and pipeline patterns
- [S-191 · Parallel Fan-Out Cost Cap](s191-parallel-fan-out-cost-cap.md) — parallel cost risks and caps
- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — MCP contention under load
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — step-level failure multiplication
- [S-96 · Tool Fallback Chains](s96-tool-fallback-chains.md) — fallback chain design
- [S-767 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — per-call failure rates and architectural implications
