from prometheus_client import Counter, Histogram

REQUESTS = Counter("agent_requests_total", "Chat turns", ["role"])
AGENT_LATENCY = Histogram("agent_step_seconds", "Latency per agent step", ["agent"],
                          buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10))
TOOL_CALLS = Counter("agent_tool_calls_total", "MCP tool calls", ["tool", "status"])
TOKENS = Counter("agent_llm_tokens_total", "LLM tokens", ["agent"])
GUARDRAIL = Counter("agent_guardrail_triggers_total", "Guardrail triggers", ["kind"])
FIRST_RESPONSE = Histogram("agent_first_response_seconds", "Time to first agent message",
                           buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10))
