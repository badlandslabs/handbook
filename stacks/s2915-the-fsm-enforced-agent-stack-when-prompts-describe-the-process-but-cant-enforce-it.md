# S-2915 · The FSM-Enforced Agent Stack — When Prompts Describe the Process but Can't Enforce It

You gave your coding agent a detailed workflow: review the PR, write tests, get approval, merge. It followed the steps — but out of order, skipping tests when the review looked simple, merging directly when the branch name matched a pattern it inferred from past merges. Prompts and skills can describe a process. They cannot enforce it. The failure mode is not model capability — the model was more than capable. The failure is that process enforcement requires a runtime, not a description.

This is the core insight behind runtime FSM-enforced agent workflows: model your agent's acceptable control flow as a finite state machine, where states define what the model may do next, typed submissions prove what happened, and transitions only occur through validated exits.

## Forces

- **Prompts describe; state machines enforce.** A prompt saying "get approval before merging" is a suggestion. An FSM where the merge state has no exit until the approval state is completed is a constraint.
- **Agents drift on long-horizon tasks.** Convergent reasoning (all agents on similar tasks reach similar conclusions) combined with context pressure (recent examples feel most relevant) creates systematic drift toward inferred shortcuts.
- **Recovery is only as good as your re-entry point.** A failed step in a free-form agent pipeline leaves you at an undefined context state. A failed transition in an FSM leaves you at a defined state with a known recovery path.
- **FSMs enable audit, not just enforcement.** Every state transition is a log entry. You know exactly which step the agent was in, what it submitted, and whether the transition was valid — without instrumenting the model itself.
- **Not every task belongs in a state machine.** Short, exploratory, or genuinely open-ended tasks become rigid and brittle when forced into FSM structure. The key is identifying which workflows are processes (enforceable) vs. which are quests (undetermined destination).

## The move

**Step 1 — Identify FSM-eligible workflows.**

Workflows are FSM candidates when: outcomes are bounded, steps have dependencies, there are identifiable valid/invalid exit conditions, and rollback paths exist. Quests (research, brainstorming, exploration) are not.

Typical FSM candidates:
- Code review → test → approval → merge pipelines
- Incident response triage → mitigation → verification → resolution
- Customer onboarding: verify → configure → validate → activate
- Data pipeline: extract → transform → validate → load

**Step 2 — Model the FSM in code.**

```typescript
// Aharness-style FSM for a code-review → merge workflow
// https://github.com/Alfredvc/aharness

import { createHarness, State, Submission } from 'aharness';

// Define states as typed constraints
const states = {
  review: State({
    exits: ['approved', 'changes_requested', 'blocked'],
    allowedTools: ['read_file', 'list_files', 'git_diff'],
    maxSteps: 20,
  }),
  changes_requested: State({
    exits: ['review', 'abandoned'],
    allowedTools: ['edit_file', 'write_file', 'git_commit'],
  }),
  approved: State({
    exits: ['merged', 'blocked'],
    allowedTools: ['git_merge', 'github_pr_merge'],
    requiresApproval: true,
  }),
  merged: State({
    exits: [], // terminal
    allowedTools: [],
  }),
};

// Typed submission proves what happened
interface ReviewSubmission extends Submission {
  verdict: 'approved' | 'changes_requested' | 'blocked';
  reviewerId: string;
  blockingIssues?: string[];
}

const harness = createHarness({ states });

// Model can only advance through validated exits
const session = harness.start('review');
const step = session.step({
  toolCalls: ['read_file("src/handler.ts")', 'git_diff()'],
  summary: 'Reviewed PR: added rate limiting to handler',
});

if (step.transition('approved', { reviewerId: 'jane', verdict: 'approved' })) {
  session.transitionTo('approved');
} else if (step.transition('changes_requested', { 
  verdict: 'changes_requested', 
  blockingIssues: ['missing test coverage for edge case'] 
})) {
  session.transitionTo('changes_requested');
}
// Invalid exit (e.g., trying to transition from 'review' directly to 'merged')
// throws TransitionError
```

**Step 3 — Layer typed submissions on state transitions.**

Each transition carries a typed submission that proves the exit condition was met. The FSM validates the submission schema before accepting the transition:

```typescript
// Transition validation — the FSM rejects malformed or insufficient submissions
try {
  session.transitionTo('approved', {
    verdict: 'approved',
    // missing: reviewerId — schema validation fails
  });
} catch (e) {
  if (e instanceof TransitionError) {
    // Agent must resubmit with complete submission
    session.revertTo('review');
  }
}
```

**Step 4 — Handle invalid exits gracefully.**

When an agent attempts an invalid transition, the FSM does not block — it redirects:

```typescript
session.onInvalidTransition((from, attempted, allowed) => {
  logger.warn(`Agent at ${from} attempted ${attempted}, allowed: ${allowed}`);
  return {
    redirect: from, // stay in current state
    feedback: `Cannot transition from ${from} to ${attempted}. Valid exits: ${allowed.join(', ')}`,
    incrementAttempts: true,
  };
});
```

**Step 5 — Compose FSMs as npm packages.**

The architectural bet: useful workflows are reusable software. Install a workflow FSM as a dependency and build on top of it:

```bash
npm install @team/standard-code-review-fsm
```

```typescript
import { createHarness } from 'aharness';
import { codeReviewFSM } from '@team/standard-code-review-fsm';

// Extend the base FSM with team-specific overrides
const teamHarness = createHarness({
  states: {
    ...codeReviewFSM.states,
    security_review: State({
      exits: ['approved', 'blocked'],
      allowedTools: ['semgrep_scan', 'dependency_check'],
      requiredForPaths: ['auth/**', 'payments/**'],
    }),
  },
});
```

## Receipt

> Verified 2026-08-20 — Research sources: Aharness Show HN (Alfredvc, github.com/Alfredvc/aharness, 3 weeks prior); Microsoft AutoGen StateFlow (13-28% task success improvement vs ReAct agents); VIGIL (arXiv:2606.26524, Microsoft Research, June 2026, runtime behavioral enforcement). Code reflects Aharness FSM patterns. Live validation: npm package at aharness on npm (TypeScript, MIT). No execution performed — Receipt pending.

## See also

- [S-1036 · The Orchestration Gap Stack](s1036-the-orchestration-gap-when-your-agent-demo-shines-and-your-production-system-dies.md) — why orchestration frameworks fail; FSMs as the enforcement layer underneath
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — FSM re-entry points as the structured recovery primitive
- [S-1040 · The Protocol Gap Stack](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — FSM state contracts as the agent-to-agent protocol layer
