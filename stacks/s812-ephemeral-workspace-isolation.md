# S-812 · Ephemeral Workspace Isolation

When your agent writes files, downloads artifacts, runs scripts, or extracts archives — it does it into a shared, persistent filesystem. The next task inherits a dirty working directory, stale outputs, and leaked secrets. Ephemeral workspaces give every task a clean, isolated directory that is torn down on completion or error.

## Forces

- Agents accumulate state between tasks: downloaded files, generated artifacts, credentials written to disk, modified configs. This state bleeds into the next task and causes hard-to-reproduce failures.
- A compromised agent that wrote to a persistent workspace has left a trail. Ephemeral workspaces limit the blast radius — the moment the task ends, everything is gone.
- Filesystem isolation between concurrent agents is not optional in multi-tenant deployments. Two agents processing different user requests should never share a working directory.
- `tmp` directories are not workspaces — they persist beyond the task, fill up disk, and have no lifecycle management. True ephemeral workspaces have explicit create, populate, execute, and teardown phases.

## The move

Treat every agent task as if it runs inside a fresh container. The workspace lifecycle:

1. **Create** — allocate a unique, random working directory (`/workspace/agent-{task-id}-{timestamp}/`). Use a UUID, not a task counter, to prevent path collisions.
2. **Populate** — inject only the artifacts the task needs (input files, credentials as env vars or short-lived tokens, not written to disk). No shared filesystem access.
3. **Execute** — agent operates entirely inside the workspace. All `write_file`, `read_file`, and file-manipulation tools are scoped to this directory.
4. **Harvest** — on success, extract only the explicitly named output files. Copy results out, discard the rest.
5. **Teardown** — on success or error, delete the entire workspace directory. Nothing persists.

### Implementation: Workspace-scoped tool wrapping

```python
import tempfile
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def ephemeral_workspace(prefix: str = "agent-workspace"):
    """Create a clean, isolated workspace for a task. Teardown on exit."""
    workspace_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    base = Path(tempfile.gettempdir())
    workspace = base / workspace_id
    workspace.mkdir(parents=True, exist_ok=False)

    # Chroot all file operations to this workspace
    original_cwd = Path.cwd()

    try:
        import os
        os.chdir(workspace)  # Agent's cwd is now inside the workspace
        yield workspace
    finally:
        os.chdir(original_cwd)
        # Teardown: recursive delete. Nothing persists.
        shutil.rmtree(workspace, ignore_errors=True)


# Tool wrappers that enforce workspace isolation
import functools

def workspace_scoped(fn):
    """Decorator: redirects all file operations to the current workspace."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        workspace_root = Path.cwd()  # In production: pass workspace path explicitly
        # Validate all paths resolve inside workspace
        def resolve_within(path):
            p = (workspace_root / path).resolve()
            if not str(p).startswith(str(workspace_root.resolve())):
                raise ValueError(f"Path escape attempt: {path}")
            return p
        # Inject resolve_within into fn's kwargs or use a thread-local
        kwargs['_resolve'] = resolve_within
        return fn(*args, **kwargs)
    return wrapper


@workspace_scoped
def agent_write_file(path: str, content: str, _resolve):
    """Write content only within the current workspace boundary."""
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"path": str(target.relative_to(Path.cwd())), "size": len(content)}


@workspace_scoped
def agent_read_file(path: str, _resolve):
    """Read a file only within the current workspace boundary."""
    target = _resolve(path)
    return {"content": target.read_text(), "path": str(target.relative_to(Path.cwd()))}


# Orchestrator side: workspace per task
async def run_task_in_workspace(task_id: str, agent_fn, input_files: list[dict]):
    with ephemeral_workspace(prefix=f"agent-{task_id}") as ws:
        # Populate inputs
        for inp in input_files:
            dest = ws / inp["name"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(inp["data"])

        # Agent operates inside ws. cwd is ws.
        result = await agent_fn(workspace=ws)

        # Harvest outputs (only named artifacts)
        harvested = {}
        for name in result.requested_outputs:
            p = ws / name
            if p.exists():
                harvested[name] = p.read_bytes()
            # Non-requested files are left behind and rmtree'd on exit

        return {"task_id": task_id, "outputs": harvested}
        # Workspace teardown happens in finally: rmtree(ws)
```

### The three workspace policies

| Policy | When to use | Tradeoff |
|--------|-------------|----------|
| **Per-task** (above) | Independent tasks, maximum isolation | Higher setup cost; no cross-task state |
| **Per-session** | Stateful tasks where the agent needs continuity | State pollution risk; teardown at session end |
| **Per-agent, shared** | Multiple sub-tasks by the same agent sharing artifacts | Isolation only between agents, not between tasks |

For production agents that run code execution tools, **per-task is the default**. The startup cost of creating a fresh directory is milliseconds; the cost of debugging a stale artifact failure is hours.

### Kubernetes: workspace as emptydir volume

```yaml
# Pod spec: each agent container gets an emptydir volume
# Mounted at /workspace, torn down when the pod/container exits
spec:
  containers:
  - name: agent
    image: agent-runtime:latest
    volumeMounts:
    - name: task-workspace
      mountPath: /workspace
    env:
    - name: WORKSPACE_ROOT
      value: /workspace
  volumes:
  - name: task-workspace
    emptyDir:
      medium: Memory          # Optional: tmpfs for speed + security (no disk persistence)
      sizeLimit: 500Mi       # Prevent disk exhaustion
```

> Receipt pending — 2026-07-08

## See also

- [S-205 · Agent Sandbox Isolation](stacks/s205-agent-sandbox-isolation.md) — the syscall/kernel isolation layer; workspace isolation is the filesystem layer above it
- [S-223 · Agent Sandboxing and Code Execution Isolation](stacks/s223-agent-sandboxing-code-execution.md) — ephemeral VMs as a complement to workspace isolation for untrusted code
- [S-196 · OTEL GenAI Telemetry](stacks/s196-otel-genai-telemetry.md) — tracing that should span workspace operations to make failures traceable
