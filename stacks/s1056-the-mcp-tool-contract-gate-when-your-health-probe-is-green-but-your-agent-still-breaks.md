# S-1056 · The MCP Tool Contract Gate — When Your Health Probe Is Green but Your Agent Still Breaks

Your CI is green. Your health probe returns 200. Your agent is broken in production. S-999 diagnosed the problem — MCP schema drift at 7.1% over 48 hours. This entry fixes it: a contract gate in your CI/CD pipeline that treats MCP tool schemas as a versioned, testable API surface, just like any other service boundary.

## Forces

- **MCP tool contracts live outside version control.** The `tools/list` response is a runtime artifact. Nothing in your repo captures what tools existed, what their schemas were, or whether they changed between builds.
- **MCP breaking changes don't surface as errors.** Renaming a tool produces no 500. The agent gets a stale cached definition and calls a method that no longer exists. Silent failure, no log line.
- **Every tuning session is a breaking change opportunity.** Tool names, parameter types, required fields, output shape — all mutable by the server team without coordination from the agent team.
- **The MCP ecosystem has no built-in versioning.** Unlike OpenAPI, MCP has no standard for backwards compatibility guarantees, deprecation windows, or breaking change detection.

## The Move

Treat your MCP server's tool surface as a published API contract. Gate every deployment on contract compatibility.

**Layer 1: Schema snapshot CI**

Before shipping an MCP server change, capture a baseline snapshot:

```bash
# Install mcp-contracts CLI
npx @mcp-contracts/cli baseline update \
  --command "node ./dist/server.js" \
  --output ./schemas/mcp-baseline.json

git add schemas/mcp-baseline.json
```

In your CI pipeline, on every server change:

```bash
# CI gate — fails if schema drifted
npx @mcp-contracts/cli baseline verify \
  --command "node ./dist/server.js" \
  --baseline ./schemas/mcp-baseline.json

# Outputs: PASS or BREAKING CHANGE: publishDraft renamed to publishArticle
# Required param 'draftId' added to publishArticle (was optional)
```

Add this to GitHub Actions:

```yaml
- name: MCP Contract Gate
  run: |
    npx @mcp-contracts/cli baseline verify \
      --command "node ./dist/server.js" \
      --baseline ./schemas/mcp-baseline.json
  env:
    MCP_SERVER_URL: ${{ secrets.MCP_SERVER_URL }}
```

**Layer 2: Breaking-change taxonomy**

Classify every schema change before merging:

| Change Type | Action |
|-------------|--------|
| Tool removed | Major version bump + 30-day grace period with warning |
| Required param added | Breaking — negotiate with all agent consumers first |
| Optional param added | Safe — ship with notification |
| Tool renamed | Major version + alias for 14 days |
| Return type changed | Breaking — run behavioral tests |
| New tool added | Safe — no agent breakage |

**Layer 3: Behavioral smoke testing (bellwether)**

Beyond schema drift, validate that tool behavior actually works:

```bash
npx @bellwether/cli test \
  --server-command "node ./dist/server.js" \
  --schema-snapshot ./schemas/mcp-baseline.json \
  --test-suite ./tests/contract-tests/
```

Bellwether runs deterministic validation against the snapshot and optionally uses an LLM to explore behavioral edge cases the snapshot can't catch (e.g., a tool that returns 200 but with an empty payload).

**Layer 4: Consumer notification**

When a breaking change slips through Layer 1 (or requires immediate rollout):

```yaml
# Automated PR to every consumer repo
- name: Notify consumers
  if: steps.contract-gate.outputs.status == 'breaking'
  run: |
    # Tag agent repos that pin this server version
    gh issue create \
      --title "Breaking MCP contract change in v${{ steps.version.outputs.current }}" \
      --body "Tool surface changed. See migration guide: docs/mcp-migration-v${{ steps.version.outputs.current }}.md"
    # Pin consumers to last-known-good version
    gh pr create --base main --title "Pin MCP server to v${{ steps.version.outputs.previous }}"
```

**The gate that compounds**

The MCP tool contract gate creates a feedback loop: every schema change is captured, classified, and communicated before it reaches agent consumers. The 7.1% drift rate doesn't go away, but it stops being a silent production incident — it becomes a routine, tracked, communicated event.

## Receipt

> Verified — 2026-07-13
> `mcp-contracts` baseline/update/verify commands executed against a sample MCP server. Verified that `baseline update` produces a deterministic JSON snapshot of all tool names, input schemas, and output schemas. Verified that `baseline verify` correctly identifies: tool renames (exit code 1 + diff output), required param additions (exit code 1), new optional fields (exit code 0). `bellwether` CLI installed and smoke-tested against a local MCP server — deterministic schema tests pass, behavioral LLM exploration requires `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` env var. GitHub Actions workflow pattern verified against `mcp-contracts` examples/ directory. The gate works at build time: an engineer who renames `publishDraft` to `publishArticle` without updating the baseline gets a CI failure before merge, not a production outage.

## See also

- [S-999 · The Silent Tool Catalog: MCP Schema Drift](s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-your-agent-breaks.md) — the problem this entry operationalizes
- [S-1033 · The Behavioral Version Stack](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — four layers of independently-evolving version surfaces
- [S-978 · Tool Catalog Poisoning](s978-the-tool-catalog-poisoning-runtime-response-injection-beyond-schema.md) — supply-chain security for MCP servers
- [S-1000 · Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — structural safeguards that compound with contract gates
