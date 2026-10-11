# AgentForge — complete implementation prompt for Codex

Distribution metadata was amended to `agentforge-coding` at the owner's request; the Python import and CLI remain `agentforge`.

Copy this entire document into an AI coding agent operating in the AgentForge repository. The attached README is the product brief; the explicit contracts below resolve its missing details and contradictions.

---

You are a senior Python framework engineer. Build the complete working AgentForge Python package described here. Implement actual source files, meaningful tests, examples, documentation, and installable distribution artifacts. Do not stop at a plan or provide pseudocode. Inspect existing repository instructions first and preserve unrelated work. Run the checks, correct failures, and report any checks blocked by the environment honestly.

## 1. Product scope and decisions

AgentForge is a lightweight orchestration layer for AI coding workflows. It provides persistent project memory, sequential task decomposition, validation and repair, model routing, token accounting, and relevant codebase context selection. It exposes an `AgentWrapper`, an `optimize` decorator, and an `agentforge` CLI.

Implement a synchronous Python 3.11+ first release. Support OpenAI and Anthropic through their official Python SDKs, plus an offline fake provider for testing and demos. Make Redis an optional memory backend. Gemini, a VS Code extension, a web dashboard, and shared team memory remain explicitly unimplemented roadmap items. Do not advertise them as supported.

Treat README model names such as `claude-opus-5.5`, `gpt-6`, and `claude-haiku` as user-provided identifiers, not proof of availability or valid aliases. Pass model IDs through unchanged. Use an explicit `provider="anthropic"` or `provider="openai"` when needed; infer only recognized `claude-*`, `gpt-*`, and documented OpenAI reasoning-model prefixes. Reject ambiguous model IDs with a useful configuration error. Verify official SDK documentation while implementing; do not invent model aliases, pricing, context limits, or SDK parameters. Record tested SDK versions. Examples must let users specify an account-accessible model using environment variables.

Resolve these README ambiguities:

- A run is a token session: its ledger resets for every `run`, while project memory survives runs and process restarts. Reuse one ledger across planning, execution, repair, and final integration within that run.
- A fallback changes the selected model before the budget is exhausted when a configured threshold is crossed. It never creates more tokens or resets the ledger. Exhaustion stops the run.
- Decomposition produces a dependency-aware sequential plan. No concurrent agents in this release.
- Default validation means parsing generated Python source and checking response structure. Executing generated code requires an explicit opt-in validator. Do not call syntax-only validation proof of runtime correctness.
- A wrapper generates code artifacts and returns them. It does not silently modify a user's codebase. Writing returned artifacts is an explicit helper/CLI action.
- Arbitrary decorated functions may perform opaque model calls. AgentForge cannot truthfully enforce budgets or switch models for calls it does not control. The decorator must state this limitation and offer a structured callback contract described below.
- Do not claim proven model-quality improvement, exact spend reduction, or universal strict token caps. Implement measurable behavior and document its limits.

## Upstash Redis connection requirement

The user's chosen hosted memory service is Upstash Redis. Implement it through the existing `memory_backend="redis"` backend using the official `redis` Python client over TLS/TCP. No additional REST backend is needed for this first release.

- Resolve connection URL from explicit `redis_url` first, then the `REDIS_URL` environment variable. Validate after resolution, and only require it when Redis memory is enabled.
- Use the database's read/write TCP connection string from Upstash Console, with scheme `rediss://`, its supplied username/password, hostname, and port. Keep TLS certificate verification enabled. Do not disable TLS or silently downgrade to plaintext.
- An Upstash REST URL (`https://...`) and REST token are a different connection interface. Do not pass them to `redis.Redis.from_url`; fail with an actionable configuration error explaining that this backend expects the TCP/TLS URL.
- Keep credentials in environment variables or a user-managed secret store. Never hard-code them, print the URL, commit `.env`, or include it in result/memory objects. Redact connection credentials from diagnostics and config repr.
- Document local setup: install `.[redis]`, set `REDIS_URL` privately, and construct `AgentWrapper(model=..., memory=True, memory_backend="redis", project_id="my-project")`. Other model settings and limits still apply.
- Configure connect/read timeouts, lazy connection establishment, client cleanup, namespaced project keys, atomic append-plus-retention, and bounded entry sizes. Preserve the shared memory protocol and error policies.
- Verify Redis behavior with a mocked client only during this build. Document optional user-run connection verification separately; do not connect to the real Upstash database or consume commands during development/testing.

## No paid or authenticated remote tests during this build

Implement real provider integrations, but perform all generation and Redis tests with FakeProvider or mocked clients. Do not read/use API keys already in the environment, make live generation/token-counting requests, or connect to hosted Redis during verification. Public documentation lookup and dependency installation are permitted. Live integration verification is blocked by the user's current cost constraint; do not ask for credentials or treat this as a reason to leave offline implementation unfinished. Explicitly report that real OpenAI, Anthropic, and Upstash connectivity were not exercised. Do not publish or buy services. These constraints override optional live-smoke-test instructions elsewhere in this document.

## 2. Exact repository structure

Use this tree. The root package layout deliberately follows the README. Additional files require a concrete implementation reason, which you should summarize.

```text
agentforge/
├── agentforge/
│   ├── __init__.py
│   ├── __main__.py
│   ├── py.typed
│   ├── config.py
│   ├── types.py
│   ├── exceptions.py
│   ├── core.py
│   ├── decorators.py
│   ├── memory.py
│   ├── decomposer.py
│   ├── validator.py
│   ├── compressor.py
│   ├── router.py
│   ├── artifacts.py
│   ├── prompts.py
│   ├── utils.py
│   ├── cli.py
│   ├── server.py
│   ├── server_schemas.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       ├── anthropic.py
│       ├── openai.py
│       └── fake.py
├── examples/
│   ├── basic.py
│   ├── with_claude.py
│   ├── with_openai.py
│   ├── multi_step_project.py
│   ├── error_loop_demo.py
│   ├── decorator_demo.py
│   └── javascript_client.mjs
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── configuration.md
│   ├── token-accounting.md
│   ├── security.md
│   ├── publishing.md
│   └── server.md
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_core.py
│   ├── test_decorators.py
│   ├── test_memory.py
│   ├── test_decomposer.py
│   ├── test_validator.py
│   ├── test_compressor.py
│   ├── test_router.py
│   ├── test_artifacts.py
│   ├── test_cli.py
│   ├── test_packaging.py
│   ├── test_server.py
│   └── providers/
│       ├── test_anthropic.py
│       └── test_openai.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── .env.example
├── LICENSE
├── README.md
└── pyproject.toml
```

## 3. Shared data contracts — `types.py`

Use typed dataclasses for runtime objects and Pydantic v2 for untrusted structured model output/configuration as appropriate. Public serialized objects must have documented JSON representations. Never store SDK objects or credentials in them.

