# S-1512 · The Harness Engineering Stack — When Your Model Isn't the Problem, but Your Scaffolding Is

Your agent scores well on evals. Your prompt is tight. You switched from GPT-4o to Claude Sonnet 4 and saw no meaningful improvement. The terminal output still breaks on unusual file paths. The agent still loops when the API returns a non-JSON error. The tool still gets called with the wrong schema when the LLM hallucinates a parameter name. The model didn't fail — the harness did. And in 2026, the most productive engineering investment in any agent system is not a better model. It is a tighter harness.

## Forces

- **The model ceiling is real, but the harness floor is lower.** Prompts plateau. Adding more examples, more instructions, more system prompt real estate delivers diminishing returns after a point. The remaining failure modes live in tool definitions, context delivery, feedback loops, and recovery paths — none of which model improvements fix.
- **"Harness" is everything that isn't the model.** Viv Trivedy's framing: if you're not the model, you're the harness. This is deliberately broad — and correctly so. Every decision about how the agent perceives, acts, recovers, and self-evaluates lives in the harness, not the weights.
- **LangChain improved from 30th to 5th on Terminal Bench 2.0 in March 2026 without touching the model.** The entire gain came from harness optimization: eval harness redesign, tool interface restructuring, and context policy tightening.
- **The harness is where Lusser's Law bites hardest.** A 90%-accurate model in a loose harness produces a 40%-reliable agent. Every soft boundary in the harness — permissive tool schemas, forgiving output parsers, missing rollback logic — converts model accuracy into system unreliability.

## The move

Harness engineering is the practice of treating the scaffolding around the model as a first-class engineering artifact: designed, versioned, tested, and optimized independently of the model. It operates across five layers.

### Layer 1 — Tool Interface Contract

The tool definition is the most leveraged part of the harness. It is the contract between the agent's decision and the external world's response.

```
# Loose: the agent can guess wrong parameter names and get a silent pass
# Bad tool definition
{
  "name": "read_file",
  "description": "Reads a file from the filesystem",
  "parameters": { "type": "object", "properties": { "path": { "type": "string" } }
}

# Tight: enum-constrained, semantics-clear, failure-mode-explicit
# Good tool definition
{
  "name": "read_file",
  "description": "Read the contents of a text file. Returns raw UTF-8 text. Fails with FILE_NOT_FOUND if path does not exist, PERMISSION_DENIED if unreadable, IS_BINARY if the file contains non-text bytes.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Absolute path to the file. Use / for root, ~/ for home directory.",
        "examples": ["/etc/hosts", "~/projects/agent/config.yaml"]
      },
      "max_bytes": {
        "type": "integer",
        "description": "Maximum bytes to read. Truncates if file exceeds. Defaults to 512KB.",
        "default": 524288
      }
    },
    "required": ["path"]
  }
}
```

The second version reduces hallucinated-parameter calls, makes error responses interpretable, and constrains the agent's reasoning about what the tool can and cannot do. Per aiagentsfirst.com's production data (May 2026): rewriting tool descriptions on one MCP server lifted task completion from 68% to 89% in a single afternoon. Schema mismatches account for 38% of all MCP server failures (12,000-trial study, aiagentsfirst.com).

### Layer 2 — Context Delivery Policy

Context is not just what you include — it is when, how, and at what cost you deliver it. The policy governs retrieval strategy, budget allocation, and eviction behavior.

```
class ContextDeliveryPolicy:
    """
    Tiered context delivery: hot / warm / cold.
    Hot: injected on every turn (system prompt, active session state).
    Warm: retrieved on threshold (semantic memory, project conventions).
    Cold: fetched on explicit request (documentation, past sessions).
    """
    def should_retrieve(self, query: str, session_state: dict) -> str:
        query_complexity = self.classify_complexity(query)
        session_depth = session_state.get("turn_count", 0)
        
        if query_complexity == "simple" or session_depth < 3:
            return "hot"       # Inline, no retrieval cost
        elif query_complexity == "medium":
            return "warm"      # Semantic search, top-3 results
        else:
            return "cold"      # Explicit fetch, full context window

    def classify_complexity(self, query: str) -> str:
        # Pattern-based classification; replace with LLM classifier in production
        trigger_words = {"debug", "architect", "refactor", "why", "explain"}
        return "cold" if trigger_words & set(query.lower().split()) else "medium"
```

