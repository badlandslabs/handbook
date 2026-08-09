# S-2391 · The Capability Erosion Stack — When Your Agent Gets Smarter at New Things and Dumber at Old Ones

Your agent accumulates skills, refines workflows, fine-tunes itself, and updates its memory — it is doing everything right. Six weeks in, it handles the new task distribution beautifully. Then someone asks it to do something it handled effortlessly at launch, and it fails. Not because the model degraded. Not because the prompt drifted. Because it learned so hard to be good at the new thing that it forgot how to do the old thing. This is **capability erosion under self-evolution**: the structural failure mode of agents that improve continuously.

## Situation

You deploy a customer-support agent that handles order status, refund requests, and product FAQs. It starts at 87% accuracy across all three categories. Over the next 30 days, it self-evolves: it refines its troubleshooting workflow, accumulates skill patches for edge cases, fine-tunes its routing logic, and updates its knowledge memory with every resolved ticket. The agent gets better at refunds and FAQs — accuracy climbs to 94%. Order-status accuracy drops to 61%. Nobody changed the model's temperature. Nobody updated the prompt. The agent did exactly what it was designed to do: adapt to the dominant task distribution. The side effect is capability erosion.

## Forces

- **Self-evolution is non-monotonic.** Continuous adaptation does not mean continuous improvement — it means the agent's capability landscape is reshaped by what it learns, and previously stable capabilities can be destabilized by that reshaping.
- **Bounded repository capacity creates overwrite pressure.** Whether it is a skill repository, a workflow library, or a fine-tuning dataset, capacity is finite. New capabilities must displace old ones. Retrieval frequency determines which survives.
- **Sequential task-distribution shift amplifies overwrite.** When the task mix shifts (e.g., a product launch spikes FAQ volume), the agent over-allocates capacity to the new distribution. Old capabilities become retrieval-underutilized and get overwritten — even if they were mastered.
- **All four evolution channels erode.** Workflow evolution makes execution paths longer and more complex. Skill evolution causes repository overwrite. Model evolution (fine-tuning) introduces retroactive bias. Memory evolution degrades episodic integrity. No single channel is safe.
- **The agent tests fine in isolation.** Erosion is invisible in unit evaluation — it only manifests in the full task distribution the agent actually encounters. Your order-status test still passes because you never mixed it with the shifted distribution.

## The move

**Detect and prevent capability erosion across all four evolution channels.**

### 1. Instrument the capability baseline before evolution begins

Establish a per-capability accuracy baseline for every task type the agent handles. Run this suite periodically — not just after changes, but on a schedule independent of the deployment lifecycle. Erosion is gradual; it needs a periodic signal to be caught.

```
python
# Baseline capability suite — run at deployment, then weekly
def capability_baseline(agent, task_distributions):
    results = {}
    for task_type, eval_set in task_distributions.items():
        # Hold out a fixed eval set for each task type
        # Never fine-tune on eval_set examples
        results[task_type] = agent.evaluate(eval_set)
    return results

baseline = capability_baseline(agent, ORDER_STATUS_TASKS + REFUND_TASKS + FAQ_TASKS)
```

### 2. Track capability parity across evolution cycles

After each self-evolution event (workflow refinement, skill accumulation, fine-tuning step, memory consolidation), re-run the baseline suite and compare. The moment any task type drops below threshold (e.g., 95% of baseline), pause evolution and audit. Log the delta per task type — not just the aggregate score.

### 3. Enforce capability-preserving constraints in each evolution channel

| Channel | Erosion mechanism | Preservation constraint |
|---------|-------------------|------------------------|
| **Workflow** | New paths override old ones; execution traces grow noisy | Pin canonical workflows for high-stakes task types; version-stamp workflow edits by task type |
| **Skill** | Repository overwrite under bounded capacity; high-frequency new skills crowd out old | Skill retrieval = f(frequency, recency, importance); enforce minimum retention score per task type |
| **Model** | Fine-tuning on new distribution introduces retroactive bias | Maintain a frozen snapshot per capability; validate against frozen snapshots before deploying new checkpoints |
| **Memory** | Episodic updates overwrite priors; recent experience dominates | Weighted episodic consolidation: decay by relevance, not just recency; pin critical facts |

### 4. Separate evolution from inference

The agent that evolves should not be the agent that infers. Use a separate evolution loop that generates capability patches, and a separate inference loop that consumes verified patches. This is the Capability-Preserving Evolution (CPE) principle: **isolation between adaptation and deployment**.

```
python
class CapabilityPreservingEvolution:
    def __init__(self, agent, patch_queue, frozen_snapshots):
        self.agent = agent
        self.patch_queue = patch_queue
        self.frozen_snapshots = frozen_snapshots  # per task-type frozen copies

    def evolve(self, new_task_examples):
        # Generate patches on new distribution
        patches = self.agent.generate_patches(new_task_examples)
        # Apply to shadow agent, not production
        shadow = self.agent.clone()
        shadow.apply_patches(patches)
        # Verify against frozen snapshots
        for task_type, snapshot in self.frozen_snapshots.items():
            delta = shadow.evaluate_task(task_type) - snapshot.evaluate_task(task_type)
            if delta < -0.05:  # 5% drop triggers rollback
                patches.discard_for(task_type)
        # Only deploy patches that don't erode frozen capabilities
        self.patch_queue.commit(patches.filtered())
```

### 5. Set a task-mix awareness layer

Monitor the distribution of incoming tasks. When the task mix shifts significantly (detectable via a rolling chi-square or KL-divergence test against the training distribution), the agent should: (a) slow evolution velocity to allow baseline capabilities to re-stabilize, and (b) explicitly re-sample from the full task distribution rather than the current dominant one.

### 6. Design for snapshot-based rollback

Every evolution checkpoint should be a deployable snapshot. If erosion is detected post-deployment, roll back to the last known-good snapshot and re-apply only the verified-safe patches. Do not attempt to "fix" erosion by evolving further — this is the path to deeper erosion.

## Signs you already have erosion

- A task type that worked at launch now requires more retries or produces lower-quality output — but the model, prompt, and tooling are unchanged.
- Your self-evolution metrics look great (skill count up, workflow efficiency up, fine-tuning loss down) but user satisfaction on specific task types has dropped.
- Your agent's execution traces for mastered tasks now include unnecessary intermediate steps — behavioral policy drift.
- Fine-tuning a model on recent data improves performance on recent tasks and degrades performance on established tasks.

## The core tension

You want an agent that learns and adapts. Erosion is the price of adaptation. The mitigation is not to stop evolving — it is to evolve with explicit conservation: preserve what works while acquiring what is new. This requires treating capabilities as finite resources that must be actively protected, not just as facts that accumulate.

> Verified 2026-08-10 — Researched via arXiv:2605.09315v1 (UIUC, May 2026), web search, and deduplication against existing stacks. Composite: 9.15. Distinct from S-1022 (Agent Drift — behavioral regression in multi-agent systems over time) and S-1002 (Memory Consolidation Debt — episodic integration failure). Both cover adjacent ground; neither covers the specific failure mode of capability loss due to self-evolution across bounded-capacity channels.

## See also

- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — behavioral regression detection in multi-agent systems
- [S-1002 · The Memory Consolidation Debt Stack](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — episodic memory integration failure
- [S-3209 · The Capability Scoping Stack](s3209-the-capability-scoping-stack-when-your-summarization-agent-has-shell-access-and-nobody-knows-why.md) — overprovisioning and least-privilege for agent capabilities