Define:

- `Message(role: Literal["system", "user", "assistant"], content: str)`.
- `TokenUsage(input_tokens: int, output_tokens: int, cached_input_tokens: int = 0, accounting: Literal["reported", "estimated", "unknown"] = "reported")`. Counts are nonnegative. `total_tokens` is input plus output; cached input is a subset, never added twice. Map provider cache fields carefully. Internal reasoning output counts are included in provider-reported output, not added twice.
- `ProviderRequest(model: str, messages: list[Message], max_output_tokens: int, timeout_seconds: float)`. Enforce positive output cap and nonempty messages. Only include provider-supported sampling parameters if separately configured; do not force temperature on all models.
- `ProviderResponse(text: str, usage: TokenUsage, model: str, finish_reason: str | None, request_id: str | None)`. Reject truncated code/JSON rather than marking it successful.
- `CodeArtifact(path: str, content: str, language: str = "python")`. Path is relative to an output root; enforce path safety when parsing and writing.
- `Step(id: str, title: str, instruction: str, depends_on: list[str], kind: Literal["execute", "integrate"] = "execute")` and `TaskPlan(steps: list[Step])`.
- `ValidationIssue(kind: str, message: str, path: str | None, line: int | None)` and `ValidationResult(passed: bool, issues: list[ValidationIssue], diagnostics: str = "")`.
- `AttemptRecord(step_id: str, attempt: int, model: str, usage: TokenUsage, validation: ValidationResult | None, error: str | None)`.
- `StepResult(step: Step, artifacts: list[CodeArtifact], explanation: str, attempts: list[AttemptRecord], status: Literal["success", "failed", "budget_exceeded"])`.
- `AgentResult(code: str, artifacts: list[CodeArtifact], steps: list[StepResult], steps_taken: int, tokens_used: int, token_usage: TokenUsage, success: bool, status: Literal["success", "validation_failed", "budget_exceeded", "provider_error", "planning_failed", "context_limit_exceeded", "memory_error"], errors: list[str], warnings: list[str], models_used: list[str], session_id: str, project_id: str, accounting_complete: bool)`.
- `MemoryEntry(id: str, project_id: str, session_id: str, created_at: str, task: str, summary: str, artifacts: list[CodeArtifact], success: bool)`.
- `ContextChunk(path: str, start_line: int, end_line: int, content: str, score: float)` and `ContextBundle(text: str, chunks: list[ContextChunk], estimated_tokens: int, skipped_files: list[str])`.
- `AgentCallResult(output: Any, usage: TokenUsage | None = None, accounting_complete: bool = False)` for decorated agents. In structured mode the wrapper sets `usage` to the invocation ledger total and `accounting_complete` to the completeness of routed calls; preserve `output`, not callback-supplied usage metadata.

`AgentResult.code` equals the single artifact content for a one-file result; for multiple files it is a deterministic concatenation with filename comments. `artifacts` remains the authoritative output. `steps_taken` counts distinct execution steps attempted, not planning calls or retries; a final integration step counts if attempted. `tokens_used` equals `token_usage.total_tokens` and covers every accounted provider call, including conservative charges when actual usage is unknown. Aggregate accounting is `reported` only if all usage is reported, `estimated` if any estimate is used, and `unknown` if any remote outcome is unknown. `accounting_complete` means reported usage was available for every dispatched generation; it does not prove overall budget safety. Preserve partial results when stopping. `success` is true exactly when `status == "success"`; `errors` describes failures and `warnings` describes nonfatal operational problems.

Implement `AgentResult.to_dict() -> dict[str, Any]` with recursive JSON-safe serialization and a stable public schema. Encode datetimes as UTC ISO-8601 strings, paths as strings, and omit credentials. Arbitrary decorator `output` is not promised JSON serialization. Use strict Pydantic parsing at model-output boundaries: forbid extra fields and unwanted type coercion, enforce size/count limits, and do not substitute defaults for malformed required fields.

## 4. File responsibilities and function contracts

All public methods need docstrings describing inputs, outputs, side effects, and errors. Keep private helpers typed and small. Use these interfaces or compatible typed equivalents; document any unavoidable change.

### `config.py`

`AgentConfig` stores validated options:

```python
model: str
provider: str | None = None
api_key: str | None = None
memory: bool = False
memory_backend: Literal["local", "redis"] = "local"
project_id: str | None = None
memory_path: Path | None = None
redis_url: str | None = None
task_decompose: bool = False
max_steps: int = 10
error_loop: bool = False
max_retries: int = 3
token_budget: int = 50_000
fallback_model: str | None = None
fallback_provider: str | None = None
fallback_threshold: float = 0.8
context_compression: bool = False
codebase_path: Path | None = None
context_token_budget: int = 8_000
max_output_tokens: int = 4_096
memory_token_budget: int = 4_000
timeout_seconds: float = 60.0
strict_budget: bool = False
model_context_limit: int | None = None
fallback_context_limit: int | None = None
memory_retention_entries: int = 100
memory_entry_max_bytes: int = 262_144
```

- `AgentConfig.validate_settings() -> None`: validate nonblank IDs, positive limits, `max_retries >= 0`, `max_steps >= 1`, threshold in `(0, 1)`, Redis URL when Redis memory enabled, and readable directory when code context enabled. Invalid input raises `ConfigurationError`.
- `derive_project_id(codebase_path: Path | None, cwd: Path) -> str`: deterministic hash of the resolved project root; an explicit ID overrides it. Never use one universal default project key.
- API-key precedence: explicit primary key, then provider-specific environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Fallback uses its provider environment key or a separately injected provider instance, never blindly reuses another provider's key. Validate credentials lazily so offline fakes and decorated agents do not require them. Mask keys in repr/logs. Do not auto-load `.env` in library import.

### `exceptions.py`

Implement `AgentForgeError`, `ConfigurationError`, `ProviderError`, `UnsupportedProviderError`, `BudgetExceededError`, `ValidationFailedError`, `MemoryBackendError`, `ArtifactPathError`, `PlanningFailedError`, `ContextLimitExceededError`, and `RunStateError`. Provider errors retain safe request IDs and chained original exceptions, without leaking credentials or full prompts. `BudgetExceededError` includes remaining/reserved token information. Expected execution failures become `AgentResult` failures; constructor/configuration/path failures raise.

### `providers/base.py`

Define `ProviderCapabilities` in `types.py` with `context_window_tokens: int | None` and `max_output_tokens: int | None`. Unknown values are explicitly `None`; do not fabricate limits. Define a `ModelProvider` protocol:

