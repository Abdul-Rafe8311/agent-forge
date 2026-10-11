# Installation, builds and future publication

Source is hosted in the existing GitHub repository. Distributions are built locally; no package uploads have been performed.

Editable installation links a checkout: `python -m pip install -e ".[dev,all]"`.
A wheel installs packaged code: `python -m pip install dist/agentforge_coding-0.1.0-py3-none-any.whl`.
Source distribution installs use `python -m pip install dist/agentforge_coding-0.1.0.tar.gz`.
Server wheel example: `python -m pip install "dist/agentforge_coding-0.1.0-py3-none-any.whl[server]"`.

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agentforge
python -m build
python -m twine check dist/*
python scripts/check_distribution.py
```

The verification script derives artifact names from pyproject.toml and creates four fresh environments outside the checkout: wheel and sdist, each with base dependencies and with the server extra. It checks installed distribution metadata, import paths, the unchanged agentforge console command, CLI/module CLI, memory, export and offline examples. SDKs/Redis remain absent in all four environments; FastAPI/Uvicorn are present only in the server environments. Server checks invoke the installed ASGI app in-process with FakeProvider, covering health, authentication and generation without opening sockets or requiring httpx. Runtime network is blocked in check_installed.py. Distribution artifacts and environments stay ignored locally.

Metadata uses setuptools/PEP 621, Python >=3.11, MIT LICENSE, typed marker py.typed, and only agentforge import packages. Sdist includes documentation/examples/tests/CI; wheels contain package source and metadata. Version consistency and all-extra composition are tested.

## Name ownership and future maintainer actions

[PyPI agentforge](https://pypi.org/project/agentforge/) is already an unrelated project. This repository has not been published there, and account ownership was not verified. Publishing requires ownership of agentforge-coding; do not install the unrelated PyPI package expecting this implementation. The authorized distribution name is now agentforge-coding. Python import and console command remain agentforge. No PyPI ownership or name reservation is implied by local metadata.

After name ownership, release review and explicit publication authorization, maintainers could use:
```bash
# Future actions only — NOT executed in this task.
python -m twine upload --repository testpypi dist/*
python -m twine upload dist/*
```

Prefer an appropriate publishing credential/trusted-publishing workflow configured by the owner. Never commit keys. Public `pip install "agentforge-coding[server]"` examples are conditional on agentforge-coding being published; they are not currently instructions for installing this checkout.
