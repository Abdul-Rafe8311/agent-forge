# Installation, builds and future publication

This task builds distributions locally and pushes source to the existing GitHub repository. It does not upload packages.

Editable installation links a checkout: `python -m pip install -e ".[dev,all]"`.
A wheel installs packaged code: `python -m pip install dist/agentforge-0.1.0-py3-none-any.whl`.
Source distribution installs use `python -m pip install dist/agentforge-0.1.0.tar.gz`.
Server wheel example: `python -m pip install "dist/agentforge-0.1.0-py3-none-any.whl[server]"`.

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agentforge
python -m build
python -m twine check dist/*
python scripts/check_distribution.py
```

The verification script creates fresh base environments outside the checkout, downloads only base dependencies/build tooling, asserts optional SDK/Redis/server packages are absent, checks installed runtime/CLI/module CLI, memory, export, and offline examples. Runtime network is blocked in check_installed.py. Distribution artifacts and environments stay ignored locally.

Metadata uses setuptools/PEP 621, Python >=3.11, MIT LICENSE, typed marker py.typed, and only agentforge import packages. Sdist includes documentation/examples/tests/CI; wheels contain package source and metadata. Version consistency and all-extra composition are tested.

## Name ownership and future maintainer actions

[PyPI agentforge](https://pypi.org/project/agentforge/) is already an unrelated project. This repository has not been published there, and account ownership was not verified. Publishing requires an owned distribution name; do not install the unrelated PyPI package expecting this implementation. Local metadata/import remain agentforge per the supplied prompt. Choose/authorize a distribution name separately; changing distribution name need not change Python import.

After name ownership, release review and explicit publication authorization, maintainers could use:
```bash
# Future actions only — NOT executed in this task.
python -m twine upload --repository testpypi dist/*
python -m twine upload dist/*
```

Prefer an appropriate publishing credential/trusted-publishing workflow configured by the owner. Never commit keys. Public `pip install "agentforge[server]"` examples are conditional on the correct owned package being published; they are not currently instructions for installing this checkout.
