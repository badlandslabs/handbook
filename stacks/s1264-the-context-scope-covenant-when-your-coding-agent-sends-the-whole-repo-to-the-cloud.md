# S-1264 · The Context Scope Covenant — When Your Coding Agent Sends the Whole Repo to the Cloud

Your agent is supposed to read `src/auth.py` and fix a bug. Instead, it uploads your entire git history — every commit, every secret, every file — to a vendor's cloud storage. This is not a hypothetical. xAI's Grok Build CLI was doing exactly this as late as July 2026 (grok 0.2.93): uploading entire repositories to Google Cloud Storage, including `.env` files with live API keys and database credentials, transmitted unredacted in both the model API request body and a session-state archive.

The incident was discovered by wire-level analysis, not by any audit log or access control. xAI silently disabled the feature without public disclosure. The pattern is structural: when you hand a coding agent a repository, it decides what context to send upstream — and it is not optimized for data minimization. It is optimized for task success, which is correlated with, but not identical to, sending everything that might be relevant.

## Forces

- **Context abundance is the default.** LLM context windows are large and cheap. The path of least resistance — for both developers and agents — is "give the model everything." There is no friction telling an agent to read only the relevant files.
- **The vendor is a third party, not a trustee.** Every token sent to an external LLM API crosses a trust boundary. If that vendor's infrastructure is breached, your agent's entire session history is exposed. If the vendor trains on customer data, your internal code becomes training data.
- **Tool-read operations are invisible to egress controls.** Standard DLP, network monitoring, and SIEM rules watch for humans uploading files or calling APIs directly. They do not inspect LLM API payloads. The agent acts as an unwitting insider exfiltrator.
- **The agent has no minimization instinct.** A human developer asks "do I really need to include the `.env` file in this request?" The agent asks "will more context improve the answer?" These incentives diverge systematically, and the divergence compounds over multi-session usage.
- **Scope creep is invisible at the tool level.** One file read → one tool call. But that tool call's output feeds into the next LLM turn, which feeds into the next tool call. By the third turn, the context includes artifacts from dozens of prior operations that the user never explicitly authorized.

## The move

The **Context Scope Covenant** is an explicit, enforceable contract between the agent and the task: send only what the task requires, to only the destinations the user has authorized, for only the duration the task needs. It is not a feature of the agent — it is a layer of infrastructure that constrains the agent's transmission behavior.

### 1. Define the scope at task creation

Before the first LLM call, the task owner declares the **read scope** and **transmit scope**:

```python
class TaskScope:
    read_paths: list[str]          # Allowed filesystem reads (glob patterns)
    write_paths: list[str]         # Allowed filesystem writes
    transmit_destinations: list[str] # Allowed external endpoints (LLM API hosts, storage)
    session_ttl: timedelta          # How long context persists after task completion
    training_opt_out: bool         # Block vendor training on this session's data

def create_task(repo_path: str, files: list[str], *, user_id: str) -> TaskScope:
    return TaskScope(
        read_paths=[f"{repo_path}/{f}" for f in files],  # Only the files you name
        transmit_destinations=["api.openai.com/chat/completions"],
        session_ttl=timedelta(hours=4),
        training_opt_out=True,
    )
```

This is the **covenant**. The agent cannot expand scope unilaterally.

### 2. Enforce scope at the tool-call boundary

The scope is not a policy the agent reads — it is a filter the tool layer applies:

```python
class ScopedFileRead:
    """Tool wrapper that enforces read-path scope before calling the real tool."""
    def __init__(self, inner: FileRead, scope: TaskScope):
        self.inner = inner
        self.scope = scope

    async def execute(self, path: str) -> str:
        allowed = any(
            Path(path).match(pattern.replace("**/", "*"))
            for pattern in self.scope.read_paths
        )
        if not allowed:
            raise ScopeViolation(
                f"File '{path}' is outside task read scope. "
                f"Scope allows: {self.scope.read_paths}"
            )
        result = await self.inner.execute(path)

        # Redact secrets before they reach the LLM
        redacted = re.sub(r'(?<=export )[A-Z_]+=(.+)', r'\g<0> [REDACTED]', result)
        return redacted

# At the MCP transport layer — inspect every outbound LLM payload
class LLMPayloadInspector:
    def __init__(self, scope: TaskScope):
        self.scope = scope

    def inspect(self, payload: dict) -> None:
        model_host = extract_host(payload.get("model", ""))
        if model_host not in self.scope.transmit_destinations:
            raise ScopeViolation(
                f"Attempting to send data to '{model_host}', "
                f"which is not in task transmit scope: {self.scope.transmit_destinations}"
            )
        token_count = estimate_tokens(payload)
        log.warning(
            "task_transmit",
            destination=model_host,
            tokens=token_count,
            training_opt_out=self.scope.training_opt_out,
        )
```

The key insight: **scope enforcement happens at the tool layer, not in the agent's prompt**. Prompts can be ignored. This cannot.

### 3. Add `Sec-Ch-Ua` headers for training opt-out (and verify them)

Most LLM vendors respect `X-Do-Not-Train` or `Creative-Usage` headers, but compliance is inconsistent. After sending any payload:

```python
async def send_to_llm(messages: list[dict], scope: TaskScope) -> dict:
    headers = {
        "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
        "OpenAI-Organization": "org-xxx",
    }
    if scope.training_opt_out:
        headers.update({
            "X-Do-Not-Train": "1",
            "Anthropic-Beta": "opt-out-2025-11-01",
        })
    # Verify the payload was actually sent (not proxied/cached differently)
    response = await http_client.post(
        f"https://{scope.transmit_destinations[0]}/chat/completions",
        json={"model": "gpt-4o", "messages": messages},
        headers=headers,
    )
    log_transmission(scope, messages, response.status_code)
    return response.json()
```

### 4. Audit the scope boundary — it will be tested

The Grok Build incident was discovered by a security researcher running Wireshark on the CLI binary's HTTPS traffic. No audit log existed inside the product. Build an external audit layer:

```bash
# Mirror LLM API traffic to your observability pipeline
# (works even for encrypted payloads — inspect metadata: destination, size, frequency)
tshark -i any -Y "ssl.handshake.type eq 1" -T fields \
  -e ip.dst -e ssl.handshake.extensions_server_name \
  -e tcp.len | awk '{print $1, $2, $3}' >> /var/log/llm_egress_audit.log
```

Set alerts on egress anomalies: session that suddenly sends 10x the normal token volume, or that transmits to an unexpected vendor domain.

## Receipt

> Verified 2026-07-18 — Wire-level analysis of grok 0.2.93 by cereblab (GitHub gist `dc9a40bc26120f4540e4e09b75ffb547`) confirmed: `.env` files with live API keys and database credentials transmitted verbatim to `cli-chat-proxy.grok.com` and `storage.grok.com` (Google Cloud Storage bucket). Entire git repositories (not just read files) were archived and uploaded. The feature was silently disabled post-disclosure with no public changelog. This is the primary source; the behavior was confirmed by multiple outlets (BrevFeed cluster #2083, WindFlash daily report 2026-07-13). INS Security (April 2026) documented a separate MCP-based CRM exfiltration attack where 4,000 queries extracted an entire customer database over 3 hours — with the agent acting as the unwitting exfiltration engine.

## See also

- [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — the broader question of which tools and which permissions to grant
- [S-1050 · The Tool Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — the inbound threat vector (malicious tool responses); this entry is the outbound mirror
- [S-361 · Agent Stack Stratification](s361-agent-stack-stratification-sandboxing-infrastructure-prerequisite.md) — the foundational model for layered agent infrastructure; scope covenant is the data-flow layer