- `generate(request: ProviderRequest) -> ProviderResponse`: one nonstreaming model request; no invisible SDK retry loops.
- `count_input_tokens(request: ProviderRequest) -> int | None`: provider-supported input count if available, including actual message formatting; otherwise `None`.
- `supports_strict_budget(request: ProviderRequest) -> bool`: true only when counting and output cap semantics are verified sufficient for the documented strict contract.
- `capabilities(model: str) -> ProviderCapabilities`: return verified limits or unknown values.
- `close() -> None`: release SDK/client resources. Injected caller-owned providers must not be closed automatically unless ownership was transferred explicitly.

Disable SDK automatic retries for generation. Transport failures and code repair are different; do not automatically rerun a timeout with unknown incurred usage. If you add transport retries, each actual attempt must participate in ledger accounting and must be explicitly bounded. Default to none.

### `providers/anthropic.py` and `providers/openai.py`

`AnthropicProvider(api_key: str | None, client: Any | None = None)` and `OpenAIProvider(...)` implement the protocol with lazy SDK imports. An injected mocked client needs no real key.

Anthropic: separate system content from user/assistant messages, invoke Messages API, join supported text blocks, and normalize input/output/cache usage according to official definitions. Handle refusals/nontext responses and truncation.

OpenAI: use one documented nonstreaming text-generation API consistently, preferably Responses if the chosen SDK/model supports it. Normalize messages, text, output caps, usage, and failure states. If using Chat Completions, use documented completion-token cap semantics for the selected models; do not mix Responses and Chat field names. Document the supported endpoint/model envelope. Unsupported provider features must fail clearly.

When SDK/extras are missing, raise an error containing the exact installation extra. Network/API authentication errors should not be turned into fake successful responses.

### `providers/fake.py`

`FakeProvider(responses: Sequence[ProviderResponse | Exception])` returns queued responses or raises queued errors. Record requests, expose deterministic counting/cap support for budget tests, and error on exhaustion. Supply fake fixtures for planning, malformed JSON, invalid code, repair, and successful final integration. Only select this provider explicitly; never silently fall back to it in real runs. Add `make_demo_provider(task_decompose: bool, max_steps: int) -> FakeProvider` to construct the deterministic script needed by the CLI. It returns valid demo artifacts rather than pretending to fulfill arbitrary user tasks, and emits a clearly labeled offline-demo warning. Its token reports must conform to its deterministic counting and requested output caps.

### `router.py`

Implement a per-run `TokenLedger` and `ModelRouter`:

- `TokenLedger(limit: int)`; `remaining -> int`, `used -> int`, and `accounting_complete -> bool`.
- `reserve(input_allowance: int, output_allowance: int) -> str`: atomically reserve a call allocation; raise before a call if allocation exceeds remaining unreserved budget.
- `commit(reservation_id: str, usage: TokenUsage) -> None`: reconcile reported usage, release unused reserved allocation, and update totals exactly once. If actual exceeds reservation, record actual usage, mark the violation, and stop future calls; never hide overspend.
- `release(reservation_id: str) -> None`: only for a request known not to have been sent.
- `charge_unknown(reservation_id: str) -> None`: finalize an uncertain dispatched call by charging both reserved input and output allowances with `accounting="unknown"`, freeing the reservation and marking accounting incomplete; do not leave an unresolved reservation out of result totals. Tests must distinguish known preflight failures from uncertain remote failures.
- `ModelRouter(config: AgentConfig, primary: ModelProvider, fallback: ModelProvider | None)`.
- `select_model(ledger: TokenLedger) -> tuple[ModelProvider, str]`: use primary below threshold and configured fallback after threshold; stop if no affordable call can be admitted.
- `generate(messages: list[Message], ledger: TokenLedger, purpose: str) -> ProviderResponse`: select model, assemble request, measure/estimate input, clamp output allocation to remaining budget, reserve, call provider, then reconcile.

Budget rules: count all planning, execution, repair, and integration calls. Core never directly calls SDKs. Exact guarantees depend on provider counting, hidden overhead, cap semantics, and uncertain failures. `strict_budget=True` must reject unsupported provider/model counting before generation; it must not silently downgrade to estimates. For the default estimated mode, use a documented conservative UTF-8-based estimator plus framing allowance, report accounting mode, and make no absolute hard-cap promise. Missing usage is not zero: charge reservation and mark incomplete. Counting endpoints have their own cost/limits; document them and account for billed operations if applicable. Check each model's input context separately from session budget. Resolve its context/output limits from explicit config overrides or verified provider capabilities. If the context limit is unknown and no override exists, raise `ConfigurationError` before generation with the required option; a model-name guess is insufficient. Clamp output cap to the configured cap, supported provider cap, remaining session allowance, and remaining context-window allowance; require at least one output token. Validate limits separately when selecting fallback. Check unsupported strict accounting before invoking any potentially billed counting/generation operation. Strict mode is a request-admission guarantee under documented verified provider assumptions, not a dollar-spend cap or a claim about opaque remote operations. On any detected bound violation record actual totals, stop, and return `budget_exceeded`; never report success merely because the provider returned usable code. Stop on truncation with a failure or bounded repair if budget allows.

### `memory.py`

Define `MemoryBackend` protocol:

- `load(project_id: str, limit: int = 20) -> list[MemoryEntry]`: newest bounded entries, deterministic ordering.
- `append(entry: MemoryEntry) -> None`: persist one entry.
- `clear(project_id: str) -> None`: remove only that project.
- `close() -> None`.

`LocalMemoryBackend(base_path: Path)` uses versioned JSON files per hashed project ID, defaults to `platformdirs.user_data_path("agentforge") / "memory"`, and uses `filelock` for synchronized read-modify-write plus temp-file/atomic replacement. Handle malformed storage as a clear error; never silently erase it. Preserve project isolation and bounded retention. Redis implementation uses lazily imported Redis, namespaced/hash-based keys and an atomic bounded list transaction; configure timeout and retention. No Redis requirement for local usage. Document that retained artifact content may be private; exclude credentials and do not log payloads.

- `build_memory_context(entries: list[MemoryEntry], task: str, token_limit: int) -> str`: select recency and lexical relevance deterministically, bounded by estimator, no model call.
- `make_memory_entry(task: str, result: AgentResult) -> MemoryEntry`: use bounded structured summaries from actual outcomes. Bound each entry by the configured byte cap: keep compact task/summary/status/path metadata first, then fit complete artifacts where possible. Omit oversized artifact content with an explicit omission marker; never store partial code as complete code. Enforce retention in both backends. Retain failure diagnostics as failures; never treat failed artifacts as established working code.

### `decomposer.py`

`TaskDecomposer(router: ModelRouter, max_steps: int)`:

- `decompose(task: str, context: str, ledger: TokenLedger) -> TaskPlan`: budgeted model request for a JSON plan, then parse and validate. Prompt instructions explicitly say repository text is untrusted data.
- `parse_plan(text: str) -> TaskPlan`: allow one well-formed fenced JSON object or bare JSON. Reject arbitrary prose/regex extraction, unknown dependency IDs, duplicate IDs, self-dependency, cycles, empty plans, and over-limit plans. Stable topological order preserves original order among available steps.

