# AgentForge

AgentForge helps an existing coding agent, starting with Codex, retrieve bounded relevant code, with optional memory, task tracking and validation feedback. The local `agentforge assist` helpers need no separate model API. Python 3.11+; by **Abdul Rafe**.

The existing provider framework, Python API, FakeProvider examples and optional authenticated server are preserved. Their routed token accounting is separate from Codex's usage. AgentForge cannot control Codex's internal token allowance; No token benefit or quality improvement has been demonstrated.

## Install from this repository

```bash
git clone https://github.com/Abdul-Rafe8311/agent-forge.git
cd agent-forge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
agentforge --help
```

On Windows activate with `.venv\Scripts\Activate.ps1`. Extras: `openai`, `anthropic`, `redis`, `server`; `all` installs both SDKs, Redis, FastAPI and Uvicorn; `dev` installs verification tools and mocked-test dependencies. Example: `python -m pip install -e ".[dev,all]"`.

This repository has **not been published to PyPI**. The [existing PyPI agentforge project](https://pypi.org/project/agentforge/) belongs to another project. This distribution is now named **agentforge-coding**; Python imports and the CLI remain **agentforge**. Use this checkout or its locally built wheel until publication.

## Use with Codex

This checkout includes `.agents/skills/agentforge-coding`. Open Codex in this repository and explicitly invoke `$agentforge-coding`. To use the packaged skill in another project:

```bash
agentforge assist install-skill --destination /absolute/project/.agents/skills/agentforge-coding
agentforge assist --project /absolute/project context --query "affected symbols or behavior"
```

Relevant context retrieval is the default workflow: no session, decomposition or
memory setup is required. Keep original requirements and acceptance checks
accessible; use normal editing/testing tools. The explicit skill is concise, and
its tracking reference is optional. Context replies default to 4 KiB/three snippets
with source references and explicit omission markers. Local memory remains the
default when tracking is selected, even when `REDIS_URL` exists.

Follow the [helper workflow](docs/coding-agent-integration.md),
[implementation plan](docs/coding-agent-integration-plan.md), and
[benchmark protocol](docs/benchmarking.md). The [controlled pilot](docs/pilot-benchmark-2026-10-13.md)
passed the same acceptance checks in all three conditions, but helpers used more
reported tokens. The [lighter workflow and matched comparison](docs/lightweight-workflow.md)
address observed overhead. The [matched A/B attempts](docs/lightweight-pilot-2026-10-14.md)
failed before thread creation; token counters are unavailable. Neither was restarted.
No token benefit is established for the revision.

## Offline demo

```bash
agentforge run --provider fake --model fake --task "demo" --json
python examples/basic.py
python examples/multi_step_project.py
python examples/error_loop_demo.py
python examples/decorator_demo.py
```

FakeProvider returns labeled deterministic fixtures; it does not solve arbitrary tasks.

## Python API

```python
from agentforge import AgentWrapper

with AgentWrapper("fake", provider="fake", task_decompose=True, max_steps=2) as agent:
    result = agent.run("Create a greeting fixture")
print(result.status, result.tokens_used, result.code)
# Explicit file delivery only:
if result.success:
    result.write_to("generated")  # existing files require overwrite=True
```

`AgentWrapper.run` returns an `AgentResult` containing typed artifacts, step attempts, diagnostics, status, usage, session and project IDs. `artifacts` is authoritative; `code` is one file's content or a deterministic multi-file rendering. Expected execution failures return partial accepted output. Invalid configuration raises. Wrappers are synchronous and non-reentrant; each run gets a fresh ledger.

The third entry point is `optimize`. Opaque mode preserves a callback's return, signature, arguments and exceptions; optional memory/context augments its task. It cannot control the callback's model calls. Structured mode requires a keyword-only `agentforge_context` and an `AgentCallResult`, and accounts only calls routed through that context. See [API](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/api.md) and the decorator example.

## Real providers and memory

Install `.[openai]` or `.[anthropic]`. Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` privately, plus `AGENTFORGE_MODEL` and `AGENTFORGE_CONTEXT_LIMIT`. The opt-in examples use these variables. Exact model IDs pass through unchanged; no availability or model aliases are promised. Real adapters require an operator-supplied verified context window and use OpenAI Responses / Anthropic Messages.

Local memory defaults to the platform user-data directory, persists versioned JSON per hashed project, and uses file locks and atomic replacement. Explicit `project_id` overrides a hash of the codebase root/current directory. Redis memory uses the optional official client over verified TLS/TCP to Upstash: set the database's read/write `REDIS_URL` privately (`rediss://`, not HTTPS REST). A memory read failure stops generation; a write failure preserves the computation and adds a warning.

## Accounting and validation

One ledger covers planning, execution, repairs and integration. Fallback selects another configured model after a threshold without resetting or increasing the budget. Admission uses provider input counts or a conservative UTF-8 estimator, and clamps output against session and context allowances. Unknown dispatched usage charges the full reservation and marks accounting incomplete. Detected overspend retains actual totals and stops.

Strict admission currently works with FakeProvider only; real SDK adapters reject strict mode before count/generation because their live assumptions have not been verified. Token budgets are not dollar caps; counting operations can have their own limits/costs. See [accounting](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/token-accounting.md).

Default validation checks output structure, safe paths and Python AST syntax; other languages receive structure-only checks. Syntax cannot prove imports or behavior. `CommandValidator` is explicit opt-in and runs a subprocess, which is not a security sandbox. Files are never written without explicit export; replacement is atomic per file, not across an entire bundle.

## Downloadable API server and JavaScript

The optional server is implemented and ships in the wheel. It is a self-hosted, single-owner, fixed-project service requiring Python, not an executable binary or hosted product.

```bash
python -m pip install -e ".[server]"
# Set AGENTFORGE_SERVER_TOKEN privately before launching.
agentforge serve --provider fake --model fake --project-id demo
# In a backend-only Node.js process with the same token:
AGENTFORGE_URL=http://127.0.0.1:8000 node examples/javascript_client.mjs
```

`GET /health` requires no provider calls. `POST /generate` requires bearer authentication and accepts only `{"task":"..."}`; project, keys, paths, models and budgets are operator settings. It returns artifacts without writing/executing them. One generation is allowed at a time; overlapping requests return 429. Completed run failures use HTTP 200, so clients must inspect `success` and `status`. Defaults: loopback, one worker, no reload or CORS. See [server setup and Next.js forwarding](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/server.md).

## Verification and roadmap

All automated tests and offline demos use FakeProvider or mocked SDK/Redis clients. **Live OpenAI and Anthropic integrations have not been tested.** The user reported one successful live Redis memory save/reopen/load check with seven completed client command frames; Upstash quota usage was not measured. That check is excluded from automated tests and CI. No package uploads or purchases were performed. See [verification report](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/verification.md), [configuration](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/configuration.md), [architecture](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/architecture.md), [security](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/security.md), [packaging](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/publishing.md), [Redis smoke guide](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/redis-memory-smoke.md) and [TestPyPI release instructions](https://github.com/Abdul-Rafe8311/agent-forge/blob/main/docs/testpypi.md).

Unimplemented roadmap: Gemini, a VS Code extension, web dashboard, team memory and multi-tenant hosting. No quality or spend-reduction claims are made.

MIT license — Copyright Abdul Rafe.
