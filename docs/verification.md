# Verification report

Verified on macOS with Python 3.14.0. All automated provider generation/counting and Redis tests use FakeProvider or mocked official SDK clients. Tests delete inherited provider/Redis credentials and block remote connections and DNS. No live OpenAI/Anthropic endpoint was invoked. The user separately reported a successful, opt-in live Redis memory smoke test; that result and its limits are recorded below. The live check was not repeated during this review.

Distribution: **agentforge-coding 0.1.0**. Import/CLI: **agentforge**. Metadata, installation examples, optional-dependency errors, artifact discovery and tests use the new distribution name. Old-name generated artifacts were preserved under the ignored build directory; dist contains the renamed wheel/sdist and local checksums. The local editable environment was migrated to agentforge-coding.

## Actual outcomes

| Check | Outcome |
| --- | --- |
| pytest, plugin autoload disabled | 140 passed |
| Ruff check | passed |
| Ruff format --check | 65 files formatted |
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

Build and fresh-install results above are from TestPyPI preparation commit
`3387170ff1ab91ca2f64a7429fc7e214fc1b01f7`. The Redis update reran mocked source
checks; those existing artifacts were not rebuilt or uploaded for this review.

## Live Redis result reported by the user

On 2026-10-12, the user reported that the live Redis memory smoke test **passed**
with **7 completed client command frames**. The smoke test generates one small
fixture using FakeProvider, saves one standard memory entry under a unique UUID
project, closes the backend, then reopens and loads once to compare project,
session, task, success and artifacts. Certificate and hostname verification stay
enabled. No real AI requests, database scans, polling, deletion or plan changes
are part of this cycle. This live result is user-reported; the agent did not repeat
it or collect the live transcript, credentials, host or test project ID.

**Seven completed client sends are not seven measured Upstash quota units.** The
client observer records command verbs after a completed local send. It does not
measure provider-side quota accounting, replication or dashboard usage, and a
send count alone does not establish server execution. The smoke test's successful
save/load comparison provides the functional result. Upstash quota usage remains
**unmeasured**; no extra statistics or monitoring request was issued to obtain it.

For database 0, the expected protocol sequence is `AUTH, MULTI, RPUSH, LTRIM, EXEC,
AUTH, LRANGE`: five data/transaction frames and two authentication frames. Mocked
SDK transport tests observed exactly that sequence. The user supplied the live
total of seven frames, not a per-command transcript; the expected/mock breakdown
must not be represented as independently observed live telemetry.

An earlier user-run attempt stopped with TLS certificate verification failure
during save and zero completed client frames. Offline diagnosis found that the
python.org Python 3.14 default CA file was missing, leaving zero trusted CA roots.
The default CA link was repaired using the existing Certifi bundle. Offline
checks then confirmed 121 trusted CA certificates in Python and Redis SSL
contexts, with required certificate and hostname verification intact. The user
subsequently reported the successful cycle above. Zero completed frames from the
failed attempt do not establish zero network activity or a zero quota increment.

Development, debugging and automated tests continue to use mocks only. Backend
SDK retries are explicitly zero; health polling and driver metadata are disabled.
The opt-in smoke check also blocks connection reattempts and legacy AUTH fallback,
reports ambiguous sends separately, and stops on failure before any retry.
See the [Redis smoke guide](redis-memory-smoke.md) for implementation and trust
repair details. Do not repeat the completed live check as part of review or CI.

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

These are actual tested sets, not proof of every version in compatibility ranges. FastAPI/Starlette emitted 172 Python 3.14 deprecation warnings concerning asyncio.iscoroutinefunction; tests passed. CI covers Linux Python 3.11, 3.12, 3.13 and Windows 3.13, including build and fresh base/server wheel/sdist checks.

The [Actions run for rename commit de4e801](https://github.com/Abdul-Rafe8311/agent-forge/actions/runs/38174495890) passed all three Linux jobs. Windows passed 113 tests but failed 15 server tests because Windows asyncio creates a loopback socket pair through the patched connect method. The guard now permits only that private pair and still blocks all ordinary connections and DNS. The new regression checks exercise the fallback and confirm the guards remain active. On macOS the regression needs local loopback permission outside the restricted sandbox; no external destination is permitted. All four jobs passed for the [fix commit 3387170](https://github.com/Abdul-Rafe8311/agent-forge/actions/runs/38175692887). That is historical CI evidence; check the current commit's [Actions](https://github.com/Abdul-Rafe8311/agent-forge/actions/workflows/ci.yml) before release.

TestPyPI preparation adds strict Twine metadata checks, `.pypirc` exclusion and a [secure account/upload/install guide](testpypi.md). Metadata remains agentforge-coding 0.1.0; no registry upload has occurred. TestPyPI download/install verification is pending an authorized upload.

## Unexercised and publication status

**Live OpenAI and Anthropic integrations have not been tested.** Account model
availability, remote provider timeout behavior and counting/cap assumptions remain
unverified. Upstash has only the small user-reported live save/reopen/load result
above; quota accounting, long-running behavior and broader hosted Redis scenarios
remain unverified. Real model adapters deliberately reject strict mode. No live
smoke checks are enabled in standard CI. No packages were published or services
purchased.

Budgeting covers routed generation tokens, not opaque callback calls or dollar spend; unknown outcomes are conservative charges. AST validation proves syntax only. Explicit command validation is not a sandbox. Artifacts replace atomically per file rather than as a bundle.

Artifacts: `dist/agentforge_coding-0.1.0-py3-none-any.whl` and `dist/agentforge_coding-0.1.0.tar.gz`; generated files remain ignored, not committed. [PyPI agentforge](https://pypi.org/project/agentforge/) is already another project, so the authorized distribution name is now agentforge-coding. It has not been published; import and CLI remain agentforge.

Public implementation references: [OpenAI Python SDK](https://github.com/openai/openai-python), [OpenAI API](https://developers.openai.com/api/reference/), [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create), [redis TLS](https://redis.readthedocs.io/en/stable/examples/ssl_connection_examples.html), [FastAPI sync handlers](https://fastapi.tiangolo.com/async/), [FastAPI deployment](https://fastapi.tiangolo.com/deployment/manually/), [packaging metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/). These document shapes and setup; the live Redis outcome above is based on the user's report, not these sources.
