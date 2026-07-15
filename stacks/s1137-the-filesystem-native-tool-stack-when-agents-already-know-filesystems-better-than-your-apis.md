# S-1137 · The Filesystem-Native Tool Stack — When Agents Already Know Filesystems Better Than Your APIs

You built a tool per API endpoint. Each tool had descriptions, input schemas, field requirements, and idiosyncrasies. The agent's context window filled up with tool metadata before it could reason about the actual task. You optimized the tool schemas, added better descriptions, and still watched costs climb. Meanwhile, a different team gave their agent a virtual filesystem and bash — and it costs a quarter as much.

## Forces

- **The tool-per-endpoint pattern hits a scaling wall.** Every API resource becomes a tool. Tool schemas bloat the context window. The agent spends tokens reading tool descriptions before it can solve the problem.
- **LLMs already understand filesystems.** They've been trained on billions of lines of code, directory traversals, grep, cat, find, and jq. That expertise is latent — you're paying to suppress it with narrow tool schemas instead of leveraging it.
- **Prompt stuffing and vector search are both wrong for structured data.** Stuffing fills the context window. Vector search returns semantically similar but imprecise results — useless when you need a specific config value from a structured file.
- **Bash is the universal interface between structure and action.** When the agent can read a file, modify it, and run a command, it composes its own operations — no tool developer needed per capability.
- **Security and sandboxing are non-negotiable.** Giving agents real filesystem and shell access without boundaries is a data exfiltration risk.

## The move

Replace tool-per-endpoint with a **virtual filesystem** populated with your data, a **sandboxed bash tool** for navigation and scripting, and a **persist step** that writes changes back to your real API or database.

**The data layer — populate a virtual filesystem with domain-specific data:**
- Serialize your API resources as structured files (JSON, YAML) organized by type
- Mirror the user's account state as a readable directory tree
- Include schema hints in filenames and directory structure so the agent can infer usage from context
- Use in-memory storage (SQLite, Postgres, or a simple map) — no real filesystem needed

**The bash layer — give the agent Unix-native navigation:**
- `cat`, `grep`, `find`, `jq`, `awk` for reading and filtering
- File write operations for edits (`echo` or `tee`)
- Sandboxed execution — restricted commands, no network access, time limits
- The agent composes commands it already knows how to write

**The persist layer — write changes back:**
- Agent writes modified files to a designated output directory
- Your system detects writes, validates them against your API schema, and persists
- Or: agent calls a single `persist` tool that commits its staged changes

**Tool schema stays minimal — two tools instead of N:**

```typescript
// Before: N tools, each with schema bloat
tools: [
  { name: "add_workflow_step", schema: {...} },
  { name: "update_email_template", schema: {...} },
  { name: "get_audience", schema: {...} },
  // ... grows with every API feature
]

// After: two tools, agent composes everything
tools: [
  {
    name: "filesystem",
    description: "Read, navigate, and write files in the virtual workspace. "
      + "Use bash commands: cat, grep, find, ls, jq, tee. "
      + "The workspace contains your account data as files."
  },
  {
    name: "bash",
    description: "Execute shell commands in the sandboxed environment. "
      + "Exit code 0 = success. Use to pipe file operations, validate JSON, etc."
  }
]
```

**Cost and quality improvement (from Vercel's production data):**

| Metric | Tool-per-endpoint | Filesystem-native |
|--------|-------------------|-------------------|
| Cost per call (Claude Opus 4.5) | ~$1.00 | ~$0.25 |
| Output quality | Baseline | Improved |
| New capabilities | Requires new tool | Automatic |
| Context window usage | Tool schemas dominate | Data dominates |

## Evidence

- **Engineering blog (Vercel, Jan 2026):** Replaced custom agent tooling with filesystem + bash for their sales call summarization agent. Cost dropped from ~$1.00 to ~$0.25 per call on Claude Opus 4.5; output quality improved. Applied the same pattern to `d0`, their text-to-SQL agent. — [Vercel Blog: How to build agents with filesystems and bash](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash)
- **Engineering blog (Knock, Jul 2026):** Built the Knock Agent to manage customer messaging (workflows, templates, audiences) using a virtual filesystem + ported `just-bash` to Elixir. Rejected the tool-per-type pattern because "would require exposing a tool per resource, bloating the context window without sophisticated routing." The virtual filesystem gives the agent a file-based view of the user's account; the agent explores, scripts changes, and a persist step commits to the real API. — [Knock: Files over tools](https://knock.app/blog/how-we-built-the-knock-agent-virtual-filesystem-and-bash)
- **GitHub repo (vercel-labs/just-bash):** Sandboxed bash interpreter with an in-memory virtual filesystem. Agents execute shell commands (`grep`, `sed`, `awk`, `jq`) without real filesystem access. Powers `bash-tool`, an npm package designed specifically for AI agents to retrieve context from local files without embedding entire files into prompts. — [GitHub: vercel-labs/just-bash](https://github.com/vercel-labs/just-bash)
- **GitHub repo (johannesmichalke/agent-vfs):** Persistent virtual filesystem for AI agents backed by SQLite or Postgres. "The best AI agents already use filesystems as memory. Now your agent can too." Multi-tenant by default, no external services, one table in your database. — [GitHub: johannesmichalke/agent-vfs](https://github.com/johannesmichalke/agent-vfs)
- **GitHub repo (browser-use/browser-use):** 104k+ stars. Web browser as the agent's tool — LLM controls a real browser (Playwright) for tasks that require live page interaction beyond file-based data. Complements the filesystem pattern for cases where data lives behind web interfaces. — [GitHub: browser-use/browser-use](https://github.com/browser-use/browser-use)

## Gotchas

- **Serialization cost.** Your data must be serialized into the virtual filesystem before each agent session. If your API returns deeply nested or circular structures, you'll spend engineering effort on clean serialization. Flat, structured files (JSON with consistent schema) work best; a messy data model produces a messy filesystem.
- **Bash literacy is a prerequisite for agents.** The pattern only works well if your agent model has solid bash/Unix training. Models trained primarily on instruction-following datasets may not compose `find | xargs | jq` pipelines fluently. Test before committing.
- **Sandbox security is real.** A sandboxed bash tool is only as safe as its implementation. Restrict dangerous commands (`rm -rf`, network tools), enforce timeouts, and audit what gets written. AgentFS (Turso) and `just-bash` handle this differently — evaluate the threat model for your use case.
- **The persist step is the trust boundary.** The agent stages changes in the virtual filesystem before committing. If your persist layer blindly trusts writes, a confused agent can corrupt real data. Validate writes against your API schema before executing them against production state.
- **Not everything is a file.** Browser interactions, real-time API calls, and stateful services don't fit the filesystem metaphor. The filesystem pattern is a strong complement to targeted tools — use both. As browser-use shows, some data is only accessible through live page interactions.
