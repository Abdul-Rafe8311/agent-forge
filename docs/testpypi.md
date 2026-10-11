# Prepare and verify agentforge-coding 0.1.0 on TestPyPI

Distribution: **agentforge-coding 0.1.0**. Python import and CLI: **agentforge**.
Python requires 3.11 or newer. No package has been uploaded. The upload in step 4
is a future maintainer action requiring explicit publication authorization.
All runtime verification uses FakeProvider; live OpenAI, Anthropic and Upstash
integrations have not been tested.

## 1. Review and build locally

Commands below target macOS/zsh and this checkout:

```bash
cd /Users/AbdulRafe/agentforge
git status --short --branch
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
unset OPENAI_API_KEY OPENAI_ADMIN_KEY ANTHROPIC_API_KEY REDIS_URL AGENTFORGE_SERVER_TOKEN
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy agentforge
.venv/bin/python -m build --no-isolation
.venv/bin/python -m twine check --strict \
  dist/agentforge_coding-0.1.0-py3-none-any.whl \
  dist/agentforge_coding-0.1.0.tar.gz
.venv/bin/python scripts/check_distribution.py
shasum -a 256 dist/agentforge_coding-0.1.0-py3-none-any.whl dist/agentforge_coding-0.1.0.tar.gz
```

Check Actions for the exact release commit: all Linux Python 3.11/3.12/3.13 and
Windows Python 3.13 jobs must pass. Record that commit and the two hashes before
uploading. Upload only those reviewed files; do not rebuild between review and
upload. The local `dist/` folder is ignored by git.

Metadata uses setuptools/PEP 621, MIT License-Expression and LICENSE, Markdown
README with public documentation links, version 0.1.0, project URLs, bounded
dependencies and explicit extras. Wheels contain the `agentforge` package,
`py.typed`, license and console entry point. Sdist also contains documentation,
examples, tests, scripts and CI. No metadata changes are needed to switch between
TestPyPI and PyPI: the upload URL selects the registry.

The distribution check creates four environments outside checkout: wheel and
sdist, each with base dependencies and with `[server]`. It checks installed
metadata/imports, CLI/module CLI, memory/export and four offline examples.
OpenAI/Anthropic/Redis are absent in all four environments; FastAPI/Uvicorn are
present only with `[server]`. Server health/auth/generation tests invoke the ASGI
app in-process without httpx. Runtime connections and DNS are blocked. On Windows,
only asyncio's private loopback socket pair is permitted, with ordinary socket
connections still blocked. Dependency downloads are the only external requests.

## 2. Set up your own TestPyPI account