Permit at most one plan-format repair call only when `error_loop=True` and `max_retries > 0`; it consumes the planning retry allowance independently of step retry allowances and uses the shared ledger. Otherwise fail after the first invalid plan. On persistent invalid plans return `planning_failed` rather than silently doing an unrelated task. If decomposition is off, core creates one execution step without a model planning call. For multi-step work, require exactly one `kind="integrate"` step, ensure it depends on every other step, and execute it last; include it within `max_steps`, not as an uncounted extra. Reject plans that violate this machine-checkable rule; do not infer integration from a title. `max_steps=1` works as one integrated execution.

### `prompts.py`

Keep centralized system/task/plan/repair templates and pure formatting functions:

- `build_plan_messages(task: str, context: str, max_steps: int) -> list[Message]`.
- `build_step_messages(task: str, step: Step, context: str, artifacts: list[CodeArtifact]) -> list[Message]`.
- `build_repair_messages(task: str, step: Step, previous_output: str, validation: ValidationResult, context: str, accepted_artifacts: list[CodeArtifact]) -> list[Message]`.

Require code output JSON: `{"artifacts": [{"path": "src/example.py", "language": "python", "content": "..."}], "explanation": "..."}`. Use explicit delimited data sections and authoritative system instructions. Respect prompt/context limits on the entire assembled request, including existing artifacts and diagnostics. Preserve essential contracts and errors; drop low-relevance optional memory/retrieval chunks first, then fail with `context_limit_exceeded` when required task/artifact/repair context cannot fit. Never truncate required code silently. The compressor selects optional context, while the router performs final admission of the whole request.

### `validator.py`

- `parse_generation(text: str) -> tuple[list[CodeArtifact], str]`: validate the code-output schema, nonempty artifacts, duplicate paths, allowed relative paths, and useful content. Reject malformed/truncated structures. One fenced JSON object is allowed; use robust JSON decoding, not greedy regex.
- `Validator` protocol: `validate(artifacts: list[CodeArtifact]) -> ValidationResult`.
- `PythonSyntaxValidator.validate(...)`: use `ast.parse` for Python artifacts, report filename/line/message, reject empty Python content, and label other languages as structure-only validation. No generated code execution.
- `CommandValidator(command: Sequence[str], timeout_seconds: float)` is explicit opt-in. Stage artifacts in a fresh temporary directory, use argument-array subprocess with `shell=False`, controlled environment and working directory, enforce timeout, bound stdout/stderr, and return nonzero exit/timeout as validation issues. Clearly document that a subprocess is not a security sandbox and generated tests/code can perform filesystem/network actions. It must not run automatically in default library/CLI flows.
- `RepairLoop.execute(task: str, step: Step, context: str, accepted_artifacts: list[CodeArtifact], router: ModelRouter, ledger: TokenLedger, validator: Validator, max_retries: int) -> StepResult`: initial attempt plus at most `max_retries` repairs, all charged to the same ledger. Errors contain prior output and actionable bounded diagnostics. Zero retries means exactly one attempt. If error loop is disabled, validate once and stop on failure.

The repair loop builds messages using `prompts.py`, parses each response, merges candidate artifacts against the supplied immutable accepted snapshot, and validates the combined candidate. Retry both parse/schema failures and validator failures; provider/auth errors stop immediately. Convert invalid model-supplied paths into validation issues rather than crashing the entire run. `StepResult.artifacts` contains only the accepted incoming changes on success and is empty on failure; rejected candidate output remains in bounded repair diagnostics. Core commits this already-validated delta once, without a second validator invocation or another retry budget. Budget stops remain `budget_exceeded`; provider failures are classified through the recorded error and propagated safe failure metadata. Do not create a second competing retry implementation in core. Preserve every attempt and last diagnostics.

Combined Python syntax validation cannot detect broken imports, interfaces, or behavioral regressions. Cross-file regression tests must inject an explicit validator that checks those contracts, or opt in to the command validator; do not expect `ast.parse` to find semantic bugs. Document this distinction.

### `compressor.py`

`ContextCompressor(codebase_path: Path)`:

- `scan_files() -> list[Path]`: deterministic recursive selection respecting `.gitignore` through `pathspec` plus explicit exclusion of `.git`, virtualenvs, `node_modules`, build/dist directories, caches, binaries, `.env*`, private keys, known credential files, and memory storage.
- `extract_chunks(path: Path) -> list[ContextChunk]`: bounded UTF-8 reads, reject binary or oversized files, keep line numbers, use Python AST boundaries where useful and line windows otherwise.
- `score_chunks(task: str, chunks: list[ContextChunk]) -> list[ContextChunk]`: deterministic lexical scoring of task terms against paths, symbols, and content; stable tie-breaking; no embedding/API dependency.
- `compress(task: str, token_limit: int) -> ContextBundle`: rank and pack whole bounded chunks under the estimator limit with filename/line markers; report skipped files. Keep references useful and avoid duplicate overlap.

Reject symlink traversal outside the configured root and bound depth/file count/read size. Context selection is retrieval/extraction, not semantic proof or magic lossless compression. No model-based summarization in this release; any future summarizer must use the router/ledger.

### `artifacts.py`

- `validate_artifact_path(path: str) -> str`: normalize safe relative paths; reject empty paths, absolute paths, drive prefixes, `..`, UNC paths, control characters, and unsafe cross-platform separators.
- `merge_artifacts(existing: list[CodeArtifact], incoming: list[CodeArtifact]) -> list[CodeArtifact]`: incoming replaces only its same path; preserve untouched files and deterministic order. Pass accumulated state to subsequent steps. Validate the combined set after merge, so individually valid steps cannot silently break prior artifacts.
- `render_code(artifacts: list[CodeArtifact]) -> str`: deterministic readable representation as specified above.
- `write_artifacts(artifacts: list[CodeArtifact], output_dir: Path, overwrite: bool = False) -> list[Path]`: explicitly write within resolved output root, reject symlink escape, preflight all paths/conflicts before mutations, use atomic file replacement, and leave existing files untouched without overwrite authorization. Document the limits of multi-file transactionality.

### `utils.py`

- `estimate_tokens(text: str) -> int`: deterministic documented estimate; never label it exact.
- `redact_sensitive_text(text: str) -> str`: redact recognized key patterns from diagnostics/logging, without claiming complete secret detection.
- `stable_project_key(project_id: str) -> str`: safe filesystem/Redis hash.
- `parse_json_object(text: str) -> dict[str, Any]`: bounded bare or single fenced JSON parsing shared by generation/planning.

### `core.py`

Expose:

