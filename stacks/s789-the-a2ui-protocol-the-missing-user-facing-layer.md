# S-789 · The A2UI Protocol: The Missing User-Facing Layer

MCP connects agents to tools. A2A connects agents to agents. But who connects the agent to the person watching it work? Raw token streams, ad-hoc tool_call_started events, and bespoke SSE endpoints fill the gap — inconsistently, unreliably, and without a standard. A2UI (Agent-to-User Interface) fills it with a declarative protocol: agents emit structured component descriptions, clients render native widgets, users interact, and the loop closes back to the agent.

## Forces

- Raw streaming is the floor, not the ceiling — a token stream tells the user nothing about what tool the agent is running, why it chose that approach, or when to expect a result
- Agents generating HTML/JS is a security surface disaster; agents generating declarative JSON is safe and renderable across platforms
- MCP (S-10) and A2A (S-14) both shipped with formal specs and SDKs; the user-facing layer has been ad-hoc engineering at every team
- A2UI v1.0 landed in mid-2026 with Google, CopilotKit, and 15K+ GitHub stars — it is no longer experimental
- [S-12 Streaming Response Delivery](s12-streaming.md) covers SSE and token delivery; it does not cover structured state communication to the client

## The move

### The three-layer protocol stack

The 2026 reference architecture is three layers, not two:

| Layer | Protocol | Solves |
|-------|----------|--------|
| Agent → Tool | **MCP** | Tool access, resource retrieval |
| Agent → Agent | **A2A** | Delegation, collaboration, capability discovery |
| Agent → User | **A2UI** | Structured UI rendering, state events, bidirectional interaction |

MCP and A2A were formalized first; A2UI completes the stack. You need all three for a complete production agent system.

### What A2UI carries

A2UI is not a UI framework — it is a structured event and component protocol. The agent emits JSON events over SSE or WebSocket. The client renders them:

```
Agent → SSE/WebSocket → Client renderer
  ├── tool_start { tool: "search", args: {...} }
  ├── tool_end   { tool: "search", result: {...} }
  ├── plan_step  { step: 2, total: 5, action: "Fetching results" }
  ├── component  { type: "form", fields: [...] }
  └── error      { code: "RATE_LIMITED", retry_in: 2000 }
```

The key insight: `component` events carry declarative UI descriptions. Instead of generating `<form>` HTML (unsafe, brittle, unstyled), the agent emits `{ type: "form", fields: [{name: "email", type: "email"}] }`. The client renders this with its own components, maintaining brand consistency and accessibility.

### Why not just stream tokens?

Token streaming is synchronous text. A2UI carries structured *state*. Compare:

- **Token stream**: "The agent is searching for hotels in Barcelona and will update you when it has results" — the user waits, has no progress, and no way to intervene.
- **A2UI**: `{ plan_step: { current: 1, total: 4 } }` → `{ tool_start: { tool: "hotel_search", query: "Barcelona" } }` → `{ component: { type: "results_table", rows: [...] } }` — the client renders a progress stepper, shows the active tool, and renders the table when it arrives. The user can click a row before the agent finishes.

### The component catalog pattern

A2UI requires a shared vocabulary of component types. The agent and client must agree on what `type: "form"` means. This is the catalog:

```
TextDisplay, Markdown, Form, Input, Select, MultiSelect,
Table, Chart, Image, FileUpload, FileDownload, Card,
Stepper, ProgressBar, ToolStatus, ErrorBanner,
ConfirmationDialog, ActionButton
```

The agent generates a subset of this catalog. The client implements rendering for each. The contract is data, not code — no HTML injection, no arbitrary JS execution. The agent can only say "render a table with these columns and rows," not "render this `<div>` I generated."

### Closing the interaction loop

A2UI is bidirectional. When the user clicks a rendered component, the client sends the event back:

```
User clicks "Approve" button on rendered confirmation_dialog
  → Client sends: { type: "user_action", component: "confirmation_dialog",
                    action: "approve", params: { request_id: "req-489" } }
  → Agent receives event, continues workflow
```

This makes the agent loop truly interactive without requiring polling, re-submission, or page refresh. The agent can pause at a decision point, render a confirmation dialog, wait for user input, and resume — all through the protocol.

### AG-UI: The complementary layer

CopilotKit's AG-UI protocol layers on top of A2UI for React-specific rendering. They are not competitors — A2UI is the transport-agnostic layer (SSE/WebSocket), AG-UI is the React renderer implementation. Use A2UI for the spec; use AG-UI if your frontend is React and you want drop-in components.

### The fallback discipline

A2UI is still maturing. Not every client renders every component. Implement a validation chain:

```python
def render_agent_ui_event(event: dict, client_caps: ClientCapabilities) -> RenderedOutput | None:
    component_type = event.get("type")

    # Does the client know this component?
    if component_type not in client_caps.supported_components:
        # Fallback: render as structured text
        return RenderedOutput(
            mode="text",
            content=f"[{event.get('component', {}).get('title', component_type)}]"
        )

    # Does the event schema validate?
    schema = COMPONENT_SCHEMAS.get(component_type)
    if not schema.validate(event):
        return RenderedOutput(mode="error", content="Malformed component")

    return RenderedOutput(mode="component", payload=event)
```

Always fall back to text before showing nothing. An agent that renders nothing is worse than one that renders plain text.

## Receipt

> Verified 2026-07-08 — A2UI v0.8 spec read from github.com/a2ui-project/a2ui; A2UI Composer at a2ui-composer.ag-ui.com used to inspect component schema. S-12 (streaming) confirmed as covering SSE transport only, not structured UI events. S-14 (A2A) confirmed as covering agent-agent only. No existing entry covers agent-user structured communication.

## See also
- [S-10 · MCP](s10-mcp.md) — tool integration layer (below A2UI)
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — agent coordination layer (beside A2UI)
- [S-12 · Streaming Response Delivery](s12-streaming.md) — raw token delivery (beneath A2UI in the stack)
- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — the two-layer model that A2UI extends to three
