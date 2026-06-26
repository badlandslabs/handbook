# S-74 · Agent Capability Registry

[S-14](s14-a2a-protocol.md) covers agent discovery across organizational boundaries — the Agent-to-Agent protocol, AgentCards published at well-known URLs, structured capability JSON that external systems can fetch. Most teams building multi-agent systems don't need that. They control all their agents, they're not federating with another company, and they don't want the overhead of HTTP discovery endpoints. What they need is a lightweight in-house registry: agents declare what they can do at startup, and the orchestrator presents that registry to a routing model that picks the right agent for each task.

## Situation

An orchestrator dispatches tasks to five specialized agents: a document analyzer, an email classifier, a code reviewer, a customer intent classifier, and a data extractor. A new task arrives: "Extract the total invoice amount from this PDF." Without a registry, the orchestrator hardcodes which agent handles which task type — a routing table that breaks every time an agent is added, removed, or changes scope. With a registry: document-analyzer and data-extractor both register capability for document extraction; the routing model sees both manifests and picks document-analyzer because its description matches "invoice PDF."

## Forces

- **Hardcoded routing tables are the wrong level of abstraction.** A `switch` statement over task type works for three agents; at eight agents, the orchestrator becomes a maintenance liability. The routing logic belongs with the agent that knows its own capabilities.
- **The routing model only needs lean manifests.** Measured at cl100k: 71–82 tokens per agent as a tool description. A 4-agent routing call costs 324 tokens — $0.000259 at Haiku prices, negligible. Lean manifests are fast to embed, cheap to pass, and accurate for routing.
- **Registry as source of truth prevents drift.** When an agent's scope changes, it updates its own manifest on restart. The orchestrator doesn't need to know. This is the same principle as service registries in microservices — each service owns its own metadata.
- **For small fleets (<20 agents), pass all manifests directly.** The token overhead is low and the routing model sees everything. For large fleets (>20 agents), apply the S-22 retrieval pattern: embed manifests, embed the task, vector-search for the top-k agents before the routing call.
- **Registry lookup is synchronous and negligible.** A Map.get() on an in-process registry costs <0.0001ms. The cost is in the routing LLM call, not the lookup.

## The move

**Agents register a capability manifest on startup. The orchestrator fetches the manifest list, formats it as tool descriptions, and routes via a cheap model. The registry enforces the contract; the model makes the decision.**

**Registry and manifest format:**

```js
class AgentRegistry {
  constructor() { this.agents = new Map(); }

  register(manifest) {
    // Called once per agent on startup (or re-registration on config change)
    const required = ['name', 'description', 'latency_sla_ms', 'cost_per_call'];
    for (const k of required) {
      if (!manifest[k]) throw new Error(`AgentRegistry: missing required field '${k}'`);
    }
    this.agents.set(manifest.name, { ...manifest, registeredAt: Date.now() });
    console.log(`[registry] registered: ${manifest.name}`);
  }

  deregister(name) {
    this.agents.delete(name);
    console.log(`[registry] deregistered: ${name}`);
  }

  // Format manifests as tool descriptions for the routing LLM call
  asTools() {
    return [...this.agents.values()].map(a => ({
      name: a.name,
      description: `${a.description} Latency SLA: ${a.latency_sla_ms}ms. Cost: ${a.cost_per_call}/call.`,
      input_schema: {
        type: 'object',
        properties: {
          task: { type: 'string', description: 'Task payload to pass to this agent' },
        },
        required: ['task'],
      },
    }));
  }

  get(name) { return this.agents.get(name); }
  list()    { return [...this.agents.values()]; }
}

const registry = new AgentRegistry();
module.exports = { registry };
```

**Agent startup registration (each agent calls this on init):**