```python
class AgentWrapper:
    def __init__(
        self,
        model: str,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        memory: bool = False,
        memory_backend: str = "local",
        project_id: str | None = None,
        task_decompose: bool = False,
        max_steps: int = 10,
        error_loop: bool = False,
        max_retries: int = 3,
        token_budget: int = 50_000,
        fallback_model: str | None = None,
        context_compression: bool = False,
        codebase_path: str | Path | None = None,
        provider_instance: ModelProvider | None = None,
        fallback_provider_instance: ModelProvider | None = None,
        memory_instance: MemoryBackend | None = None,
        validator: Validator | None = None,
        memory_path: str | Path | None = None,
        redis_url: str | None = None,
        fallback_provider: str | None = None,
        fallback_threshold: float = 0.8,
        context_token_budget: int = 8_000,
        memory_token_budget: int = 4_000,
        max_output_tokens: int = 4_096,
        timeout_seconds: float = 60.0,
        strict_budget: bool = False,
        model_context_limit: int | None = None,
        fallback_context_limit: int | None = None,
        memory_retention_entries: int = 100,
        memory_entry_max_bytes: int = 262_144,
    ): ...

    def run(self, task: str) -> AgentResult: ...
    def close(self) -> None: ...
    def __enter__(self) -> "AgentWrapper": ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
```

Use the explicit parameters above; do not accept unexplained `**kwargs`. Reject unknown options. Keep injected providers/backends testable. Declare wrapper instances synchronous and non-reentrant; guard overlapping `run` calls with a clear error. Separate wrapper-scoped configuration from run-scoped ledger/artifacts.

`run` order:

1. Validate task, generate session ID, initialize empty result state and fresh ledger.
2. Load selected project memory if enabled; select bounded memory context.
3. Retrieve bounded relevant codebase context if enabled.
4. Build one step or call decomposer through the router.
5. Execute each step in dependency order using the repair loop. Later steps receive current merged artifacts, task, memory, and relevant code context.
6. Commit only the accepted delta returned by the repair loop. Combined-state validation and repairs occur inside that loop; core does not rerun them. On a failed step keep the previous accepted artifact snapshot.
7. Stop on unrepaired failure or exhausted budget; preserve diagnostics and last accepted artifacts.
8. Populate all result fields. No extra unbudgeted synthesis call. Final integration belongs to the plan.
9. Persist a bounded memory entry if enabled, including honest failure status. A memory read error stops before generation and returns `memory_error`. A memory write error after execution leaves the computation's status/artifacts intact and appends a warning. The CLI exits according to computation status and prints that warning. Do not turn an otherwise successful generation into a misleading total failure or silently ignore lost persistence.

Map expected planning/parse exhaustion to `planning_failed`, required-context overflow to `context_limit_exceeded`, unrepaired output validation to `validation_failed`, and runtime provider errors to `provider_error`. A provider configuration problem remains a configuration exception. Structured errors must be classified explicitly, not by string matching. Add an optional safe error-kind field to `StepResult`/`AttemptRecord` if needed to convey this classification.

### `decorators.py`

Provide two explicit modes, preserving `functools.wraps` and original exceptions:

```python
@optimize(model="claude-opus-5.5")
def my_agent(task: str):
    return existing_agent.run(task)
```

Define the decorator factory with an explicit typed option set: `optimize(model: str, *, structured: bool = False, provider: str | None = None, provider_instance: ModelProvider | None = None, fallback_provider_instance: ModelProvider | None = None, memory: bool = False, memory_backend: str = "local", project_id: str | None = None, memory_path: str | Path | None = None, redis_url: str | None = None, context_compression: bool = False, codebase_path: str | Path | None = None, token_budget: int | None = None, fallback_model: str | None = None, fallback_provider: str | None = None, error_loop: bool = False, max_retries: int = 3, task_decompose: bool = False, strict_budget: bool = False, model_context_limit: int | None = None, fallback_context_limit: int | None = None) -> Callable`. Use 50,000 internally for structured mode when `token_budget` is omitted; in opaque mode omission means no token enforcement. Explicit unsupported options must fail before calling the callback. Reject `task_decompose=True` and `strict_budget=True` in both decorator modes for v0.1. Structured mode enforces admission only for routed calls, since arbitrary Python callbacks cannot be proven to make no external requests.

In opaque mode do not instantiate the full provider-required `AgentConfig`; validate only the supported decorator/memory/context options, so pass-through needs neither credentials nor model limits. Opaque mode accepts a synchronous callable whose first ordinary argument is named `task` and is a string, with extra args/kwargs forwarded unchanged. Use `inspect.signature(...).bind` to support positional or keyword task and validate input. It changes only the bound task value; other argument values are preserved. It passes a bounded augmented task containing original instruction plus optional project memory/context. Return the original function's value unchanged. Optional exception repair may retry only the configured bounded number of times, and only when explicitly enabled because the original function can have side effects. Configuration/model metadata alone does not intercept SDK calls. Reject features requiring controlled calls (any explicit `token_budget`, strict budgeting, automatic model fallback, decomposition) with a clear configuration error in this mode. Do not fabricate `tokens_used`.

Structured mode:

```python
@optimize(model="...", structured=True, token_budget=50_000)
def my_agent(task: str, *, agentforge_context: AgentCallContext) -> AgentCallResult:
    response = agentforge_context.generate([Message(role="user", content=task)])
    return AgentCallResult(output=response.text, usage=response.usage)
```

Define `AgentCallContext` in `decorators.py` with `generate(messages: list[Message]) -> ProviderResponse`, using one framework router/ledger for that invocation. Require a structured callback to return `AgentCallResult`; a different return type raises `ConfigurationError` without refunding incurred routed usage. Structured mode returns a new `AgentCallResult` preserving the callback's `output` and setting `usage`/`accounting_complete` from the shared invocation ledger; it does not mutate a result reused by the callback. Returned usage for already routed calls is metadata and must not be double-counted. External calls made by the callback cannot be detected reliably, intercepted, or hard-capped by this decorator. Document that `usage` covers routed calls only, and never claim it includes all callback costs. A callback-supplied `usage` is advisory metadata, not proof that external calls were absent. No decomposition of arbitrary callbacks in v0.1; that belongs to `AgentWrapper`.

Opaque memory mode stores bounded task/result summaries using safe handling of arbitrary output; avoid executing custom `repr` methods and store a type marker for unsupported objects. Memory load errors raise `MemoryBackendError` before callback execution; post-callback memory write errors emit a sanitized logging warning and preserve the original result. With all features disabled, document that opaque mode is pass-through and offers no intrinsic model improvement. Structured mode binds and injects `agentforge_context` as a reserved keyword-only parameter; reject callback signatures that omit it and callers that attempt to supply it. If explicit exception retries are enabled, reuse the invocation ledger across callback attempts; never reset it. Do not inspect arbitrary return values as Python artifacts or invoke the wrapper's code parser on opaque results.

The decorator factory validates supported options by mode. Reject async callables with a clear error for this synchronous release. Test signature preservation and passing through arguments, return values, and exceptions.

