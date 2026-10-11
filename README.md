# AgentForge

A lightweight Python runtime for coding agents with project memory, task planning,
validation and repair, token admission limits, and codebase context selection.

This is a local implementation of the supplied design. All demos work offline.
**Live OpenAI and Anthropic API integrations have not been tested.** Provider tests
use mocked SDK clients; the remaining tests use FakeProvider. Nothing is published
to a package registry.

## Install locally

Requires Python 3.10 or later. From this project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Install optional adapters or development tools when needed:

```sh
python -m pip install -e '.[openai,anthropic]'
python -m pip install -e '.[redis]'
python -m pip install -e '.[dev]'
```

Use local installation: the package name on PyPI may belong to a different project.

## Quickstart: offline wrapper

```python
from agentforge import AgentWrapper, FakeProvider

agent = AgentWrapper(
    model="fake",
    provider=FakeProvider(),
    memory=True,
    project_id="my-project",
    task_decompose=True,
    error_loop=True,
    max_retries=3,
    token_budget=50000,
)
result = agent.run("Create a greeting module")
print(result.code)
print(result.steps_taken)
print(result.tokens_used)  # Simulated usage with FakeProvider.
result.write_to("generated")  # Refuses existing files unless overwrite=True.
```

FakeProvider generates a fixed greeting fixture. It demonstrates orchestration;
it does not solve arbitrary tasks. Configure a real provider in your own application
when you want model generation.

## Wrap an existing agent

```python
from agentforge import optimize


@optimize(model="custom", memory=True, project_id="my-project")
def my_agent(prompt: str) -> str:
    # Replace this offline stub with your existing agent.
    return "answer = 42\n"


result = my_agent("Create an answer module")
print(result.code)
```

The function receives the task plus selected memory and artifact context.
It returns Python source, a JSON file bundle, or `AgentResponse`; the decorator
returns `AgentResult`. Its model option labels the underlying callable.
Opaque functions cannot enforce token output limits, so finite budgets are rejected
for this adapter. Inject a bounded provider into `AgentWrapper` for budget control.

## CLI

```sh
agentforge run --model fake --task "Create a greeting module" --memory --decompose
agentforge run --task "Create a greeting module" --output generated --json
python -m agentforge --help
```

The CLI defaults to `fake` and never reads environment API keys. Live model runs
require an explicit `--api-key-file` and the corresponding optional SDK. All demos
and checks in this project use fake or mocked providers; live commands were not run.
Failures exit with code 2 and emit JSON on stderr, including partial results when available.

## OpenAI and Anthropic adapters

`OpenAIProvider` and `AnthropicProvider` accept an explicit SDK `client` or explicit
`api_key`. Injected clients have automatic retries disabled. No credentials are
read and no clients are created merely by importing the package. No environment
key discovery is implemented.

```python
# sdk_client is configured by your application. This code is not an offline demo.
from agentforge import AgentWrapper, OpenAIProvider


def make_agent(sdk_client):
    return AgentWrapper(model="gpt-6", provider=OpenAIProvider(client=sdk_client))
```

For Anthropic, use `AnthropicProvider(client=sdk_client)` with your model ID.
Model IDs are passed through, including the IDs used in the supplied README;
availability depends on your provider/account. There is no verified model catalog.
Gemini is not implemented.

Run `examples/with_openai.py` and `examples/with_claude.py` to exercise both adapters
using **mocked clients**. See [design and API references](docs/design.md) for the
integration contract and limitations.

## Configuration

| Option | Default | Behavior |
| --- | --- | --- |
| `model` | `"fake"` | Provider model ID or an offline fixture |
| `provider` | Selected by model | Inject a bounded provider or FakeProvider |
| `api_key` | `None` | Explicit key when constructing a real provider without a client |
| `memory` | `False` | Persist successful task records |
| `memory_backend` | `"local"` | SQLite, `"redis"`, or injected backend |
| `memory_path` | `".agentforge"` | Local SQLite storage directory |
| `project_id` | `"default"` | Memory namespace; set one per project |
| `redis_url` | `redis://localhost:6379/0` | Redis connection configuration |
| `task_decompose` | `False` | Request a plan and final integration |
| `max_steps` | `10` | Maximum implementation plus integration steps |
| `error_loop` | `True` | Repair invalid plans/output |
| `max_retries` | `3` | Repairs after the initial attempt, per operation |
| `token_budget` | `50000` | Shared per-run input and output allowance; `None` disables it |
| `max_output_tokens` | `4096` | Per-request maximum, reduced to fit remaining budget |
| `token_margin` | `64` | Additional input count allowance |
| `fallback_model` | `None` | Optional model for the remaining budget |
| `fallback_provider` | Same provider | Explicit adapter for cross-provider fallback |
| `fallback_threshold` | `0.8` | Switch on the next request after this budget fraction |
| `context_compression` | `False` | Select source context from a codebase |
| `codebase_path` | `None` | Required when selecting codebase context |
| `max_context_chars` | `16000` | Maximum selected source context |
| `max_memory_chars` | `12000` | Maximum selected memory context |
| `validator` | `None` | Additional merged-file checks; raise on invalid output |

The token limit is a request admission guard, not a guaranteed bill limit.
Reported usage can differ from preflight counts; an overrun stops subsequent
work. Planning, retries, and integration all count. Fallback switches before
exhaustion and retains the same budget. Unknown usage after a failed generation
charges its reservation as an estimate and stops. See [the design](docs/design.md).

## Output and validation

Providers return this JSON shape:

```json
{"files": {"app.py": "answer = 42\n"}, "summary": "Created the module"}
```

The runtime validates paths, JSON, and Python syntax without executing generated
code. A custom validator can add checks. Files are merged across steps and are
exported only when explicitly requested. Other languages need custom validation.
Context selection uses lexical relevance and bounded excerpts; it is not semantic
summarization. `.agentforgeignore` supports relative glob patterns.

## Examples and offline checks

```sh
python examples/basic.py
python examples/decorator.py
python examples/multi_step_project.py
python examples/error_loop_demo.py
python examples/with_openai.py
python examples/with_claude.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
ruff check .
python -m build --no-isolation
```

Tests block outbound socket connections. SDK tests use mocks for generation,
token counts, construction, and errors. Redis uses a mocked client. No model
API calls, purchases, or publication are required by these checks.
See the [offline verification report](docs/verification.md) for results and limitations.

## Project layout

```text
agentforge/
  core.py         Wrapper and decorator
  memory.py       SQLite and Redis project memory
  decomposer.py   Bounded JSON plans
  validator.py    File bundles and syntax checks
  compressor.py   Lexical context selection
  router.py       Shared token ledger and model fallback
  providers.py    Fake, callable, OpenAI and Anthropic adapters
  types.py        Request, response and result contracts
  cli.py          Command line entry point
examples/
docs/
tests/
pyproject.toml
```

## Roadmap

- [x] Wrapper, decorator, and CLI
- [x] Local and Redis memory adapters
- [x] Bounded task decomposition and repair
- [x] Token admission guard and fallback routing
- [x] Offline provider tests and examples
- [ ] Live provider verification
- [ ] Gemini adapter
- [ ] VS Code extension and session dashboard
- [ ] Team coordination

## License

MIT. Built by Abdul Rafe.
# agent-forge
