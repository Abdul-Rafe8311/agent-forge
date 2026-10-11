"""Fail-closed offline suite. No inherited provider/Redis/service credentials are used."""

import json
import os
import runpy
import socket
from pathlib import Path

import pytest

offline_socketpair = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/offline_socketpair.py")
)["socketpair"]


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_ADMIN_KEY",
        "REDIS_URL",
        "AGENTFORGE_SERVER_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError("Remote network is forbidden in offline tests")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, blocked)
    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, blocked)
    if os.name == "nt":
        monkeypatch.setattr(socket, "socketpair", offline_socketpair)


def generation(
    content: str = "answer = 42\n", path: str = "app.py", language: str = "python"
) -> str:
    return json.dumps(
        {
            "artifacts": [{"path": path, "language": language, "content": content}],
            "explanation": "Offline test fixture",
        }
    )


def plan(steps=None):
    return json.dumps(
        {
            "steps": steps
            or [
                {
                    "id": "build",
                    "title": "Build",
                    "instruction": "Implement",
                    "depends_on": [],
                    "kind": "execute",
                },
                {
                    "id": "integrate",
                    "title": "Integrate",
                    "instruction": "Combine",
                    "depends_on": ["build"],
                    "kind": "integrate",
                },
            ]
        }
    )