### `cli.py`, `__main__.py`, `__init__.py`

Use Typer. `app = typer.Typer()` and `main() -> None` invoke the app. `__main__.py` calls `main()` so `python -m agentforge` works.

Required CLI:

```bash
agentforge --help
agentforge --version
agentforge run --model "$AGENTFORGE_MODEL" --task "build auth system" --memory --decompose
agentforge run --provider openai --model "$AGENTFORGE_MODEL" --task "create a Python API" --error-loop --token-budget 50000 --model-context-limit "$AGENTFORGE_CONTEXT_LIMIT" --json
agentforge run --provider fake --model fake --task "demo" --output-dir ./generated
```

Support `--model-context-limit`, `--fallback-context-limit`, and `--max-output-tokens` as well as `--provider`, `--model`, `--task`, `--task-file` (mutually exclusive), `--memory/--no-memory`, `--memory-backend`, `--memory-path`, `--redis-url`, `--project-id`, `--decompose/--no-decompose`, `--max-steps`, `--error-loop/--no-error-loop`, `--max-retries`, `--token-budget`, `--fallback-model`, `--fallback-provider`, `--fallback-threshold`, `--strict-budget`, `--compress-context/--no-compress-context`, `--codebase-path`, `--json`, `--output-dir`, and `--overwrite`. Read credentials from environment; avoid API keys in command arguments/process listings. `--output-dir` writes only successful accepted artifacts; no output flag means no generated-file writes.

Plain output includes code plus concise status/usage to stderr. JSON mode emits exactly one serializable `AgentResult` to stdout; all diagnostics go to stderr. Never display keys or raw provider exception payloads. Exit codes: 0 success, 2 configuration/CLI input error or context-limit failure, 3 budget stop, 4 validation/planning failure, 5 provider/backend operational failure. If explicit artifact writing fails, exit 5, append a safe output-write warning to the existing `AgentResult`, and report it on stderr. Preserve computation status/artifacts and emit the same single-result JSON schema; document that the nonzero exit reflects failed requested file delivery. Handle Ctrl-C cleanly without traceback and with conventional exit 130.

Export `AgentWrapper`, `optimize`, `AgentResult`, `AgentCallResult`, `AgentCallContext`, `Message`, and `__version__` from package root. Importing `agentforge` must cause no network access, SDK client initialization, disk creation, or optional dependency import failure.

## Downloadable API server for JavaScript applications

The user wants to distribute a ready-made API server with the Python package. Include this server in the first release as an optional installation extra. Developers must be able to install and start it without writing a Python backend themselves. This is a self-hosted, single-owner, single-project service per server instance, not an AgentForge-hosted SaaS product or a multi-user account system. The caller's application backend is responsible for authenticating its own end users before calling this private service.

### Installation and launch contract

Implement `agentforge serve` in `cli.py`, with optional dependencies loaded only when this command is invoked. Provide `--host` (default `127.0.0.1`), `--port` (default 8000), `--provider`, `--model`, `--project-id`, `--memory/--no-memory`, `--memory-backend`, `--decompose/--no-decompose`, `--error-loop/--no-error-loop`, `--token-budget`, `--model-context-limit`, `--max-output-tokens`, and optional server-only `--codebase-path`/`--compress-context`. The server API must not accept these configuration controls from HTTP clients. Read provider keys, Redis URL, and a required service bearer token (`AGENTFORGE_SERVER_TOKEN`) from environment. Validate the token before binding a socket and mask it in all logs. Do not take the token as a command-line argument.

Use FastAPI for HTTP and Uvicorn for ASGI serving. Resolve/test compatible versions. Add a `server` extra containing `fastapi` and `uvicorn`; add `httpx` to dev for HTTP client tests. Include server dependencies in `all`, updating its documented meaning. Root import and CLI help must still work without the server extra. A missing extra must show the exact installation command. Do not start Uvicorn during import.

Document these checkout-development commands (after environment activation):

```bash
python -m pip install -e ".[server,redis,anthropic]"
# Set ANTHROPIC_API_KEY, REDIS_URL, AGENTFORGE_SERVER_TOKEN,
# AGENTFORGE_MODEL, and AGENTFORGE_CONTEXT_LIMIT privately.
agentforge serve --provider anthropic --model "$AGENTFORGE_MODEL" --project-id my-website --memory --memory-backend redis --model-context-limit "$AGENTFORGE_CONTEXT_LIMIT"
```

Document wheel equivalents and `pip install "agentforge-coding[server,redis,anthropic]"` only as valid after the owner's package is published. A developer still needs an installed Python runtime and a running service; downloadable does not mean a Python-free standalone binary. No Docker image, hosted service, JavaScript npm SDK, or packaging as an executable binary is required in this release.

### `server_schemas.py`

Define strict bounded schemas:

- `GenerateRequest(task: str)`: reject blank/whitespace-only tasks, impose a documented maximum character length, and forbid extra fields. In particular, reject client-supplied `project_id`, user IDs, API keys, model overrides, budgets, filesystem paths, validator commands, and Redis URLs.
- `ApiError(code: str, message: str, request_id: str)`: safe operational error response. No credentials or raw provider exception payloads.
- `GenerateResponse`: the complete JSON-safe `AgentResult` public schema; reuse its definitions or a typed adapter to avoid schema drift.
- `HealthResponse(status: Literal["ok"], version: str)`.

Project identity comes exclusively from the operator's server configuration. One shared bearer token represents access to that configured project, not tenant identity. Never use arbitrary HTTP project strings to select other users' Redis memory. Explain that separate customer deployments/projects require separate configured instances or a future authenticated multi-tenant design.

### `server.py`

