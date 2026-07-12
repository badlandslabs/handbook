# S-814 · The WebMCP Stack: Websites That Talk Back to Agents

When an agent browses a website today, it does something absurd: it takes a screenshot, sends it to a vision model, and asks the model to guess which rectangle is the "Buy Now" button. That's a billion-parameter model squinting at pixels — expensive, slow, and fragile to the slightest UI change. WebMCP (Web Model Context Protocol) flips this: websites declare their tools explicitly, and agents call them like APIs. The web becomes a documented, typed surface instead of a visual puzzle.

## Forces

- **DOM was designed for rendering, not machine consumption.** CSS class names like `.css-1a2b3c`, div soup, and dynamic SPA rendering make programmatic discovery brittle. An agent that works today breaks next Tuesday when the dev team refactors the nav.
- **Vision-based browsing is economically painful.** A GPT-4o or Claude vision call to read a single page costs $0.05–0.20. An agent doing 50-page research tasks spends more on vision than on the reasoning model. WebMCP eliminates the vision call entirely for sites that support it.
- **The agent-to-website interaction is one-directional.** MCP standardizes how agents consume tools from servers. A2A standardizes how agents talk to each other. Neither addresses how websites expose themselves as tool providers to agents. That gap is WebMCP.
- **Bots are 51% of web traffic.** The web was designed for humans. As agents become a primary audience, the medium needs a machine-readable interface — not just HTML for humans to parse.

## The move

WebMCP is a W3C Draft Community Group Report (February 10, 2026), developed by engineers at Google and Microsoft, maintained by the W3C Web Machine Learning Community Group. Available in Chrome 146 Canary behind a flag. It exposes two APIs:

### Declarative API (HTML attributes)

Add attributes directly to HTML elements:

```html
<!-- A flight search form becomes an explicit tool -->
<form webmcp:tool="search_flights"
      webmcp:param:origin="text"
      webmcp:param:destination="text"
      webmcp:param:date="date">
  <input name="origin" placeholder="Origin">
  <input name="destination" placeholder="Destination">
  <input name="date" type="date">
  <button type="submit">Search</button>
</form>

<!-- A checkout action -->
<button webmcp:tool="book_ticket"
        webmcp:param:flight_id="@selectedFlight"
        webmcp:param:passengers="number">
  Confirm Booking
</button>
```

The browser reads these attributes and registers the tool with the in-browser agent runtime. No JavaScript, no vision call, no guessing.

### Imperative API (JavaScript)

For complex interactions that HTML forms can't express:

```javascript
// Expose a search tool with full schema
navigator.webMCP.registerTool({
  name: "search_products",
  description: "Search the product catalog with filters",
  parameters: {
    type: "object",
    properties: {
      query:   { type: "string", description: "Search term" },
      category: { type: "string", enum: ["electronics", "clothing", "home"] },
      maxPrice: { type: "number" }
    },
    required: ["query"]
  }
}, async ({ query, category, maxPrice }) => {
  const results = await productDB.search({ query, category, maxPrice });
  return { items: results, count: results.length };
});

// Expose a state channel for live UI data
navigator.webMCP.registerStateChannel("cart", (sendUpdate) => {
  cart.on("change", sendUpdate);
});
```

The state channel is key: it lets the agent read live session data (shopping cart, selected items, form state) without screen-scraping. The agent knows exactly what's in the cart, what's selected, what validation errors exist — structured data, not pixel interpretation.

### The integration stack

```
Agent runtime (Claude, GPT, etc.)
    ↓
Browser (Chrome 146+ with WebMCP flag)
    ↓ reads webmcp:tool attributes + JS registrations
WebMCP tool registry (per-tab)
    ↓ structured tool calls
Website's WebMCP-exposed tools
    ↓
Direct API calls — no vision, no DOM scraping
```

### Contrast: vision agent vs. WebMCP agent

**Vision-based agent browsing a travel site:**
1. Screenshot the page → vision API call ($0.05–0.20)
2. Model identifies search form, extracts field positions
3. Agent fills form by simulating clicks at pixel coordinates
4. Screenshot the results → vision call again
5. Identify flight cards by visual layout → fragile on redesign
6. Click "book" → pixel-level guess

**WebMCP agent:**
1. Query `list_tools()` → returns `["search_flights", "book_ticket", "cancel_booking"]` with schemas
2. Call `search_flights({origin: "SFO", destination: "LAX", date: "2026-07-15"})`
3. Receive structured JSON response — no vision, no pixels
4. Call `book_ticket({flight_id: "FL-441", passengers: 2})`
5. Receive structured confirmation

Token cost: $0.001–0.005 per page vs $0.05–0.20. Reliability: structurally immune to CSS class renaming or nav bar refactors.

### Security angle

WebMCP is a narrowing, not a widening, of the attack surface:

- **Explicit tool surface:** The agent sees only the tools the site declared. An agent browsing a banking site with WebMCP sees `view_balance`, `initiate_transfer`, `pay_bill` — and nothing else. It cannot discover or call tools that weren't explicitly exposed.
- **No capability inference:** Vision-based agents must infer what actions are possible from visual cues. WebMCP removes the inference step, which closes the attack surface of "agent guesses wrong and triggers unintended functionality."
- **State channel bounds:** The `registerStateChannel` API gives the agent read access to declared state. Write operations still require explicit tool calls with typed parameters. No blind form submission.

The security model is "explicit deny" vs. "implicit allow" — agents can only act on what was declared.

## When to use it

- **Use WebMCP** when you're building or integrating with sites that will opt into the standard, especially transactional sites (travel, e-commerce, booking, finance) where agents need reliable, low-cost navigation.
- **Use vision-based agents** (S-15) when the target site doesn't support WebMCP, when the interaction requires visual verification (CAPTCHA, charts, diagrams), or when scraping arbitrary third-party sites.
- **Use Playwright MCP** (S-10) for controlled automation where you own both the agent and the browser — WebMCP is for third-party sites.

## Receipt

> Verified 2026-07-08 — W3C WebMCP spec at [w3c.github.io/webmachinelearning/webmcp](https://w3c.github.io/webmachinelearning/webmcp/) confirms the Declarative API (HTML attributes) and Imperative API (JS registration) as the two core surfaces, and the state channel mechanism. Chrome 146 Canary availability confirmed via [Chrome Status](https://chromestatus.com). A2A Protocol blog's WebMCP guide (a2aprotocol.ai, Feb 2026) provides the economic contrast: vision = $0.05–0.20/page vs WebMCP = $0.001–0.005/page. Bot traffic = 51% confirmed via Medium reporting on Chrome WebMCP launch.

## See also

[S-15](s15-browser-computer-use-agents.md) · [S-10](s10-mcp.md) · [S-14](s14-a2a-protocol.md) · [S-811](s811-the-mcp-stack-from-protocol-to-production-connectivity-layer.md) · [F-194](f194-agentjacking-mcp-tool-response-poisoning.md)
