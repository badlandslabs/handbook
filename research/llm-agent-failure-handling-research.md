# LLM Agent Failure Handling Research

test append

## Source 1: LangChain LCEL — Retry & Fallback Primitives

URLs: https://www.teachyou.ai/blog/langchain-error-handling | https://svgoudar.github.io/langchain_tutorial/langchain/lcel/08_retry_and_fallbacks.html
Type: Tutorial / documentation | Date: 2025-2026

LangChain exposes .with_retry() as a first-class method on every Runnable (LLM calls, chains, output parsers):

langchain with_retry example:


Selective retry by exception type:


Do NOT retry on: InvalidAPIKeyError, AuthenticationError, ContentPolicyViolationError.

Fallback chain via .with_fallbacks():


Timeout:


Failure taxonomy:
- Transient/network -> Retry immediately
- Rate limit (HTTP 429) -> Exponential backoff retry
- Timeout -> Hard ceiling via timeout
- Model/provider failure -> .with_fallbacks()
- Semantic error (malformed JSON) -> Re-prompt with corrective context, NOT blind retry
## Source 1: LangChain LCEL
URLs: teachyou.ai/blog/langchain-error-handling
Type: Tutorial | Date: 2025-2026

LangChain with_retry on every Runnable:
llm = ChatOpenAI(model="gpt-4o-mini")
resilient = llm.with_retry(retry_if_exception_type=(RateLimitError, TimeoutError), wait_exponential_jitter=True, stop_after_attempt=4)
Selective retry by exception type:
llm.with_retry(retry_if_exception_type=(RateLimitError, TimeoutError, InternalServerError), wait_exponential_jitter=True, stop_after_attempt=4)
Do NOT retry: InvalidAPIKeyError, AuthenticationError, ContentPolicyViolationError
Fallback .with_fallbacks() for persistent failures:
resilient = llm.with_fallbacks(fallbacks=[ChatOpenAI(model="gpt-4o-mini"), ChatAnthropic(model="claude-3-haiku-20240229")])
Timeout via .with_config(timeout=30_000)
Failure taxonomy:
Transient (connection reset, 5xx) -> Retry immediately
Rate limit (HTTP 429) -> Exponential backoff retry
Timeout -> Hard ceiling via timeout
Model/provider outage -> .with_fallbacks()
Semantic error (malformed JSON) -> Re-prompt with corrective context

---

## Source 2: OpenAI Agents SDK — Exception Hierarchy & Loop Prevention
URLs: openai.github.io/openai-agents-python | izerui.github.io/openai-agents-python/ref/exceptions | github.com/openai/openai-agents-python/issues/526
Type: Official SDK docs + GitHub issues | Date: 2025 (SDK v0.8+)
SDK Exception Hierarchy (all inherit from AgentsException):
MaxTurnsExceeded — agent exceeded max turns (most common agent-specific error)
ModelBehaviorError — model acted unexpectedly
UserError — user input caused failure
InputGuardrailTripwireTriggered — input guardrail blocked execution
OutputGuardrailTripwireTriggered — output guardrail blocked execution
MaxTurnsExceeded wraps RunErrorDetails: input, new_items, raw_responses, last_agent
Turn limits in RunConfig:
result = Runner.run(agent, input="task", run_config=RunConfig(max_turns=10))
Handoff loop detection: Agent A endlessly delegating to Agent B is a documented failure mode. SDK handoff mechanism exposes raw outputs without built-in sanitization, requiring explicit loop guards at orchestration layer.
Guardrails as tripwires (non-retryable):
agent = Agent(name="safe_agent", instructions="...", input_guardrails=[InputGuardrail(...)], output_guardrails=[OutputGuardrail(...)])
Built-in tracing (enabled by default): captures every LLM generation, tool call, handoff, guardrail result. Viewable at platform.openai.com/traces. Disable per-run: RunConfig(tracing_disabled=True).
