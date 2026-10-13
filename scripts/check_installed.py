"""Isolated installed base/server checks: no SDKs, real credentials, or network."""

import importlib.metadata
import importlib.util
import json
import os
import runpy
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

offline_socketpair = runpy.run_path(str(Path(__file__).with_name("offline_socketpair.py")))[
    "socketpair"
]

for key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_ADMIN_KEY",
    "REDIS_URL",
    "AGENTFORGE_SERVER_TOKEN",
):
    os.environ.pop(key, None)


def blocked(*args, **kwargs):
    raise AssertionError("Network forbidden during runtime checks")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
if os.name == "nt":
    socket.socketpair = offline_socketpair

import agentforge  # noqa: E402
from agentforge.assist.packets import prepare  # noqa: E402
from agentforge.assist.planning import complete, final_review, task_for  # noqa: E402
from agentforge.assist.sessions import start, update_requirements  # noqa: E402
from agentforge.assist.skill_install import install  # noqa: E402
from agentforge.assist.validation import validate  # noqa: E402
from agentforge.memory import LocalMemoryBackend  # noqa: E402

distribution_name, expected_version = sys.argv[1:3]
server = "--server" in sys.argv[3:]
distribution = importlib.metadata.distribution(distribution_name)
assert distribution.metadata["Name"] == distribution_name
assert distribution.version == expected_version == agentforge.__version__
assert any(
    entry.name == "agentforge" and entry.value == "agentforge.cli:main"
    for entry in distribution.entry_points
)
assert (
    Path(agentforge.__file__).resolve()
    == Path(distribution.locate_file("agentforge/__init__.py")).resolve()
)
assert all(importlib.util.find_spec(name) is None for name in ("openai", "anthropic", "redis"))
assert all(
    (importlib.util.find_spec(name) is not None) == server for name in ("fastapi", "uvicorn")
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
    project = root / "assist-project"
    project.mkdir()
    (project / "answer.py").write_text("answer = 42\n", encoding="utf-8")
    prompt = root / "task.md"
    prompt.write_text("Retain answer = 42.\n", encoding="utf-8")
    session = start(project, prompt)
    with session.transaction() as state:
        requirements = state["requirements"]
        for requirement in requirements:
            requirement["clarification_status"] = "resolved"
        update_requirements(session, state, requirements)
        task = task_for(state, "task")
        packet = prepare(session, state, task)
        assert packet["status"] == "ready" and state["memory_backend"] == "local"
        assert validate(session, state, task, "syntax", files=["answer.py"])["status"] == "passed"
        assert (
            complete(
                session,
                state,
                task,
                {
                    "spec_hash": state["spec_hash"],
                    "plan_version": state["plan_version"],
                    "summary": "Offline installed fixture reviewed",
                    "changed_files": ["answer.py"],
                },
            )["status"]
            == "complete"
        )
        assert (
            final_review(session, state, reviewed=True, note="Original fixture reviewed")["status"]
            == "accepted"
        )
    destination = root / "skills" / "agentforge-coding"
    install(destination)
    assert (destination / "SKILL.md").is_file()
    assert (destination / "references" / "workflow.md").is_file()
    assert (destination / "agents" / "openai.yaml").is_file()
print("Installed runtime checks passed:", agentforge.__file__)
print("Installed local assist workflow and packaged skill checks passed.")

if server:
    import asyncio

    from agentforge.config import AgentConfig
    from agentforge.server import ServerConfig, create_app

    # Exercise the installed ASGI service in-process; httpx is not required by the server extra.
    app = create_app(
        ServerConfig(
            AgentConfig("fake", provider="fake", project_id="installed-server"),
            token="offline-test-service-token",
        )
    )

    async def request(path, body=b"", authorization=True):
        sent = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            sent.append(message)

        headers = [(b"content-type", b"application/json")]
        if authorization:
            headers.append((b"authorization", b"Bearer offline-test-service-token"))
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST" if path == "/generate" else "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": headers,
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive,
            send,
        )
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        payload = json.loads(
            b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        )
        return status, payload

    async def check_server():
        status, payload = await request("/health", authorization=False)
        assert status == 200 and payload["version"] == expected_version
        status, payload = await request("/generate", b'{"task":"demo"}', authorization=False)
        assert status == 401 and payload["code"] == "unauthorized"
        status, payload = await request("/generate", b'{"task":"demo"}')
        assert status == 200 and payload["success"] and payload["status"] == "success"
        assert payload["project_id"] == "installed-server"
        assert payload["artifacts"][0]["path"] == "hello.py"
        assert payload["warnings"]

    asyncio.run(check_server())
    print("Installed server-extra health/auth/FakeProvider checks passed.")
    print(
        "Server dependency versions:",
        ", ".join(
            name + "=" + importlib.metadata.version(name)
            for name in ("fastapi", "starlette", "uvicorn")
        ),
    )