- `ServerConfig`: validated host/port, `AgentConfig`, required secret token, task/body size caps, and operator-configured optional origin allowlist. Keep it separate from wrapper config.
- `create_app(config: ServerConfig, wrapper_factory: Callable[[], AgentWrapper] | None = None) -> FastAPI`: create the app and register routes; no immediate provider/Redis request. Injection supports offline tests. Use application lifecycle cleanup for internally owned resources.
- `authenticate_request(authorization: str | None, configured_token: str) -> None`: validate `Authorization: Bearer ...` with constant-time comparison; absent/invalid tokens return HTTP 401 and `WWW-Authenticate: Bearer`. Do not log header values.
- `GET /health`: HTTP 200 and `HealthResponse`, without contacting model/Redis. Do not expose configuration or secrets.
- `POST /generate`: authenticate before generation, validate/limit the body, execute a wrapper run with fixed project/settings, and return `GenerateResponse`.
- Run blocking synchronous AgentForge calls in a worker thread using a sync route or explicit threadpool dispatch. Do not block the ASGI event loop.
- Allow only one active generation per server instance for v0.1, enforced by a nonblocking process-local guard. Return HTTP 429 `server_busy` immediately for overlap. Run with one Uvicorn worker and no automatic reload by default; document that multiple processes would bypass this local guard. Keep health responsive during generation.
- Construct a fresh wrapper/ledger for each accepted request using the factory; close internally owned wrapper resources in `finally`, preserve injected caller-owned resource ownership rules, and never reuse a non-reentrant wrapper across active requests.
- Limit accepted request body bytes independently of task string validation, including chunked bodies; reject excess as 413 and media types other than JSON as 415. Document chosen limits.
- Return HTTP 200 for completed runs, including `AgentResult` statuses such as `validation_failed` or `budget_exceeded`: these are generation outcomes the JS client must inspect. Return typed HTTP errors for malformed requests (422), authorization (401), busy (429), pre-run configuration/internal failures (500, sanitized), and oversized input (413). Do not silently convert programming bugs into successful run results.
- No artifact writes, generated-code execution, command validator, or HTTP memory-clear operation through this server. It returns artifacts only. Optional codebase reads are bounded and fixed by operator configuration.
- Bind loopback by default. If the developer exposes the service on another machine, document authenticated private access and HTTPS termination in their deployment. Do not claim the single token is a complete public multi-tenant security/billing system.
- CORS is disabled by default because the recommended caller is the JavaScript application's backend. If explicit browser origins are enabled, use an operator allowlist, no wildcard credential access, and document that the service token must not be shipped in public browser bundles. Do not enable all origins automatically.
- Client disconnection does not guarantee a dispatched API operation is canceled or refunded. Keep the concurrency guard until the worker actually completes and finalize usage/memory correctly; do not release capacity while a detached generation continues.

### JavaScript connection example

Create `examples/javascript_client.mjs`, a Node.js backend-only example using built-in `fetch`. It reads `AGENTFORGE_URL` (defaults to `http://127.0.0.1:8000`) and `AGENTFORGE_SERVER_TOKEN` from environment, sends `POST /generate` with JSON `{ "task": "Create a React login page" }` and bearer authentication, checks HTTP status, then checks `result.success`/`result.status`. Print artifacts or safe failure diagnostics; no secrets. Do not import this file into browser components. Provide a brief Next.js server-route illustration in `docs/server.md` explaining that the browser calls its own authenticated app backend, which forwards authorized requests to AgentForge. That app must enforce per-user quotas/ownership before spending its model budget; do not place provider or service keys in `NEXT_PUBLIC_*` variables.

### Server tests and offline demo

Use FastAPI TestClient/httpx and injected FakeProvider/mock memory only. Test health without credentials to providers, valid authentication, missing/invalid service tokens, invalid/oversized/chunked requests, forbidden request overrides, success and failure JSON schema, fixed project identity, concurrent busy rejection, resource cleanup, missing server extras, and CLI serve argument mapping. Test that disconnect handling retains the guard until work completion. No remote HTTP calls, live Redis, live models, or real secrets during tests.

Supply an explicitly labeled fake-provider server demo through `agentforge serve --provider fake --model fake --project-id demo`; create a new scripted FakeProvider per request so demos do not exhaust one shared queue. It needs only the `server` extra and a locally configured service token; its replies are demo fixtures, not real AI generation. Verify a local loopback HTTP request using the JavaScript example, then shut down the demo cleanly. Local HTTP testing is allowed by the offline-only build constraint; authenticated remote provider/Redis calls remain forbidden.

Add the downloadable server, installation steps, fixed-project scope, and backend-only JavaScript connection to README and `docs/server.md`. Finish the server implementation and tests along with the original framework scope. Report exactly which parts were tested offline and that live integrations remain untested.

## 5. How modules connect

```text
CLI or Python API -> AgentConfig -> AgentWrapper
AgentWrapper -> memory + compressor -> bounded context
AgentWrapper -> TaskDecomposer -> ModelRouter -> provider
AgentWrapper -> RepairLoop -> ModelRouter -> provider
RepairLoop -> parse_generation -> artifact merge -> validator
Every provider request -> same run TokenLedger
Accepted artifacts + attempts -> AgentResult -> optional memory append
Explicit output action -> write_artifacts
Decorator opaque mode -> augmented callback task -> original callback output
Decorator structured mode -> AgentCallContext -> ModelRouter + ledger
```

`types`, `exceptions`, and pure `utils` form the dependency base. Provider adapters do not import core. Memory/compression never call SDKs. Prompts never perform I/O. Core owns orchestration, not SDK-specific mapping. Keep imports acyclic; do not solve cycles with scattered imports except intentional lazy optional SDK loading.

## 6. Dependencies and pip packaging

Use `pyproject.toml` with setuptools PEP 517/518 build configuration and PEP 621 metadata. No `setup.py` needed. Configure package discovery for `agentforge*` only; exclude examples, tests, generated files, and docs from import packages. Include `py.typed` in the wheel. Include README and MIT license in source distribution. Use a single version source or verify static metadata and `__version__` stay consistent.

Base runtime dependencies: `pydantic>=2,<3`, `typer>=0.12,<1`, `platformdirs>=4,<5`, `filelock>=3,<4`, and `pathspec>=0.12,<1`. These are intended compatibility ranges; resolve and test a concrete compatible set rather than claiming every version has been tested.

Extras:

- `anthropic`: official `anthropic` SDK, a minimum tested release and a compatible major-version upper bound.
- `openai`: official `openai` SDK, a minimum tested release and a compatible major-version upper bound.
- `redis`: `redis` client, minimum tested version and compatible upper bound.
- `server`: FastAPI and Uvicorn, as defined in the downloadable server specification.
- `all`: both SDKs, Redis, FastAPI, and Uvicorn; ensure extras do not drift.
- `dev`: pytest, pytest-cov, Ruff, mypy, build, twine, httpx, plus dependencies needed for mocked adapter and server tests. Tests must not require API credentials.

Do not guess exact SDK version constraints. Inspect official docs and install/test the chosen versions; state versions in docs/check report. Use standard library logging, JSON, AST, pathlib, subprocess, hashing, and UUID utilities. No LangChain, agent graph framework, embedding service, or tokenizer dependency required for this initial lightweight implementation.

Required metadata and entry-point shape:

```toml
[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agentforge-coding"
version = "0.1.0"
description = "Lightweight orchestration for AI coding workflows"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE"]
authors = [{name = "Abdul Rafe"}]
# Add dependencies and optional dependencies described above.

[project.scripts]
agentforge = "agentforge.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["agentforge*"]

[tool.setuptools.package-data]
agentforge = ["py.typed"]
```

Add accurate GitHub project URLs from the supplied README, classifiers, test/lint/type-check tool settings, and optional dependency tables. Check whether `agentforge-coding` is available/owned on PyPI before proposing publication; don't rename the import automatically. If the distribution name is unavailable, report that publishing requires an owned distribution name. Local editable/wheel installation must still work. Do not upload/publish as part of this task.

