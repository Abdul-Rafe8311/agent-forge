# Configuration

All constructor options are explicit; unknown keywords raise. `AgentConfig.validate_settings()` checks local configuration without requests. No automatic .env loading. The distribution is agentforge-coding; Python import and CLI are agentforge. Published-package installation commands become valid only after publication.

| Settings | Defaults and behavior |
| --- | --- |
| model / provider | model required; explicit fake, openai, anthropic, or recognized family inference |
| api_key | explicit primary key before provider environment; lazy resolution, repr hidden |
| provider_instance / fallback_provider_instance / memory_instance / validator | injected interfaces; caller retains resource ownership |
| memory / memory_backend / project_id | false / local / hash of resolved codebase or current directory |
| memory_path / redis_url | platform user-data agentforge/memory / explicit then REDIS_URL |
| task_decompose / max_steps | false / 10, integration included |
| error_loop / max_retries | false / 3 repairs after initial candidate |
| token_budget / fallback_threshold | 50000 per run / 0.8; no budget reset |
| fallback_model / fallback_provider | unset; provider's environment key or injected adapter |
| context_compression / codebase_path | false / unset; readable directory required when enabled |
| context_token_budget / memory_token_budget | 8000 / 4000, conservative whole-record selection |
| max_output_tokens / timeout_seconds | 4096 / 60, each dispatch constrained further |
| strict_budget | false; real adapters reject strict before any request |
| model_context_limit / fallback_context_limit | unknown SDK windows require explicit verified overrides |
| memory_retention_entries / memory_entry_max_bytes | 100 / 262144 (minimum 512) |

Provider SDKs are optional. Install checkout extras with `python -m pip install -e ".[openai,anthropic]"`. Real opt-in examples require privately set provider key, AGENTFORGE_MODEL and AGENTFORGE_CONTEXT_LIMIT. Config passes exact IDs to SDKs; it supplies no catalog of available models or fabricated windows. SDK automatic retries are disabled.

## Upstash

```bash
python -m pip install -e ".[redis]"
# Privately set REDIS_URL to the database's read/write TCP/TLS connection URL.
```

```python
from agentforge import AgentWrapper

agent = AgentWrapper(
    "fake", provider="fake", memory=True, memory_backend="redis", project_id="my-project"
)
# run() would connect to the configured database; not executed during this build.
```

Use the Console's `rediss://username:password@hostname:port` URL. HTTPS REST URLs/tokens, plaintext Redis and URL query overrides are rejected. Explicit redis_url wins over REDIS_URL. TLS certificate and hostname verification remain enabled; connection/read timeouts are 5 seconds. Namespaced hashed project lists append/trim atomically in a transaction. Storage and entries are bounded. Neither URL nor keys enter serialized results or config repr.

Redis SDK retries are explicitly zero and health polling is disabled. RESP2 and
disabled driver metadata avoid HELLO/CLIENT SETINFO setup traffic. For a single
optional live save/reopen/load check with FakeProvider, use the
[Redis smoke guide](redis-memory-smoke.md); all development checks use mocks.

Redis creation is lazy, and only owned clients are closed. Automated verification
uses mocked clients only. The user reported one successful opt-in live
save/reopen/load cycle with seven completed client command frames; Upstash quota
usage was not measured. See the [verification report](verification.md). Do not
repeat that live check during development, review or CI.
