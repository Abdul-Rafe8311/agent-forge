# Architecture

`types`, `exceptions` and pure `utils` form the base. Optional SDK clients and Redis connections are lazy; imports perform no remote requests or memory writes.

```text
Python / Typer CLI -> AgentConfig -> AgentWrapper
wrapper -> memory + source retrieval -> bounded optional context
wrapper -> TaskDecomposer / RepairLoop -> ModelRouter -> provider
every generation -> one run TokenLedger
repair -> strict artifact parse -> merge candidate -> injected validator
accepted delta -> accumulated state -> typed AgentResult -> optional memory
explicit export -> write_artifacts
HTTP /generate -> sync worker -> fresh wrapper for one fixed project
```

Plans are validated and executed in stable dependency order. Multi-step plans have exactly one integration step depending on all other steps within max_steps. A single format-repair allowance applies to planning. Execution repairs are separate and bounded per step. There is no extra unaccounted synthesis call.

RepairLoop is the sole candidate acceptance authority. It validates the merged snapshot and returns only accepted changes. Core commits those changes once. Failure retains previously accepted artifacts and all attempt diagnostics. Syntax validation cannot detect semantic interface regressions; custom validators can enforce them.

Each run resets ledger and artifacts, while project memory persists. Failed runs are retained as failures, and failed memory entries never establish working code. Required accepted code remains complete in later prompts; optional memory/retrieved text can be dropped to fit. Required overflow returns a typed failure.

Opaque decoration forwards the original output; structured decoration injects one routed context/ledger per invocation. Exception retries require explicit opt-in and reuse that ledger. Arbitrary external callback operations remain outside accounting.

Wrappers own adapters/backends they construct, close them via context managers, and retain caller ownership of injected resources. They guard the entire run including persistence against reentry. The server creates a fresh wrapper per request and retains its guard until worker completion, including disconnects.

Additional files have concrete purposes: `errors.py` retains compatibility exception aliases from the prototype; `scripts/check_installed.py` and `check_distribution.py` prove clean base wheel/sdist behavior; `test_examples.py` verifies runnable examples; `docs/build-prompt.md` records the supplied acceptance contract; `verification.md` records actual checks; `design.md` points old documentation to this architecture. `MANIFEST.in` includes non-package docs/examples/tests in source distributions. No roadmap features are implemented.
