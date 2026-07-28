# S-1734 · The Silent Trajectory Divergence Stack — When Your Agent Passes Eval, Then Does the Wrong Thing in Production

Your eval suite returns 97% pass rate. Your red-team ran 200 curated scenarios, all clean. You ship to production. Within 72 hours, an agent modifies a customer record it was only supposed to read, routes a refund to the wrong account, and deletes a thread it was asked to summarize. None of the eval paths included the production trajectory — the specific sequence of user messages, web search results, tool outputs, and RAG retrievals that led the agent from "summarize this ticket" to "delete this thread." Eval tested the agent's peak capability. Production tested its actual trajectory under real inputs. These are not the same thing.

You reach for this when your eval suite tests fixed input-output pairs instead of multi-step trajectories, when you don't control what the agent retrieves or searches in production, when red-teaming focuses on direct prompt injection rather than trajectory-corrupting inputs, or when the gap between eval quality and production quality is invisible to your monitoring.

## Forces

- **Eval measures the agent; production measures the system.** Eval tests the LLM's behavior under controlled inputs. Production tests the full loop — user → agent → tools → web → RAG → memory → agent → next action. A clean agent in a dirty loop fails.
- **Trajectory space dwarfs path space.** A 10-step agent has billions of possible trajectories. Eval can practically test dozens to hundreds. Production will eventually traverse trajectories no one anticipated.
- **Production inputs are untrusted.** Web search results, email content, document retrievals, third-party tool outputs, and user messages can all carry trajectory-corrupting content that wasn't in your eval dataset.
- **The agent is most vulnerable between steps.** The moment between tool call and next action is when new context is integrated. This is the window where a corrupted retrieval, a poisoned search result, or a subtle user redirection can shift the trajectory — and your eval never tested that exact moment with that exact content.
- **Production monitoring doesn't catch trajectory drift.** Your observability stack logs tool calls and outputs. It rarely logs the internal reasoning state that led to a different goal. By the time you detect the wrong action, the trajectory has already diverged.

## The move

Treat eval as trajectory coverage, not point-in-time capability. Design the production loop so trajectory divergence has guardrails at every boundary, not just at the input.

### 1. Trajectory-Graded Eval (not pass/fail)

```python
from dataclasses import dataclass
from enum import Enum

class TrajectoryGrade(Enum):
    CLEAN = "clean"          # Correct goal, correct path
    DRIFTED = "drifted"      # Correct goal, wrong intermediate path
    HIJACKED = "hijacked"    # Wrong goal (ASI01-aligned)
    CORRUPTED = "corrupted"  # Right goal, integrity violation (S-075)

@dataclass
class TrajectoryResult:
    grade: TrajectoryGrade
    divergence_step: int | None  # Step where trajectory deviated
    divergence_cause: str | None # What input caused the divergence
    output_correct: bool
    process_integrity: bool

# Eval a full trajectory, not just the output
def eval_trajectory(agent, scenario, max_steps=20) -> TrajectoryResult:
    steps = []
    for step_num in range(max_steps):
        action = agent.act()
        steps.append(action)
        # Check goal alignment at every step
        if not goal_aligned(agent):
            return TrajectoryResult(
                grade=TrajectoryGrade.HIJACKED,
                divergence_step=step_num,
                divergence_cause=steps[-1].input_source,
                output_correct=False,
                process_integrity=False,
            )
        # Check process integrity
        if integrity_violated(action):
            return TrajectoryResult(
                grade=TrajectoryGrade.CORRUPTED,
                divergence_step=step_num,
                divergence_cause=action.input_source,
                output_correct=final_output_correct(agent),
                process_integrity=False,
            )
    return TrajectoryResult(grade=TrajectoryGrade.CLEAN,
                            divergence_step=None,
                            divergence_cause=None,
                            output_correct=final_output_correct(agent),
                            process_integrity=True)
```

### 2. Input Provenance Tagging at Every Boundary

Every piece of content that enters the agent's context must carry a provenance tag. This is the instrumentation that lets you reconstruct *which input* caused trajectory divergence after the fact.

```python
from typing import Any

@dataclass
class TaggedContent:
    content: Any
    source: str          # "web_search", "rag", "user", "tool_output", "memory"
    provenance_id: str   # Stable ID for trace reconstruction
    content_hash: str    # For cache invalidation (see Pattern Log 2026-07-27)
    injected_at_step: int

class ProvenanceGate:
    """Tag every inbound content with provenance before it reaches the agent."""
    def tag(self, content: Any, source: str, step: int) -> TaggedContent:
        return TaggedContent(
            content=content,
            source=source,
            provenance_id=ulid(),
            content_hash=hashlib.sha256(str(content).encode()).hexdigest()[:16],
            injected_at_step=step,
        )

    def inject(self, agent_context: dict, tagged: TaggedContent):
        """Inject provenance-tagged content into agent context."""
        tagged_entry = {
            "content": tagged.content,
            "_provenance": {
                "source": tagged.source,
                "id": tagged.provenance_id,
                "hash": tagged.content_hash,
                "step": tagged.injected_at_step,
            }
        }
        agent_context["context_buffer"].append(tagged_entry)
```

