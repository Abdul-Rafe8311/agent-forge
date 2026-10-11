# Python API and serialization

Root exports: `AgentWrapper`, `optimize`, `AgentResult`, `AgentCallResult`, `AgentCallContext`, `Message`, `FakeProvider`, real adapter classes, `__version__`. Other typed contracts live in `agentforge.types`; configuration, ledger, storage, artifact and validator APIs live in their corresponding modules.

## Wrapper

`AgentWrapper(model, *, provider=..., provider_instance=..., ...)` validates configuration without dispatch. Inject a provider or memory backend to retain caller ownership. `run(task)` returns one result; `close()` closes only owned resources. Context-manager exit calls close. Async/concurrent use of one wrapper is unsupported.

`AgentResult.to_dict()` serializes dataclasses recursively; schemas contain no SDK clients/configuration/credentials. Fields: `code`, `artifacts`, `steps`, `steps_taken`, `tokens_used`, `token_usage`, `success`, `status`, `errors`, `warnings`, `models_used`, `session_id`, `project_id`, `accounting_complete`. Each artifact has `path,content,language`. Steps include the plan step, accepted delta, explanation, attempts and status. Attempts retain model, usage, validation and safe error/error_kind. Usage has input/output/cached subset and accounting mode; total is input+output.

Statuses: `success`, `validation_failed`, `budget_exceeded`, `provider_error`, `planning_failed`, `context_limit_exceeded`, `memory_error`. Success is true exactly for success status. Steps count execution steps attempted, including attempted integration, excluding planning/retries. Partial artifacts remain available after a failure. Constructor, credential/optional dependency configuration and invalid task errors raise; expected runtime errors produce failure results.

Model generation must return one bare or fenced JSON object:
```json
{"artifacts":[{"path":"hello.py","language":"python","content":"def hello():\n    return 'Hello'\n"}],"explanation":"Greeting module"}
```
All fields are required, extras/type coercion/duplicates/unsafe paths/empty content are rejected. Structured plans require id,title,instruction,depends_on,kind. Cycles, missing dependencies and malformed integration are rejected.

`result.write_to(path, overwrite=False)` explicitly exports accepted artifacts. Safe paths preflight before mutations; existing files require overwrite. Concurrent hostile filesystem changes and multi-file transactionality are not guaranteed.

## Decorator

```python
from agentforge import optimize, AgentCallResult, AgentCallContext, Message, FakeProvider


@optimize("metadata-only")
def opaque(task, suffix="!"):
    return task + suffix


@optimize(
    "fake",
    provider="fake",
    structured=True,
    provider_instance=FakeProvider(["fixture"]),
    token_budget=1000,
)
def routed(task, *, agentforge_context: AgentCallContext):
    reply = agentforge_context.generate([Message("user", task)])
    return AgentCallResult(reply.text, reply.usage)
```

Opaque mode preserves values, args, signatures and original exceptions. With all options off it is pass-through without intrinsic improvement. The first ordinary argument must be named task; positional/keyword task is supported. Explicit budgets, automatic fallback, decomposition and strict mode are rejected. Memory/context augments only the task. Unsupported object outputs are stored as safe type markers without custom repr.

Structured mode reserves keyword-only agentforge_context; callers cannot inject it. It returns a new AgentCallResult preserving output with ledger usage replacing advisory callback usage. Arbitrary output is not promised JSON serialization. External SDK calls cannot be detected/capped. Both modes reject async callbacks, decomposition and strict mode. Exception retries are opt-in because callbacks can have side effects; structured retries share the invocation ledger.

## CLI

`agentforge --help`, `agentforge run --help`, `python -m agentforge` and `agentforge serve --help` describe explicit flags. JSON run output is one AgentResult on stdout; diagnostics/warnings go to stderr. Exit codes: 0 success, 2 configuration/context, 3 budget, 4 validation/planning, 5 provider/memory or requested file delivery failure, 130 interrupted. Export failure preserves computation status/artifacts and appends a warning. No output-dir means no artifact writes.
