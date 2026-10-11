# Offline verification report

Verified on macOS with Python 3.14.0. All provider generation/counting and Redis tests use FakeProvider or mocked official SDK clients. Tests delete inherited provider/Redis credentials and block socket connections and DNS. No live OpenAI/Anthropic endpoint or hosted Upstash command was invoked.

Distribution: **agentforge-coding 0.1.0**. Import/CLI: **agentforge**. Metadata, installation examples, optional-dependency errors, artifact discovery and tests use the new distribution name. Old-name generated artifacts were preserved under the ignored build directory; dist contains only the renamed wheel/sdist. The local editable environment was migrated to agentforge-coding.

## Actual outcomes

| Check | Outcome |
| --- | --- |
| pytest, plugin autoload disabled | 128 passed |
| Ruff check | passed |
| Ruff format --check | 59 files formatted |
| mypy agentforge | no issues in 24 source files |
| setuptools wheel + sdist build | both built |
| twine check (metadata only) | both passed |
| fresh base wheel installation outside checkout | passed |
| fresh source-distribution installation outside checkout | passed |
| fresh wheel and sdist installs with server extra | both passed |
| installed server health/auth/FakeProvider ASGI checks, socket access blocked | both passed |
| installed imports, py.typed, CLI and module CLI | passed |
| base installation without OpenAI/Anthropic/Redis/FastAPI/Uvicorn | passed |
| server-extra installations without OpenAI/Anthropic/Redis/httpx | passed |
| four base-only offline examples | passed |
| local Uvicorn fake server + Node.js backend fetch | HTTP success, fixed demo project, one artifact; server stopped |

Offline coverage includes atomic ledger reservations/reconciliation/unknown charges, overspend stop, shared planning/repair/integration accounting, fallback, context admission, strict rejection before calls, stable dependency validation, artifact paths/collisions/preflight, partial accepted results, merged-candidate semantic validators, syntax repairs, non-reentrancy including persistence, memory corruption/read/write policies and concurrent writers, mocked verified TLS Redis, SDK payload/cap/cache/error contracts, cleanup ownership, opaque/structured decorators, CLI exits/export failures, server auth/body/schema/concurrency/disconnect and sanitized errors.

The local HTTP check used a synthetic private service token on loopback port 18765 and fake generation only. All inherited provider/Redis credentials were removed from the child environment. No service remains running.

Dependency downloads needed permission outside the restricted network sandbox. Temporary base environments were created outside checkout and removed afterward. All four installations resolved imports to installed site-packages, not repository source, and verified the distribution metadata and unchanged console entry point. Server checks use the installed ASGI app directly, without binding sockets or requiring dev-only httpx. macOS temporary aliases were resolved before safe artifact export.

## Concrete versions exercised

| Dependency | Version |
| --- | --- |
| OpenAI SDK (mocked) | 2.54.0 |
| Anthropic SDK (mocked) | 0.125.0 |
| Redis (mocked) | 7.4.1 |
| Pydantic | 2.13.4; fresh base install 2.14.1 |
| Typer | 0.27.3 |
| platformdirs | 4.13.0 |
| filelock | 3.32.3; fresh base install 3.32.7 |
| pathspec | 0.12.1 |
| FastAPI / Starlette | 0.115.6 / 0.41.3 |
| Uvicorn / httpx | 0.34.0 / 0.28.1 |
| fresh server-extra smoke: FastAPI / Starlette / Uvicorn | 0.143.0 / 1.7.0 / 0.54.0 |
| pytest / Ruff / mypy | 8.3.4 / 0.17.0 / 1.19.1 |
| build / twine / setuptools | 1.6.1 / 7.0.0 / 84.0.0 |

These are actual tested sets, not proof of every version in compatibility ranges. FastAPI/Starlette emitted 172 Python 3.14 deprecation warnings concerning asyncio.iscoroutinefunction; tests passed. CI is configured for Linux Python 3.11, 3.12, 3.13 and Windows 3.13, including build and fresh base/server wheel/sdist checks. Those OS/interpreter combinations were not run on this local macOS host; inspect repository Actions for remote outcomes.

## Unexercised and publication status

**Live OpenAI, Anthropic and Upstash integrations have not been tested**, as required by the cost constraint. Credentials, account model availability, remote timeout behavior, provider counting/cap assumptions and real TLS connectivity remain unverified. Real adapters deliberately reject strict mode. No live smoke checks are enabled in standard CI. No packages were published or services purchased.

Budgeting covers routed generation tokens, not opaque callback calls or dollar spend; unknown outcomes are conservative charges. AST validation proves syntax only. Explicit command validation is not a sandbox. Artifacts replace atomically per file rather than as a bundle.

Artifacts: `dist/agentforge_coding-0.1.0-py3-none-any.whl` and `dist/agentforge_coding-0.1.0.tar.gz`; generated files remain ignored, not committed. [PyPI agentforge](https://pypi.org/project/agentforge/) is already another project, so the authorized distribution name is now agentforge-coding. It has not been published; import and CLI remain agentforge.

Public implementation references: [OpenAI Python SDK](https://github.com/openai/openai-python), [OpenAI API](https://developers.openai.com/api/reference/), [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create), [redis TLS](https://redis.readthedocs.io/en/stable/examples/ssl_connection_examples.html), [FastAPI sync handlers](https://fastapi.tiangolo.com/async/), [FastAPI deployment](https://fastapi.tiangolo.com/deployment/manually/), [packaging metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/). These document shapes and setup; they do not establish a passing live integration.
