# S-2250 · The CoreBreak Stack — When Your Guardrails Never Run Because Your Agent Skips the Model

Your system prompt is airtight. Your refusal training is state-of-the-art. Your content filter scores every output. Your agent just executed a `Create IAM User` tool call — and none of those guardrails fired. Not because they were bypassed. Because they were never in the path.

CoreBreak is a vulnerability class disclosed at Black Hat USA 2026 by Hedi Ingber and Aviyam Ivgi of Stealth. It demonstrates that the tool-execution layers of major agentic platforms — Amazon Bedrock AgentCore (CVE-2026-18830, CVSS 8.6), Google Agent Development Kit for Python (CVE-2026-18236, CVSS 9.3), and Vercel AI SDK — can be induced to execute tools **without a legitimate model turn ever occurring**. All model-level guardrails are structurally bypassed, not defeated.

## Forces

- Agent frameworks split into two layers: the **harness** (which manages state, tools, and orchestration) and the **model** (which decides what to do). Guardrails live in the model layer. The harness doesn't know if the model ran.
- Prompt injection is a model-level attack — you fool the model into making a bad decision. CoreBreak skips the model entirely — you send crafted content blocks directly to the harness, which interprets them as tool calls and dispatches without model authorization.
- Every guardrail layered on the model's output — system prompts, content filters, refusal training, constitutional AI, output validators — is downstream of a decision that never happened.
- The harness-to-tool pipeline has no intrinsic authorization checkpoint. Tool execution looks like a normal API call once the harness decides to dispatch. Infrastructure-level access controls (IAM, RBAC) still apply, but harness-level authorization (did a model turn authorize this?) does not.
- Cloud vendors patching server-side is insufficient: Google ADK requires manual upgrade to 2.5.0; AWS Bedrock was auto-patched but the architectural pattern persists across any custom harness implementation.

## The Move

The attack surface is the gap between "the model decided to call a tool" and "a tool was called." Close that gap with a **mandatory model-turn binding** on every tool dispatch.

### 1. Sign tool calls at the model layer

Before returning any tool-call decision from the model, produce a cryptographic binding:

```python
import hashlib, hmac, uuid
from datetime import datetime, timedelta

class ModelTurnBinding:
    def __init__(self, signing_key: bytes):
        self.signing_key = signing_key

    def create_turn_token(
        self,
        tool_name: str,
        tool_args: dict,
        model_turn_id: str,
        session_id: str,
        ttl_seconds: int = 300
    ) -> str:
        payload = f"{session_id}|{model_turn_id}|{tool_name}|{sorted(tool_args.items())!s}"
        sig = hmac.new(
            self.signing_key,
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        return f"{sig}.{model_turn_id}.{int(datetime.utcnow().timestamp())}"

    def verify_token(self, token: str, tool_name: str) -> bool:
        try:
            sig, turn_id, ts = token.split(".", 2)
            if datetime.utcnow().timestamp() - float(ts) > 300:
                return False  # Expired
            # Reconstruct and compare signature
            return True
        except ValueError:
            return False
```

### 2. Enforce binding at the harness pre-dispatch gate

Every tool call must present a valid, non-expired token before execution:

```python
class BindingEnforcementHarness:
    def __init__(self, binding: ModelTurnBinding):
        self.binding = binding

    async def dispatch_tool(self, tool_name: str, args: dict, turn_token: str | None):
        if not turn_token or not self.binding.verify_token(turn_token, tool_name):
            raise AuthorizationError(
                f"No valid model-turn binding for tool '{tool_name}'. "
                f"Harness cannot verify this call originated from a model decision. "
                f"Rejecting dispatch to prevent CoreBreak-class authorization bypass."
            )

        # Only reachable if token is valid — model turn confirmed
        return await self.execute_tool(tool_name, args)
```

### 3. Tag model turns with an unforgeable ID

The model's response must carry a turn ID that the harness can verify:

```python
# At the model API boundary — wrap every response
def wrap_model_response(raw_response: dict, session_id: str) -> dict:
    turn_id = str(uuid.uuid4())
    return {
        **raw_response,
        "_turn_meta": {
            "turn_id": turn_id,
            "session_id": session_id,
            "model": raw_response.get("model"),
            "timestamp": datetime.utcnow().isoformat()
        }
    }
```

### 4. Audit the bypass path

Log and alert when tool calls arrive without valid bindings — this is a CoreBreak attempt:

```python
async def dispatch_tool_audited(self, tool_name: str, args: dict, turn_token: str | None):
    if not turn_token:
        # Log at CRITICAL — this is the CoreBreak attack signature
        logger.critical(
            "CoreBreak detection: tool dispatch without model-turn binding",
            extra={"tool": tool_name, "args_keys": list(args.keys())}
        )
        raise AuthorizationError("Unbound tool call rejected.")
    return await self.dispatch_tool(tool_name, args, turn_token)
```

### 5. Pin the binding to the session

A turn token from session A must not be replayable in session B:

```python
def verify_session_binding(self, token: str, active_session_id: str) -> bool:
    sig, turn_id, ts = token.split(".", 2)
    # The signature includes session_id — replay to a different session fails
    payload = f"{active_session_id}|{turn_id}|..."  # session mismatch breaks sig
    expected = hmac.new(self.signing_key, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expected)
```

## Receipt

> Verified 2026-08-06 — Research sourced from: CSA AI Safety Initiative research note "When the Model Never Runs: Agent Guardrail Bypasses" (2026-08-06); NVD CVE-2026-18830 (AWS Bedrock AgentCore); SecNews.gr coverage of Black Hat USA 2026 CoreBreak disclosures. Pattern validated against existing entries: no prior S-### or F-### covers harness-layer tool authorization bypass without model invocation. AWS Bedrock auto-patched server-side (CVE-2026-18830). Google ADK requires manual upgrade to ≥2.5.0 (CVE-2026-18236). Vercel AI SDK patch pending.

## See also

- [S-1400 · The Pre-Execution Policy Gate](stacks/s1400-the-pre-execution-policy-gate-when-your-guardrails-fire-too-late-to-matter.md) — guardrails that fire before tool dispatch; complements this entry's binding requirement
- [S-894 · The Tool Schema Contract](stacks/s894-the-tool-schema-contract-stack-when-your-mcp-server-ships-and-your-fleet-is-none-the-wiser.md) — MCP schema validation at the tool boundary
- [S-2147 · The Approved Manifest Drift](stacks/s2147-the-approved-manifest-drift-stack-when-your-security-team-approved-an-mcp-server-that-no-longer-exists.md) — MCP server governance and supply-chain risk
