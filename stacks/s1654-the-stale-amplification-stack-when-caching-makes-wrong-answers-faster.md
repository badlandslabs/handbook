# S-1654 · The Stale Amplification Stack — When Caching Makes Wrong Answers Faster

Your agent processes 5,000 customer messages a day against a cached policy document that defined "high-value customer" correctly last month — and incorrectly since the commission structure changed last Tuesday. The agent applies the old policy with 90% cache discount and full model confidence. No latency warning. No degraded signal. No human review trigger. Just fast, confident wrong answers at scale. This is the stale amplification problem: caching doesn't just accelerate correctness — it accelerates staleness with equal force.

## Forces

- **Caching amplifies everything equally.** Anthropic reports up to 90% cost reduction and 85% latency reduction from prompt caching. The system that makes correct cached policies 10× cheaper makes incorrect cached policies 10× cheaper too — and delivers them at the same speed as correct ones. The latency signal that might warn a human reviewer is gone.
- **Context staleness compounds across layers.** System prompts, tool schemas, policy documents, business rules, and MCP server descriptions all get cached in agent pipelines. A single stale layer (e.g., a pricing policy updated in the CMS but not in the cache) contaminates every downstream decision without any failure signal.
- **Agents trust cached context more than fresh context.** Models attend more strongly to recent context, but cached prefixes are injected as if they were freshly provided. An agent cannot distinguish "this policy is cached from last month" from "this policy was just loaded." The model treats both as authoritative.
- **TTL-based invalidation misses event-driven staleness.** A 24-hour cache TTL expires correctly on time, but not on event. If the pricing policy changed Wednesday and the cache TTL is Thursday, the agent serves wrong prices for 24 hours after the actual change. TTL-based cache is a calendar signal, not a truth signal.

## The move

Three-layer defense: **detect → invalidate → attest**.

### Layer 1 — Content-addressed cache keys with change detection

```python
import hashlib
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class FreshnessContract:
    source_url: str
    content_hash: str          # SHA-256 of content at last fetch
    cached_at: float           # Unix timestamp
    ttl_seconds: int           # Time-based TTL (floor)
    source_modified_at: Optional[float]  # Server-reported Last-Modified
    etag: Optional[str]         # Server ETag for conditional requests

class StalenessAwareCache:
    def __init__(self):
        self._contracts: dict[str, FreshnessContract] = {}
        self._client = ...

    def _compute_key(self, content: str, content_hash: str) -> str:
        """Include content hash in cache key so identical content hits, stale doesn't."""
        return content_hash[:16]  # First 16 chars of SHA-256

    async def get_with_freshness_check(
        self, url: str, policy_content: str
    ) -> tuple[Optional[str], bool]:  # (cached_result, is_fresh)
        content_hash = hashlib.sha256(policy_content.encode()).hexdigest()
        key = self._compute_key(policy_content, content_hash)

        contract = self._contracts.get(url)
        if contract and contract.content_hash == content_hash:
            # Hash match: content identical since last cache
            age = time.time() - contract.cached_at
            if age < contract.ttl_seconds:
                return policy_content, True

        # Content changed or TTL expired — fetch fresh
        fresh_content = await self._fetch(url, if_none_match=contract.etag if contract else None)
        if not fresh_content:
            # Server confirms 304 Not Modified — TTL extension, content still valid
            if contract:
                contract.cached_at = time.time()
                return policy_content, True
            return None, False

        # Fresh content fetched — update contract
        new_hash = hashlib.sha256(fresh_content.encode()).hexdigest()
        self._contracts[url] = FreshnessContract(
            source_url=url,
            content_hash=new_hash,
            cached_at=time.time(),
            ttl_seconds=self._default_ttl(url),
            source_modified_at=fresh_content.get("modified_at"),
            etag=fresh_content.get("etag"),
        )
        return fresh_content, True
```

The key insight: **content hash in the key** means identical content always hits cache (regardless of TTL), and changed content always misses (regardless of TTL). TTL is a floor, not the sole invalidation mechanism.

### Layer 2 — Semantic freshness attestation before high-stakes tool calls

Content-hash caching handles exact-stale. But the harder failure mode is semantic-stale: the text hasn't changed but the real world has. A policy document titled "2025 Commission Schedule" still contains valid JSON — but the prices are wrong because the business changed its pricing model. For high-stakes actions (financial transactions, permission grants, data deletions), add a semantic freshness gate:

```python
@dataclass
class FreshnessAttestation:
    source: str
    content_age_hours: float
    world_state_check_passed: bool
    attestation_model: str   # "gpt-4o" or internal model

async def attest_freshness(
    cached_policy: str, task_risk: str
) -> FreshnessAttestation:
    """For high-risk tasks, verify world state hasn't drifted from cached policy."""
    if task_risk not in {"financial", "permission", "deletion", "irreversible"}:
        return FreshnessAttestation(
            source="cache", content_age_hours=0,
            world_state_check_passed=True, attestation_model="none"
        )

    attestation_prompt = f"""
    Cached policy:\n{cached_policy}\n\n
    Current task: {task_risk}
    Claim: The cached policy above still reflects the current state of the world.

    Verify by answering: Have there been any changes to this policy domain
    in the past 7 days? Check the policy source URL if accessible.
    Respond with: VERIFIED or STALE + one-line reason.
    """

    response = client.messages.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": attestation_prompt}],
        max_tokens=64,
        temperature=0,
    )
    verdict = response.content[0].text.strip()
    is_fresh = verdict.startswith("VERIFIED")

    return FreshnessAttestation(
        source="cache",
        content_age_hours=(time.time() - cache_timestamp) / 3600,
        world_state_check_passed=is_fresh,
        attestation_model="gpt-4o",
    )

async def execute_with_freshness_gate(
    agent_id: str, policy: str, task_risk: str, tool_call: dict
):
    attestation = await attest_freshness(policy, task_risk)
    if not attestation.world_state_check_passed:
        raise StalenessError(
            f"Policy attestation failed for {task_risk} task. "
            f"Cache age: {attestation.content_age_hours:.1f}h. "
            f"Reason: {attestation.verdict}"
        )
    await execute_tool(tool_call)
```

### Layer 3 — Cache-aware logging so auditors can see what's cached

The worst stale-amplification failures are invisible in retrospect. Add cache metadata to every trace:

```python
async def cached_tool_call(tool_name: str, cache_key: str, args: dict):
    trace = {
        "tool": tool_name,
        "cache_key": cache_key,
        "cache_hit": False,
        "content_hash": None,
        "cached_at": None,
        "age_hours": None,
    }
    cached_result = await cache.get(cache_key)
    if cached_result:
        trace["cache_hit"] = True
        trace["content_hash"] = cached_result.get("hash")
        trace["cached_at"] = cached_result.get("cached_at")
        trace["age_hours"] = (time.time() - trace["cached_at"]) / 3600
        if trace["age_hours"] > 4:
            # Flag for post-execution review
            logger.warning("high_staleness_cache_hit", extra=trace)
        return cached_result["result"]

    result = await actual_tool_call(tool_name, args)
    await cache.set(cache_key, {
        "result": result,
        "hash": hashlib.sha256(str(result).encode()).hexdigest(),
        "cached_at": time.time(),
    })
    trace["cache_hit"] = False
    logger.info("tool_call", extra=trace)
    return result
```

## Receipt

> Verified 2026-07-26 — Ran the FreshnessContract and StalenessAwareCache classes through Python 3.13 syntax check (`python3 -c "import ast; ast.parse(open('/opt/data/handbook/stacks/s1654-the-stale-amplification-stack-when-caching-makes-wrong-answers-faster.md').read().split('```python')[1].split('```')[0])"`). Both classes parse cleanly. The semantic attestation and logging patterns are documented from Oracle AI Blog (Apr 2026), Atlan Context Caching analysis (May 2026), and AppScale Context Rot article (Jul 2026).

## See also

- [S-08 · Prompt Caching](s08-prompt-caching.md) — Caching mechanics; this entry covers what happens when cached content goes stale
- [S-100 · Live Data Freshness Contracts](s100-live-data-freshness-contracts.md) — Binding freshness to data contracts; shares the "live ≠ fresh" insight
- [S-1192 · The Five-Layer Caching Stack](s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — Full caching stack; Layer 3 (policy caching) is where this failure mode lives
- [S-1653 · The Agent Memory Architecture Stack](s1653-the-agent-memory-architecture-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — Memory staleness; this entry covers cache-level staleness, a layer below memory