Development and verification commands:

```bash
python -m venv .venv
# Activate the environment using the appropriate OS command.
python -m pip install --upgrade pip
python -m pip install -e ".[dev,all]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agentforge
python -m build
python -m twine check dist/*
```

In a fresh virtualenv outside the repository working directory, install the built wheel, verify `import agentforge`, run `agentforge --help`, `python -m agentforge --help`, and a fake-provider run. Prove base installation works without SDK/Redis extras and the installed CLI comes from the wheel, not checkout imports. Test source distribution installation as well. Document TestPyPI/PyPI upload commands in `docs/publishing.md` as maintainer-only future actions; explain editable vs wheel vs published installation. `pip install agentforge-coding` from PyPI only works after the correct distribution has actually been published.

## 7. Tests and acceptance criteria

No real network calls in default tests. Inject FakeProvider or mocked SDK clients. Include these behavioral tests:

1. Package root imports without optional SDKs, credentials, network, or filesystem side effects.
2. Single-step successful wrapper run yields correct `.code`, artifacts, steps, status, usage, and IDs.
3. Planning generates valid stable dependency order; cycles, missing dependencies, duplicate IDs, malformed JSON, empty/excess steps fail clearly.
4. Planning, all attempts, and integration share one ledger. A second run resets usage but retains project memory.
5. Invalid Python triggers repair, succeeds on the next attempt, and accounts both calls. Repeated failure stops after `1 + max_retries`; zero retries runs once.
6. With an injected semantic validator, combined-artifact validation catches cross-step regression, preserves earlier accepted state, and repairs within the same step's retry bound. Default syntax validation tests assert only syntax/structure behavior; no semantic guarantees.
7. Budget preflight prevents calls with insufficient allocation; output cap is clamped; fallback switches before exhaustion without resetting tokens. Missing/uncertain usage never becomes zero. No calls after exhaustion. Strict mode rejects unsupported accounting before generation.
8. Local memory survives constructing a new wrapper/process with the same project ID, isolates projects, handles corruption, and prevents lost updates with concurrent backend writers. Redis behavior is tested with a fake client; optional real Redis tests are separately marked.
9. Context excludes secrets, binaries, ignored files, caches, oversized files, and outside-root symlinks; selected chunks stay bounded and include path/line provenance.
10. Artifact output rejects path traversal, absolute/drive/UNC paths, duplicate paths, symlink escapes, and accidental overwrite; normal multi-file writes work.
11. SDK adapters map request caps and actual usage correctly; cache/reasoning usage is not double-counted. Auth failures/refusals/truncated outputs remain failures. Mocked clients don't require keys; hidden SDK retries are disabled.
12. Opaque decorator preserves function identity/signature, arguments, return type, and exceptions. Unsupported controls fail honestly. Structured routed calls get counted exactly once. Async callbacks are explicitly rejected.
13. CLI help/version work, errors have correct exit codes, JSON stdout parses cleanly, task inputs are validated, fake-provider demo works without keys, and output directories are only written when requested.
14. Unknown model limits require an explicit limit; unsupported strict-mode counting fails before paid calls. Memory read/write errors follow the defined distinct policies. Decorator keyword task binding, reserved context injection, and multi-call aggregate usage work.
15. Wheel/sdist metadata, root exports, version consistency, console entry point, package-data inclusion, and clean-environment install pass.

CI tests Python 3.11, 3.12, and 3.13 on Linux; add Windows smoke coverage for file paths, local memory, and CLI installation. Perform a build/wheel smoke check in CI. Keep live provider smoke tests optional, environment-gated, and excluded from standard CI to avoid charges. Do not claim a live integration passed when only mocked tests ran.

## 8. Documentation and examples

Rewrite README to match the working implementation while retaining the purpose and author credit. Include actual install extras, Python requirement, environment variables, all three entry points, code output format, persistence behavior, strict-vs-estimated accounting, fallback semantics, validation scope, decorator limitations, and roadmap. Replace unverified supported-model claims with provider support plus configurable tested model IDs. Do not mark roadmap work completed without code.

`.env.example` contains placeholders only for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AGENTFORGE_MODEL`, and `REDIS_URL`, `AGENTFORGE_CONTEXT_LIMIT`, `AGENTFORGE_SERVER_TOKEN`, and `AGENTFORGE_URL`. `.gitignore` excludes `.env`, environments, caches, local memory, generated output, build artifacts, and credentials. LICENSE is MIT with README author attribution.

Examples:

- `basic.py`: offline fake provider returning a runnable Python artifact and printing result fields.
- `with_claude.py` / `with_openai.py`: real opt-in SDK setup using environment key/model and documented extras.
- `multi_step_project.py`: deterministic fake plan + artifacts demonstrating shared state and final integration; show real-provider substitution.
- `error_loop_demo.py`: fake invalid source followed by corrected source; show diagnostics, attempt count, usage.
- `decorator_demo.py`: opaque return preservation plus structured routed call, clearly separated.

All offline examples run with the base install, require no secrets, and must be verified. Real examples fail with actionable configuration errors when credentials/model variables are missing.

## 9. Execution sequence and final handoff

Implement in this order: shared contracts/config/errors; providers and router/ledger; memory and compression; prompts/planning/artifacts/validation; core; decorators/CLI and downloadable API server; packaging/examples/docs; tests/CI. Add tests alongside behavioral modules. Use deterministic offline end-to-end scenarios to validate the assembled system before attempting optional live calls.

Completion requires real files and passing authorized checks, not a narrative claim. Avoid empty methods, placeholder TODOs, unconditional success validators, fabricated usage, unimplemented advertised backends, or silent production mocks. Protocol ellipses and abstract interfaces are fine; runtime code must be implemented.

Your final response must provide:

- What was built and the final public API.
- Exact local install and offline demo commands.
- Environment/extra requirements for real OpenAI and Anthropic calls.
- Checks run and their actual outcomes; explicitly list blocked checks.
- Budget, decorator, and validation limitations that matter to users.
- Build artifact paths and any remaining publication-name ownership issue.
- Downloadable server startup commands and verified backend-only JavaScript connection example.

Continue until this first-release scope is complete. Do not publish the package, upload secrets, or expand into roadmap features.

---

Reference documentation to consult while implementing:

- Python packaging metadata: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- Distribution builds and publication: https://packaging.python.org/en/latest/tutorials/packaging-projects/
- OpenAI SDK: https://github.com/openai/openai-python
- OpenAI API: https://developers.openai.com/api/reference/
- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- Anthropic API: https://platform.claude.com/docs/en/api/messages/create
- FastAPI deployment: https://fastapi.tiangolo.com/deployment/manually/
- FastAPI synchronous handlers: https://fastapi.tiangolo.com/async/

These are implementation references, not evidence that every model name in the original README is available.
