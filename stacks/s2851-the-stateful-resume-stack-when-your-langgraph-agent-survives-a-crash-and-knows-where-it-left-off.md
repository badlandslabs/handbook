# S-2851 · The Stateful Resume Stack

_Your LangGraph agent spent 40 minutes navigating a 12-step customer support workflow. The pod restarted at step 9. Without checkpointing, the customer starts over and your support costs double. With it, the agent resumes exactly where it left off — and no one notices the crash._

## Forces

- **MemorySaver dies with the worker**: in-process checkpoints vanish on restart, making local dev testing look clean while production silently loses state on every redeploy
- **The "it works in my notebook" illusion**: developers test checkpointing interactively and conclude it works, but MemorySaver is to production what a notepad is to a database
- **Redis TTL creates silent data loss**: teams pick Redis for speed and later discover their checkpointer data expired or got evicted — long-running workflows silently resume from step 1
- **Concurrency reveals the checkpointer as the spine**: at scale (12k+ conversations/day), every graph invocation must be idempotent and resumable, which means checkpointing cannot be an afterthought
- **The checkpointer is your program counter**: Postgres and SQLite store immutable `StateSnapshot` records keyed by `thread_id`; Redis stores search-indexed entries with TTL — the storage primitive determines whether state is a ledger or a cache

## The move

Treat the LangGraph checkpointer as a first-class production dependency, not a configuration detail.

- **Pick PostgresSaver for any production system above ~1k daily invocations**. It writes an immutable checkpoint after every super-step, keyed by `thread_id`, so re-invoking with the same thread_id resumes from `state.next` instead of re-executing from scratch. It is ACID, horizontally backed up, and queryable with SQL — you can audit, replay, and fork state history.
- **Reserve RedisSaver for stateless, short-lived workflows** where state is a cache with graceful expiry. Redis lacks ACID guarantees and its TTL mechanism means long-running graphs (>15 min default TTL) silently lose their checkpoint state. Teams using Redis alone for a 12k-conversation/day support system hit data loss after restart.
- **Use `interrupt()` for human-in-the-loop pauses** — it writes a checkpoint holding the paused state, and any operator can inspect `get_state(config)` or manually update it with `update_state()` before resuming. This is the mechanism for approval gates, fallback routing, and supervisor intervention.
- **Implement crash recovery as a first-class test**: kill the process mid-workflow, then resume with the same `thread_id` and assert that `state.next` points to the correct node. A checkpointer that hasn't been crash-tested in CI is unproven in production.
- **Use `get_state_history(thread_id)` for time-travel debugging**: the full chain of checkpoints is immutable, so you can walk backward to any prior state and fork from it — useful for replaying incidents or recovering from bad model decisions.
- **Pair PostgresSaver with idempotency keys at the tool-call layer**: checkpointing makes retries safe (re-invoking a crashed workflow re-enters at the correct node), but individual tool calls still need idempotency if the tool itself has side effects.

## Evidence

- **Engineering post:** A multi-agent customer support system serving ~12k conversations/day using LangGraph + PostgresSaver encountered a 3 AM incident after a pod restart. Without a checkpointer in place, every in-flight conversation would have reset. Post-incident, the team moved to PostgresSaver with connection pooling via `psycopg_pool`, adding a `/healthz` endpoint that runs `SELECT 1` against the checkpoint store. — [HolySheep AI: "LangGraph Production Deployment: PostgreSQL State Persistence"](https://www.holysheep.cn/articles/en-langgraphshengchanjibushupostgresqlzhuangtaichijiu-2026-06-30-0008.html)
- **Technical comparison:** A production-grade LangGraph setup using PostgresSaver for 100k+ daily graph executions shows: thread resumes with same `thread_id` and messages intact after process kill; `get_state_history()` enables walking the checkpoint chain backward; custom `BaseCheckpointSaver` implementations write to Postgres, Redis, or S3 with every node execution bookended by a save. — [Markaicode: "LangGraph + PostgreSQL: Persistent Agent State That Survives Crashes"](https://markaicode.com/integrate/langgraph-with-postgresql)
- **Architecture analysis:** The Postgres-vs-Redis choice for checkpointer backend is framed as a lifecycle decision: Postgres stores a permanent, queryable ledger; Redis stores a searchable cache with expiry. A LangGraph checkpointer is not a cache and not your application database — it is the agent's program counter plus stack, persisted after every super-step as an immutable `StateSnapshot`. — [Dreaming.press: "LangGraph Checkpointer: Postgres vs Redis Backend Comparison"](https://dreaming.press/posts/langgraph-checkpointer-postgres-vs-redis.html)

## Gotchas

- **SQLite is fine for a single-worker setup but not multi-replica**: if your LangGraph app runs on more than one pod or gunicorn worker, SQLite's file-level locking will cause checkpoint writes to fail intermittently. Postgres or Redis handle multi-replica correctly.
- **The checkpoint TTL on Redis must exceed your worst-case workflow duration**: a 45-minute procurement workflow on a Redis checkpointer with a 15-minute TTL silently loses state. Always set TTL to 2× the p99 workflow duration.
- **Resuming does not replay failed tool calls**: `invoke(None, config=config)` resumes execution from `state.next`, but the tool that was executing when the crash happened does not automatically re-run. If the tool call was mid-flight, you may need to inspect `pending_writes` in the checkpoint and manually replay or skip.
- **Connection pooling is non-optional for Postgres in production**: raw `psycopg2` connections that don't pool will exhaust under load. Use `AsyncConnectionPool` with `max_requests` and `max_lifetime` settings tuned to your request volume.