### Layer 3 — Feedback Loop and Self-Evaluation Gate

The agent needs to know when it is wrong before the wrongness propagates. The feedback loop wraps every consequential action with a narrow verification step.

```
def verify_action(agent_output: dict, context: dict) -> VerificationResult:
    """
    Narrow-scope LLM-as-judge gate before high-stakes actions.
    Not a full re-run — a targeted question: does this output make sense
    given the input and the tool being called?
    """
    verification_prompt = f"""
    Task: {context['task']}
    Planned tool: {agent_output['tool']}
    Tool arguments: {agent_output['arguments']}
    Prior context: {context.get('recent_history', '')[:500]}
    
    Question: Does this tool call make sense for the task? 
    Answer YES, NO, or UNCERTAIN. If NO or UNCERTAIN, briefly explain why.
    """
    # ...
```

This is the architectural sibling of the runtime verification loop (S-1239) — the harness version lives in the scaffolding layer rather than the agent's own decision logic.

### Layer 4 — Recovery Path (Not Just Error Handling)

Error handling is "try again." Recovery is "understand what went wrong and try differently." The harness provides named recovery strategies:

```
RECOVERY_STRATEGIES = {
    "json_parse_error":     "parse_and_retry",    # Extract partial JSON, retry with fixed schema
    "tool_timeout":         "retry_with_backoff",  # 2x backoff, max 3 attempts
    "auth_error":           "escalate_human",      # Do not retry; alert operator
    "schema_mismatch":      "rewrite_args",        # Re-call tool with corrected parameter names
    "loop_detected":        "abort_and_summarize", # Stop, return partial result with explanation
}
```

Without named recovery strategies, the agent either retries blindly (compounding the failure) or halts entirely. Named strategies give the harness agency over failure modes without requiring the model to reason about them.

### Layer 5 — Eval Harness as Development Artifact

The eval harness is itself a harness component. It must evolve with the agent — not as a static test suite, but as a living artifact that captures new failure modes from production.

```
# Production failure → new harness test in one step
failed_trace = capture_failed_run(agent_id, session_id)  # Structured trace doc
test_case = harness.from_trace(failed_trace)              # Convert to test case
harness.add_test(test_case, tags=["regression", "production-edge"])
harness.run()                                           # Verify fix
```

This is the trace-replay pattern (S-1013) applied to the harness development loop. The key discipline: every production failure that isn't a model bug becomes a harness gap. Fix the harness.

## Receipt

> Verified 2026-07-23 — Core thesis confirmed: Faros.ai (May 2026) reports LangChain moved from 30th to 5th on Terminal Bench 2.0 in March 2026 via harness optimization alone. Addy Osmani (April 2026) independently frames "Agent = Model + Harness" as the organizing principle for agentic development. Aiagentsfirst.com (May 2026) reports tool description rewrites improved task completion from 68% to 89% on one MCP server; schema mismatches are 38% of MCP failures across 12,000 trials. Three-layer maturity progression (Prompt Engineering → Context Engineering → Harness Engineering) confirmed across Faros.ai, Addy Osmani, and aws.amazon.com/builder (Shashi Jagtap, April 2026). Code examples reflect standard harness engineering patterns from Faros.ai's five-layer model and Addy Osmani's component taxonomy.

## See also

- [S-1044 · The Trajectory Eval Stack](s1044-the-trajectory-eval-stack-when-your-agent-looks-accurate-but-fails-in-production.md) — the eval harness that validates harness changes
- [S-1013 · The Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — capturing failed runs as harness regression tests
- [S-1239 · The Runtime Verification Loop](s1239-the-runtime-verification-loop-when-your-agent-checks-its-own-work.md) — in-harness verification gates
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — making harness failures visible
