import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from agentforge import AgentWrapper
from agentforge.config import AgentConfig
from agentforge.server import ServerConfig, create_app

TOKEN = "offline-test-token"
AUTH = {"Authorization": "Bearer " + TOKEN}


def config(**kwargs):
    return ServerConfig(AgentConfig("fake", project_id="demo"), TOKEN, **kwargs)


def test_health_auth_success_schema_and_fixed_project():
    app = create_app(config())
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "version": "0.1.0"}
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            response = client.post("/generate", json={"task": "demo"}, headers=headers)
            assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
            assert set(response.json()) == {"code", "message", "request_id"}
        result = client.post("/generate", json={"task": "demo"}, headers=AUTH)
        assert result.status_code == 200 and result.json()["success"]
        assert result.json()["project_id"] == "demo" and result.json()["artifacts"]


@pytest.mark.parametrize(
    "body",
    [
        {"task": " "},
        {"task": "x", "project_id": "other"},
        {"task": "x", "api_key": "mock"},
        {"task": "x", "model": "gpt-custom"},
        {"task": "x", "token_budget": 100},
        {"task": "x", "redis_url": "mock"},
        {"task": "x", "codebase_path": "/"},
        {"task": "x", "validator_command": ["anything"]},
    ],
)
def test_forbidden_overrides_or_invalid_tasks_do_not_invoke_factory(body):
    factory = Mock()
    app = create_app(config(), factory)
    with TestClient(app) as client:
        assert client.post("/generate", json=body, headers=AUTH).status_code == 422
    factory.assert_not_called()


def test_body_limit_and_media_type():
    app = create_app(config(max_body_bytes=64))
    with TestClient(app) as client:
        assert (
            client.post(
                "/generate", content="x", headers={**AUTH, "Content-Type": "text/plain"}
            ).status_code
            == 415
        )
        assert client.post("/generate", json={"task": "x" * 100}, headers=AUTH).status_code == 413


def test_chunked_body_cap_without_network():
    app = create_app(config(max_body_bytes=32))
    chunks = iter(
        [
            {"type": "http.request", "body": b"x" * 20, "more_body": True},
            {"type": "http.request", "body": b"x" * 20, "more_body": False},
        ]
    )
    output = []

    async def receive():
        return next(chunks)

    async def send(message):
        output.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/generate",
        "query_string": b"",
        "headers": [
            (b"authorization", ("Bearer " + TOKEN).encode()),
            (b"content-type", b"application/json"),
        ],
    }
    asyncio.run(app(scope, receive, send))
    assert output[0]["status"] == 413


def test_computation_failures_return_200_and_owned_wrapper_cleanup():
    conf = config()
    conf.agent.token_budget = 1
    factory = Mock(side_effect=lambda: AgentWrapper("fake", project_id="demo", token_budget=1))
    with TestClient(create_app(conf, factory)) as client:
        response = client.post("/generate", json={"task": "demo"}, headers=AUTH)
        assert response.status_code == 200 and response.json()["status"] == "budget_exceeded"


def test_busy_health_responsive_cleanup_and_no_early_release():
    started = threading.Event()
    release = threading.Event()
    closed = []

    class Slow(AgentWrapper):
        def run(self, task):
            started.set()
            release.wait(5)
            return super().run(task)

        def close(self):
            closed.append(True)
            super().close()

    app = create_app(config(), lambda: Slow("fake", project_id="demo"))
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/generate", json={"task": "demo"}, headers=AUTH)
        assert started.wait(2)
        try:
            assert client.get("/health").status_code == 200
            response = client.post("/generate", json={"task": "overlap"}, headers=AUTH)
            assert response.status_code == 429 and response.json()["code"] == "server_busy"
            assert app.state.generation_guard.locked() and not closed
        finally:
            release.set()
        assert pending.result().status_code == 200 and closed
        assert not app.state.generation_guard.locked()


def test_disconnect_cancellation_keeps_guard_until_worker_finishes():
    started = threading.Event()
    release = threading.Event()

    class Slow(AgentWrapper):
        def run(self, task):
            started.set()
            release.wait(5)
            return super().run(task)

    app = create_app(config(), lambda: Slow("fake", project_id="demo"))
    body = json.dumps({"task": "demo"}).encode()

    async def exercise():
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.sleep(10)
            return {"type": "http.disconnect"}

        async def send(message):
            pass

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/generate",
            "raw_path": b"/generate",
            "query_string": b"",
            "headers": [
                (b"authorization", ("Bearer " + TOKEN).encode()),
                (b"content-type", b"application/json"),
            ],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 100),
            "root_path": "",
        }
        task = asyncio.create_task(app(scope, receive, send))
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert app.state.generation_guard.locked()
        release.set()
        for _ in range(100):
            if not app.state.generation_guard.locked():
                break
            await asyncio.sleep(0.01)
        assert not app.state.generation_guard.locked()

    try:
        asyncio.run(exercise())
    finally:
        release.set()


def test_internal_failures_are_sanitized_and_factory_project_cannot_drift():
    def bad():
        raise RuntimeError("sk-secretmock123456")

    with TestClient(create_app(config(), bad)) as client:
        response = client.post("/generate", json={"task": "demo"}, headers=AUTH)
        assert response.status_code == 500 and "sk-" not in response.text
    with TestClient(
        create_app(config(), lambda: AgentWrapper("fake", project_id="other"))
    ) as client:
        assert client.post("/generate", json={"task": "demo"}, headers=AUTH).status_code == 500


def test_server_token_repr_and_origins():
    assert TOKEN not in repr(config())
    with pytest.raises(Exception):
        create_app(ServerConfig(AgentConfig("fake"), ""))
    with pytest.raises(Exception):
        create_app(config(origins=["*"]))