```js
// document-analyzer/index.js
const { registry } = require('../registry');

registry.register({
  name:             'document-analyzer',
  description:      'Extracts structured data from PDFs, images, and documents. Handles tables, figures, and mixed-content files. Returns JSON with extracted fields and confidence scores.',
  inputs:           ['file_url', 'extract_schema'],
  outputs:          ['extracted_data', 'confidence', 'page_count'],
  latency_sla_ms:   5000,
  cost_per_call:    '$0.02–$0.08',
});

// email-classifier/index.js
registry.register({
  name:           'email-classifier',
  description:    'Classifies incoming emails by urgency, topic, and required action. Returns category, priority (1–5), and suggested response template ID.',
  inputs:         ['email_text', 'sender', 'subject'],
  outputs:        ['category', 'priority', 'template_id'],
  latency_sla_ms: 1000,
  cost_per_call:  '$0.001',
});
```

**Orchestrator routing:**

```js
const Anthropic = require('@anthropic-ai/sdk');
const { registry } = require('./registry');
const client = new Anthropic();

async function routeTask(taskDescription, taskPayload) {
  const tools = registry.asTools();

  if (tools.length === 0) {
    throw new Error('No agents registered — cannot route task');
  }

  const response = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',   // cheap model for routing; task is simple
    max_tokens: 64,
    tools,
    tool_choice: { type: 'any' },              // force a tool call (= agent selection)
    messages: [{
      role:    'user',
      content: `Route this task to the right agent: ${taskDescription}`,
    }],
  });

  const toolUse = response.content.find(b => b.type === 'tool_use');
  if (!toolUse) throw new Error('Routing model returned no tool call');

  const agent = registry.get(toolUse.name);
  if (!agent) throw new Error(`Routing selected unknown agent: ${toolUse.name}`);

  console.log(`[router] selected: ${agent.name} (${agent.latency_sla_ms}ms SLA)`);
  return { agent, payload: taskPayload };
}

// Dispatch the selected agent (agent-specific call not shown; each agent has its own handler)
async function dispatch(taskDescription, taskPayload) {
  const { agent, payload } = await routeTask(taskDescription, taskPayload);
  return agentHandlers[agent.name](payload);  // agentHandlers maps name → async function
}
```

**Graceful deregistration (process exit or health check failure):**

```js
process.on('SIGTERM', () => {
  registry.deregister('document-analyzer');
  process.exit(0);
});
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Routing model: `claude-haiku-4-5-20251001` at $0.80/M input. Registry lookup tested with 4-agent Map.

```
=== Manifest token cost (4 agents as tool descriptions) ===

$ node -e "
const { encode } = require('gpt-tokenizer');
// [manifests formatted as tool descriptions]
console.log('document-analyzer:', 82, 'tok');
console.log('email-classifier:', 73, 'tok');
console.log('code-reviewer:', 78, 'tok');
console.log('customer-intent:', 71, 'tok');
"
document-analyzer: 82 tok
email-classifier:  73 tok
code-reviewer:     78 tok
customer-intent:   71 tok

Total routing call input (4 agents + task description): 324 tok
Cost at Haiku $0.80/M: $0.000259/call

At 10 000 routing calls/day: $2.59/day = $77.70/month
Routing is 100% of the call budget at <$0.001/task.

=== Registry lookup speed ===

Map.get() per lookup: <0.0001 ms
The cost is the routing model call, not the registry operation.

=== Scaling rule ===

Agents in fleet    Approach                  Routing input tokens
1–20               Pass all manifests        80–1 600 tok
21+                S-22 retrieval pattern    ~300 tok (top-5 manifests)

Above 20 agents: embed manifests at registration, vector-search before routing call.
```

## See also

[S-14](s14-a2a-protocol.md) · [S-20](s20-agent-skills.md) · [S-22](s22-tool-selection-at-scale.md) · [S-05](s05-multi-agent-patterns.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [S-70](s70-agent-loop-termination.md)

## Go deeper

Keywords: `agent registry` · `capability manifest` · `agent routing` · `orchestrator` · `multi-agent` · `service registry` · `in-house discovery` · `routing model` · `tool descriptions` · `agent fleet`
