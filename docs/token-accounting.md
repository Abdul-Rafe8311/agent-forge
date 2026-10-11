# Token accounting

One TokenLedger covers every dispatched generation in a run: planning, at most one plan-format repair, execution, repairs, and final integration. The router is the only dispatch authority. Ledger reservation admission is atomic; unused allocations release on commit, known unsent allocations release, and uncertain dispatched calls charge the full input+output allocation with unknown accounting. Finalization happens once.

Output allowance is the minimum of configured cap, verified provider cap when known, remaining session budget after input, and remaining context window after input. Fallback switches at the configured used/limit threshold and keeps the same ledger. It cannot increase budget or lower already incurred usage. Unknown real windows require explicit model_context_limit/fallback_context_limit.

UTF-8 estimation uses one byte as one token plus 16 framing tokens per message. It is conservative heuristic accounting, not an exact tokenizer. Providers may offer their own count operation. Optional retrieved/memory context can be dropped before admission; required task and full accepted code are never silently truncated. Required context overflow stops.

Reported counts include cached input once as a subset; Anthropic cache-read/cache-create input is included in total input, OpenAI cached input is already part of input. Reasoning output is already included in reported output. Totals equal input+output. Aggregate modes: reported only if all usage reported; estimated if any estimated; unknown if any dispatched result uncertain. Missing usage is never zero. accounting_complete indicates available reported generation usage, not proven spend safety.

Detected input/output/reservation overspend retains actual totals and disables subsequent calls, even if usable code was returned. Transport failures are not retried automatically; code-repair retries are bounded and separately accounted.

Strict mode is an admission guarantee under a verified counting/cap contract, not a dollar limit. Only the deterministic fake contract is verified here. Real OpenAI/Anthropic adapters return unsupported before counting or generation; no silent downgrade.

The real adapters expose OpenAI Responses input_tokens.count and Anthropic Messages count_tokens. Those authenticated counting endpoints are not called by offline tests. Counting may have separate limits, provider billing, and uncertain remote outcomes; the ledger covers generation token usage, not currency or separately billed ancillary operations. This release does not authorize a cost claim or provide a universal hard cap. Users must verify current endpoint pricing/semantics and model windows before enabling real calls.

References: [OpenAI SDK](https://github.com/openai/openai-python), [Responses API](https://developers.openai.com/api/reference/), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create). These establish API shapes, not live integration verification.