1. Open [TestPyPI registration](https://test.pypi.org/account/register/) and create
   a separate account with a unique password. A PyPI account does not create a
   TestPyPI account. Verify the email using the message TestPyPI sends.
2. In [TestPyPI account settings](https://test.pypi.org/manage/account/), configure
   two-factor authentication using an authenticator or an existing security key.
   Save recovery codes privately in your password manager or secure offline
   storage. Never paste them into chat, source files or terminal commands.
3. Check the [TestPyPI project page](https://test.pypi.org/project/agentforge-coding/).
   If it exists, confirm that your account owns it or has publishing rights.
   If it is absent, the first successful upload creates the project. Absence does
   not guarantee that the name is allowed or reserve it for you.

On 2026-10-12, public JSON queries for agentforge-coding returned 404 on both
TestPyPI and PyPI. Ownership has not been established. TestPyPI data may be pruned;
its names and accounts are separate from production PyPI.

See [PyPA's TestPyPI guide](https://packaging.python.org/en/latest/guides/using-testpypi/)
and [TestPyPI two-factor guidance](https://test.pypi.org/help/#twofa).

## 3. Use secure TestPyPI authentication

In TestPyPI account settings, select **Add API token**. Use a descriptive name
such as `agentforge-coding-initial-test-release`. If the project already exists,
scope the token to agentforge-coding. For an initial upload that creates a project,
use a temporary account-wide token; revoke it after the first upload and create a
project-scoped token for subsequent uploads.

Store the token privately in a password manager. It is a **TestPyPI** token, not a
production PyPI token, account password, 2FA code or AI provider key. For token
authentication, the username is `__token__`; paste the complete token only at
Twine's hidden password/token prompt. Do not supply `--password`, echo the token,
put it in shell history, `.env`, `.pypirc`, source or CI logs, or send it here.

The command in step 4 clears inherited Twine authentication settings, uses an
empty config file and disables keyring lookup so it prompts for your TestPyPI
token. No token is stored in the command or environment. Twine's password input
does not display characters. Use a private terminal without screen recording.

For future automated releases, TestPyPI Trusted Publishing can replace stored
tokens with short-lived OIDC credentials. This repository has no publishing
workflow or registry credentials configured by this preparation task.

See [TestPyPI token guidance](https://test.pypi.org/help/#apitoken) and
[Twine authentication and options](https://twine.readthedocs.io/en/stable/).

## 4. Future upload — do not execute during preparation

**Only after explicit approval to publish to TestPyPI**, run in your own terminal:

```bash
cd /Users/AbdulRafe/agentforge
env -u TWINE_PASSWORD -u TWINE_USERNAME -u TWINE_REPOSITORY_URL \
  -u TWINE_NON_INTERACTIVE \
  PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring \
  .venv/bin/python -m twine upload \
  --config-file /dev/null \
  --repository-url https://test.pypi.org/legacy/ \
  --username __token__ \
  dist/agentforge_coding-0.1.0-py3-none-any.whl \
  dist/agentforge_coding-0.1.0.tar.gz
```

Paste the TestPyPI API token at the hidden prompt. Confirm the output targets
`https://test.pypi.org/legacy/`. Check the project page and its 0.1.0 file list,
README rendering, metadata and file SHA256 hashes. Public indexing can take a
minute or two. Revoke the temporary account-wide token after both uploads succeed.

If an upload partially succeeds, review TestPyPI's file list and upload only the
missing reviewed file. Uploaded filenames cannot be reused to replace release
bytes; corrected published releases need a new version. Never automatically
delete a project or use `--skip-existing` to hide an unexpected collision.

## 5. Fresh TestPyPI installation, after upload

Use a new directory outside checkout. Install dependencies explicitly from PyPI,
then install only agentforge-coding from TestPyPI with `--no-deps`. This avoids
mixing indexes with `--extra-index-url`, which pip warns can cause dependency
confusion. The package is public, so installation needs no upload token.

```bash
verify_dir="$(mktemp -d -t agentforge-testpypi)"
cd "$verify_dir"
python3 -m venv .venv
source .venv/bin/activate
unset OPENAI_API_KEY OPENAI_ADMIN_KEY ANTHROPIC_API_KEY REDIS_URL AGENTFORGE_SERVER_TOKEN
unset PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_FIND_LINKS PIP_NO_INDEX
export PIP_CONFIG_FILE=/dev/null
python -m pip install --index-url https://pypi.org/simple/ \
  'pydantic>=2,<3' 'typer>=0.12,<1' 'platformdirs>=4,<5' \
  'filelock>=3,<4' 'pathspec>=0.12,<1'
python -m pip install --index-url https://test.pypi.org/simple/ \
  --no-deps --no-cache-dir --only-binary=:all: 'agentforge-coding==0.1.0'
python -m pip check
python -I /Users/AbdulRafe/agentforge/scripts/check_installed.py agentforge-coding 0.1.0
agentforge --help
agentforge run --provider fake --model fake --task 'Create a greeting fixture' --json
```

Expected: metadata/version 0.1.0 and import from this environment's site-packages,
`pip check` with no conflicts, installed checks pass, and CLI JSON has
`"success": true`. OpenAI/Anthropic/Redis and server dependencies should be absent.

Then verify the same TestPyPI wheel with the server extra:

```bash
python -m pip install --index-url https://pypi.org/simple/ \
  'fastapi>=0.115,<1' 'uvicorn>=0.34,<1'
python -m pip install --index-url https://test.pypi.org/simple/ \
  --no-deps --no-cache-dir --only-binary=:all: --force-reinstall \
  'agentforge-coding[server]==0.1.0'
python -m pip check
python -I /Users/AbdulRafe/agentforge/scripts/check_installed.py agentforge-coding 0.1.0 --server
agentforge serve --help
```

Expected: server health 200, unauthenticated generation 401 and authenticated
FakeProvider generation 200; all checked in-process with network blocked. A
synthetic local service token is supplied internally by the script. No registry
token or provider credential is used. The authenticated server and JavaScript
demo are implemented; use [the server guide](server.md) for the optional loopback
demo, keeping `--provider fake --model fake` and `--no-memory`.

To test the TestPyPI sdist in another fresh environment, preinstall the same base
dependencies plus `setuptools>=77` and `wheel` from PyPI, then replace the wheel
installation command with:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ \
  --no-deps --no-build-isolation --no-cache-dir \
  --no-binary=agentforge-coding 'agentforge-coding==0.1.0'
```

Repeat the base installed checks there. See
[pip's index guidance](https://pip.pypa.io/en/stable/cli/pip_install/#examples).
Local wheel/sdist checks were executed during preparation. Registry download and
installation checks remain pending until an authorized TestPyPI upload exists.

## Later production publication

Production PyPI needs its own account/project rights and separate credentials or
Trusted Publishing configuration, plus separate explicit publication approval.
Publishing on TestPyPI does not reserve a production name. The unrelated
[PyPI agentforge](https://pypi.org/project/agentforge/) package is not this project.
Do not publish to production as part of this TestPyPI preparation.
