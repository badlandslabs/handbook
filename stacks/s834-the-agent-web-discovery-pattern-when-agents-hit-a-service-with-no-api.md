# S-834 · The Agent Web Discovery Pattern

When an agent encounters a new web service and needs to call it — but has no schema, no SDK, and no hardcoded integration.

## Situation

Your agent receives a task: look up a flight on united.com, find pricing on Amazon, and check inventory at a retailer's site. These are real services with real APIs. But your agent has no `unified_api` tool. It has web search and a browser. It can try to scrape HTML — but the page changes, the agent guesses wrong, and you get `$NaN`. Or it gives up entirely.

The fundamental problem: **agents can't dynamically discover and call web services** the way browsers or clients do. Web services expose human-readable pages and hope a crawler or scraper can figure it out. There is no standard for a service to tell an agent: here are my capabilities, here are my parameters, here is my auth, here is my policy.

## Forces

- Every new web service requires a bespoke integration — custom wrapper, schema mapping, auth negotiation. At 100+ services, this is a full-time job
- HTML scraping is fragile: page structure changes, forms are stateful, JavaScript renders content the agent can't see
- Agents need machine-readable service manifests at runtime — not hardcoded at build time
- The `.well-known/ai` endpoint (IETF draft, March 2026), World Agent Web protocols, and llms.txt are all emerging simultaneously as competing/complementary solutions — no clear winner yet
- Auth is the hardest part: services need to authenticate agents without leaking credentials or allowing unlimited access

## The move

**Layer 1 — Discovery endpoint.** A web service exposes `/.well-known/ai` returning a JSON manifest:

```json
{
  "name": "United Flights API",
  "version": "1.0",
  "description": "Real-time flight search and booking",
  "actions": [
    {
      "name": "search_flights",
      "description": "Find flights between two airports on a date",
      "parameters": {
        "type": "object",
        "properties": {
          "origin":      { "type": "string", "format": "IATA" },
          "destination": { "type": "string", "format": "IATA" },
          "date":        { "type": "string", "format": "date" }
        },
        "required": ["origin", "destination", "date"]
      },
      "auth": { "type": "Bearer", "scope": "read:flights" }
    }
  ],
  "llm_hint": "token-efficient: use IATA codes, ISO dates, no timezone strings"
}
```

The `llm_hint` field is the differentiator — a direct instruction to the LLM about how to format parameters for this service. Token-efficient, unambiguous, service-specific.

**Layer 2 — Protocol stack.** Three protocols address different concerns:

- **HADP** (Hypermedia Agent Description Protocol): standardizes the manifest format above
- **ACDL** (Agent Capability Definition Language): describes complex workflows, stateful interactions, and multi-step procedures the agent must follow
- **AWCP** (Agent Web Capability Policy): describes rate limits, usage policies, auth requirements, and acceptable use

Together they form a stack: describe → define → constrain.

**Layer 3 — Agent workflow.** On encountering a new service, the agent:

1. Fetches `/.well-known/ai`
2. Parses available actions and picks the right one
3. Reads `llm_hint` for parameter formatting
4. Reads AWCP for auth requirements and rate limits
5. Makes the call directly — no HTML scraping, no hardcoded wrapper

```python
# Minimal discovery client (conceptual)
async def call_service(agent_id: str, service_url: str, action: str, params: dict):
    # 1. Fetch the manifest
    manifest = await fetch_well_known(f"{service_url}/.well-known/ai")
    
    # 2. Find the action
    act = next(a for a in manifest["actions"] if a["name"] == action)
    
    # 3. Format params per llm_hint
    params = format_per_hint(params, act.get("llm_hint", ""))
    
    # 4. Get auth token
    token = await get_agent_token(agent_id, act["auth"]["scope"])
    
    # 5. Call the service
    return await http_post(f"{service_url}/{action}", params, 
                          headers={"Authorization": f"Bearer {token}"})
```

**The llms.txt companion.** As a fallback or complement, `GET /llms.txt` on any website returns a plain-text summary of page structure, key data fields, and navigation intent — designed for agents to understand content without rendering JavaScript. Both patterns (`.well-known/ai` + `llms.txt`) can coexist: structured discovery for APIs, prose discovery for content.

## Receipt

> Verified 2026-07-08 — IETF draft `draft-aiendpoint-ai-discovery-00` published March 2026 defines the `/.well-known/ai` endpoint with the JSON manifest structure above. World Agent Web (HN/merriBan, Jun 2026) defines the three-protocol HADP/ACDL/AWCP stack. The llms.txt convention (at risk since 2024) is gaining renewed attention as an agent-facing fallback. At time of writing, no production service has shipped a `/.well-known/ai` endpoint — the pattern is active R&D, not proven in production. The approach is directionally sound but the ecosystem is pre-convergence.

## See also

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — internal agent discovery via Agent Cards; this entry covers web/service discovery
- [S-74 · Agent Capability Registry](s74-agent-capability-registry.md) — in-house registry for internal agents; this entry covers external web service discovery
- [S-789 · The A2UI Protocol](s789-the-a2ui-protocol.md) — the user-facing layer that pairs with service discovery
