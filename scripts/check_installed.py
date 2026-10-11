"""Isolated installed-package checks: no SDKs, credentials, or network."""

import importlib.util
import json
import os
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_ADMIN_KEY", "REDIS_URL"):
    os.environ.pop(key, None)


def blocked(*args, **kwargs):
    raise AssertionError("Network forbidden during runtime checks")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked

import agentforge  # noqa: E402
from agentforge.memory import LocalMemoryBackend  # noqa: E402

assert all(
    importlib.util.find_spec(name) is None
    for name in ("openai", "anthropic", "redis", "fastapi", "uvicorn")
)
assert Path(agentforge.__file__).parent.joinpath("py.typed").is_file()
with TemporaryDirectory() as directory:
    root = Path(directory).resolve()
    with agentforge.AgentWrapper(
        "fake",
        provider="fake",
        task_decompose=True,
        memory=True,
        memory_path=root / "memory",
        project_id="installed-check",
    ) as wrapper:
        result = wrapper.run("Create a greeting fixture")
    assert result.success and result.steps_taken == 2
    assert json.loads(json.dumps(result.to_dict()))["status"] == "success"
    result.write_to(root / "output")
    assert (root / "output" / "hello.py").is_file()
    assert LocalMemoryBackend(root / "memory").load("installed-check")
print("Installed runtime checks passed:", agentforge.__file__)