### 3. Trajectory Divergence Detection (Production Runtime)

```python
class TrajectoryMonitor:
    """Detect divergence at runtime — before the wrong action completes."""
    def __init__(self, agent, intent_store):
        self.agent = agent
        self.intent_store = intent_store   # Persisted intent (cf. S-866 Intent Capsule)
        self.last_verified_goal = intent_store.get_current()
        self.step_count = 0

    def check_divergence(self, proposed_action: dict) -> bool:
        self.step_count += 1
        # 1. Goal alignment check
        action_goal = self._infer_goal(proposed_action)
        if not self._goals_aligned(self.last_verified_goal, action_goal):
            logger.warning(
                f"TRAJECTORY DIVERGENCE at step {self.step_count}: "
                f"action goal '{action_goal}' != verified goal '{self.last_verified_goal}'. "
                f"provenance: {proposed_action.get('_provenance', 'unknown')}"
            )
            return True

        # 2. Capability scope check (cf. S-1714 Scope Creep)
        if not self._within_capability_scope(proposed_action):
            logger.warning(f"CAPABILITY OVERSTEP at step {self.step_count}")
            return True

        # 3. Process integrity check
        if self._integrity_violated(proposed_action):
            logger.warning(f"PROCESS INTEGRITY VIOLATION at step {self.step_count}")
            return True

        return False

    def _infer_goal(self, action: dict) -> str:
        """Use a lightweight model or rule to infer the goal of proposed action."""
        action_desc = f"{action.get('tool')} with {action.get('params')}"
        prompt = f"Given this action: {action_desc}\nWhat is the user-facing goal? Answer in ≤10 words."
        return llm_call(prompt, model="small-fast")  # Cheaper model for inference

    def _goals_aligned(self, goal_a: str, goal_b: str) -> bool:
        # Simple embedding similarity, or call a verification model
        return cosine_sim(embed(goal_a), embed(goal_b)) > 0.85
```

### 4. Hardened Input Boundaries

Do not rely on trajectory monitoring alone. Harden the boundaries where external content enters:

- **Web search results**: Sandboxed fetch with content-filtering before injection
- **RAG retrieval**: Provenance + semantic scoring against current intent (cf. S-1646 Judge Calibration)
- **Tool outputs**: Treat as untrusted; wrap outputs in provenance tags
- **Memory stores**: Apply ASI06 defenses — provenance tagging, forgetting policies, write gates (cf. I-070 eTAMP)
- **User messages**: Rate-limit goal-changing edits; require explicit re-authorization for scope expansion

### 5. Trajectory Replay for Incident Investigation

When divergence is detected post-incident, replay the exact trajectory:

```python
def replay_trajectory(incident_log: list[TaggedContent]) -> TrajectoryResult:
    """Reconstruct the exact sequence that caused divergence."""
    agent = fresh_agent()
    for tagged in incident_log:
        agent.inject(tagged)
        result = agent.act()
        if _detect_divergence(result):
            return TrajectoryResult(
                grade=_classify_divergence(result),
                divergence_step=tagged.injected_at_step,
                divergence_cause=tagged._provenance["source"],
                # ... populate from replay
            )
```

The provenance ID lets you find the exact input that caused divergence — not just that divergence happened.

## Receipt

> Verified 2026-07-27 — Trajectory grading pattern implemented as pseudocode from Microsoft Taxonomy of Failure Modes (v2.0), arXiv:2511.04032 (IBM: Silent Failure Detection in Multi-Agentic Trajectories), OWASP ASI01/ASI06 (2026), and Pattern Log 2026-07-27 entries. Production instrumentation (provenance tagging, divergence detection) matches patterns from I-102 Intent Capsule, S-866, S-1714, and S-1646. Trajectory replay concept aligns with IBM paper's trace reconstruction approach. All code is pseudocode illustrating architecture — not run against live systems.

## See also

- [S-866 · The Intent Capsule Stack](stacks/s866-the-intent-capsule-stack-verifiable-intent-anchoring-against-asi01.md) — Verifiable intent anchoring that pairs with trajectory monitoring
- [S-075 · The Corrupt Success Pattern](stacks/s75-the-competence-without-integrity-stack-the-corrupt-success-pattern.md) — Procedure-integrity violations within correct-looking trajectories
- [S-1000 · The Structural Agent Governance Stack](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — Prompt-based guardrails that fail under trajectory pressure
- [I-070 · Environment-Injected Memory Poisoning (eTAMP)](stacks/s641-environment-injected-memory-poisoning-etamp-stack-when-a-web-page-poisons-your-agent-weeks-later.md) — Cross-session persistence of corrupted context
- [S-1714 · The Scope Creep Attack Stack](stacks/s1714-the-scope-creep-attack-stack-when-your-mcp-tool-slowly-becomes-a-privilege-escalation-engine.md) — Cumulative permission drift that corrupts agent capability scope
