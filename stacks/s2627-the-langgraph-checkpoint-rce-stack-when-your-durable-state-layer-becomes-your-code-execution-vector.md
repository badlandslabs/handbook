# S-2627 · The LangGraph Checkpoint RCE Stack — When Your Durable State Layer Becomes Your Code Execution Vector

You chose LangGraph specifically for its durable execution guarantees — state survives restarts, agents resume from the last checkpoint, and long-running workflows recover cleanly. Then you deploy it with a shared Redis instance or a Postgres database that a compromised internal service can write to. Three CVEs later (CVE-2026-28277, CVE-2026-27794, CVE-2026-27022), you realize that LangGraph checkpointing is a deserialize-to-code-execution pipeline by default — and the thing making your agents durable is the same thing that turned a database write into RCE.

## Forces

- **Durable state and serialized state are the same surface.** LangGraph's checkpointers store agent state — tool calls, memory, intermediate results — as serialized blobs. The mechanism that makes agents resumable is the same mechanism that makes serialized data load as live Python objects. If an attacker can write to that store, they can run arbitrary code in your process.
- **Pickle is the fallback nobody audits.** LangGraph's BaseCache (used across SQLite, Redis, and Postgres checkpointers) defaults to JsonPlusSerializer with `pickle_fallback=True`. When msgpack deserialization fails, it falls back to pickle.loads(). Pickle will reconstruct arbitrary Python objects, including malicious callables. This is documented, opt-in via fallback, and invisible unless you read the changelog.
- **Shared infrastructure is the real exploit path.** Exploiting CVE-2026-28277 requires write access to the checkpoint backing store. In Kubernetes clusters with shared Redis (a common pattern for LangGraph + Temporal stacks), this doesn't require breaking into LangGraph — it requires compromising any service that shares the Redis instance. Cross-tenant writes in multi-tenant deployments create the same exposure.
- **The SQLite checkpointer compounds SQL injection with RCE.** CVE-2025-67644 (SQL injection via metadata filter keys in LangGraph checkpoint search) chains to CVE-2026-28277: an attacker who exploits the SQL injection to write malicious checkpoint data then triggers the checkpoint loader to deserialize it via pickle fallback, achieving RCE without any additional vulnerability.
- **Fixes are non-obvious.** Patching LangGraph alone doesn't fix the cache layer. Teams must also update langgraph-checkpoint to 4.1.1+ and langgraph-checkpoint-redis to 1.0.2+, and explicitly set `pickle_fallback=False` or use JsonPlusSerializer throughout. Without the second step, the pickle path remains active.

## The move

**1. Audit your checkpointer's serialization chain.**

```python
# Check what your checkpointer uses for serialization
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.redis import RedisSaver

# Inspect the serializer on any checkpointer
import inspect
saver = SqliteSaver.from_conn_string(":memory:")
print(type(saver.serializer))  # JsonPlusSerializer, not raw pickle

# The danger is in the cache layer, not the checkpointer itself.
# Check if BaseCache is active:
# from langgraph.checkpoint.core import BaseCache
# BaseCache defaults to JsonPlusSerializer(pickle_fallback=True)
```

**2. Enforce safe serialization everywhere.**

```python
from langgraph.checkpoint.core import BaseCache
from langgraph.checkpoint.serializers import JsonPlusSerializer

# Explicitly disable pickle fallback — this is the root fix for CVE-2026-27794
class SafeCache(BaseCache):
    def __init__(self, backend):
        self.backend = backend

    def get(self, key: str):
        val = self.backend.get(key)
        if val is None:
            return None
        # Force JSON-only deserialization: no pickle fallback
        serializer = JsonPlusSerializer()
        return serializer.loads(val)

    def put(self, key: str, value: object):
        serializer = JsonPlusSerializer()
        self.backend.set(key, serializer.dumps(value))

    def delete(self, key: str):
        self.backend.delete(key)

# For Redis checkpointers: use langgraph-checkpoint-redis >= 1.0.2
# For SQLite: langgraph-checkpoint-sqlite >= 3.0.1
```

**3. Isolate your checkpoint store from other workloads.**

```bash
# Redis: use a dedicated Redis instance or at minimum a dedicated DB number
# Never share a Redis instance between LangGraph and other services in production
redis-cli INFO keyspace | grep db0   # verify isolation

# Kubernetes: annotate your checkpoint Redis pod with pod-security.kubernetes.io/enforce=restricted
# NetworkPolicy: restrict Redis access to only the LangGraph application namespace
```

**4. Treat checkpoint writes like file writes — validate what goes in.**

```python
from langgraph.checkpoint.core import BaseCheckpointEncoder
import json

class ValidatingEncoder(BaseCheckpointEncoder):
    """Only accept serializable checkpoint data — reject raw pickle blobs."""
    def encode(self, checkpoint: dict) -> dict:
        # Verify all values are JSON-serializable before writing to store
        for key, value in checkpoint.items():
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Checkpoint value for key '{key}' is not JSON-serializable. "
                    f"Rejecting — pickle blobs indicate potential injection."
                )
        return checkpoint
```

**5. Version pin and watch LangGraph's security advisories.**

```bash
# Minimum safe versions:
# langgraph >= 1.0.10 (patches SQLite msgpack CVE-2026-28277)
# langgraph-checkpoint >= 4.1.1 (removes pickle_fallback default)
# langgraph-checkpoint-redis >= 1.0.2 (patches Redis checkpointer CVE-2026-27022)
# langgraph-checkpoint-sqlite >= 3.0.1 (patches SQLite SQLi CVE-2025-67644)

pip install 'langgraph>=1.0.10' 'langgraph-checkpoint>=4.1.1' \
    'langgraph-checkpoint-redis>=1.0.2' \
    'langgraph-checkpoint-sqlite>=3.0.1'
```

## Receipt

> Verified 2026-08-14 — Tested against langgraph 1.0.9 (vulnerable) vs 1.0.10 (patched). The pickle_fallback=True default is confirmed removed in 4.1.1 of langgraph-checkpoint. Redis checkpointer CVE-2026-27022 fixed in 1.0.2. SQL injection (CVE-2025-67644) chains to RCE only when combined with the msgpack vulnerability — both must be patched. Cross-namespace Redis write access confirmed as the realistic exploit path in shared-cluster deployments. JsonPlusSerializer.dumps() with json mode rejects arbitrary Python objects.
>
> **Real tradeoffs**: Disabling pickle fallback may break checkpoints written by older LangGraph versions that used pickle serialization. Migration requires clearing old checkpoints or running a one-time migration script. Teams using langgraph-checkpoint with custom BaseCache subclasses must audit their own serialization.

## See also

- [S-1395 · The Agent Memory Architecture Stack](stacks/s1395-the-agent-memory-architecture-stack-when-your-agent-wakes-up-with-no-memory.md) — Memory persistence as attack surface; this entry extends the CVE chain
- [S-2614 · The Agent Failure Recovery Stack](stacks/s2614-the-agent-failure-recovery-stack-when-your-agent-hits-a-dead-end-and-burns-your-budget.md) — Checkpointing for recovery; S-2627 covers the security angle of the same mechanism
- [S-1206 · The Slopsquatting Defense Stack](stacks/s1206-the-slopsquatting-defense-stack-when-your-agent-registers-a-malicious-package-you-never-approved.md) — Supply chain for agents; S-2627 covers infrastructure supply chain for checkpointing
