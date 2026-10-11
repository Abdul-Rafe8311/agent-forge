import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from unittest.mock import MagicMock, Mock, patch

import pytest

from agentforge import AgentWrapper
from agentforge.exceptions import MemoryBackendError
from agentforge.memory import (
    LocalMemoryBackend,
    RedisMemoryBackend,
    build_memory_context,
    make_memory_entry,
)
from agentforge.types import AgentResult, CodeArtifact


def entry(task="fixture", project="p", max_bytes=262144):
    return make_memory_entry(
        task,
        AgentResult(
            project_id=project,
            session_id="session",
            success=True,
            artifacts=[CodeArtifact("app.py", "answer=42")],
        ),
        max_bytes,
    )


def test_local_persistence_project_isolation_clear_and_concurrent_writers(tmp_path):
    backend = LocalMemoryBackend(tmp_path, retention=10)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: backend.append(entry(str(i))), range(8)))
    fresh = LocalMemoryBackend(tmp_path)
    assert len(fresh.load("p")) == 8 and fresh.load("other") == []
    fresh.append(entry(project="other"))
    fresh.clear("p")
    assert fresh.load("p") == [] and fresh.load("other")


def test_corruption_is_not_silently_erased(tmp_path):
    backend = LocalMemoryBackend(tmp_path)
    path = backend._path("p")
    path.write_text("bad")
    with pytest.raises(MemoryBackendError):
        backend.load("p")
    with pytest.raises(MemoryBackendError):
        backend.append(entry())
    assert path.read_text() == "bad"


def test_retention_and_bounded_complete_artifacts(tmp_path):
    backend = LocalMemoryBackend(tmp_path, retention=2)
    for i in range(3):
        backend.append(entry(str(i)))
    assert [e.task for e in backend.load("p")] == ["1", "2"]
    result = AgentResult(
        project_id="p",
        session_id="s",
        success=True,
        artifacts=[CodeArtifact("large.py", "x" * 10000)],
    )
    bounded = make_memory_entry("large", result, 512)
    assert len(json.dumps(asdict(bounded)).encode()) <= 512
    assert bounded.artifacts == [] and "omitted" in bounded.summary


def test_memory_context_is_bounded_and_failure_code_not_established():
    failed = make_memory_entry(
        "failed",
        AgentResult(
            project_id="p", success=False, artifacts=[CodeArtifact("bad.py", "PRIVATE_BAD_CODE")]
        ),
    )
    context = build_memory_context([entry(), failed], "failed", 4000)
    assert "PRIVATE_BAD_CODE" not in context
    assert build_memory_context([entry()], "fixture", 1) == ""


def test_mocked_redis_tls_timeouts_transaction_and_borrowed_cleanup():
    client = MagicMock()
    client.lrange.return_value = []
    url = "rediss://mock:mock@example.com:6379"
    with patch("redis.Redis.from_url", return_value=client) as factory:
        backend = RedisMemoryBackend(url)
        factory.assert_not_called()
        backend.load("p")
        backend.append(entry())
        backend.close()
    options = factory.call_args.kwargs
    assert options["ssl_cert_reqs"] == "required" and options["ssl_check_hostname"]
    assert options["socket_connect_timeout"] > 0 and options["socket_timeout"] > 0
    pipe = client.pipeline.return_value.__enter__.return_value
    pipe.rpush.assert_called_once()
    pipe.ltrim.assert_called_once()
    pipe.execute.assert_called_once()
    borrowed = RedisMemoryBackend(client=client)
    client.close.reset_mock()
    borrowed.close()
    client.close.assert_not_called()


def test_mocked_redis_does_not_leak_url_on_failure():
    client = Mock()
    client.lrange.side_effect = RuntimeError("rediss://secret:secret@example.com:6379")
    with pytest.raises(MemoryBackendError) as caught:
        RedisMemoryBackend(client=client).load("p")
    assert "secret" not in str(caught.value)


def test_wrapper_memory_survives_new_instances(tmp_path):
    with AgentWrapper("fake", memory=True, memory_path=tmp_path, project_id="p") as first:
        assert first.run("remember task").success
    with AgentWrapper("fake", memory=True, memory_path=tmp_path, project_id="p") as second:
        assert second.run("continue").success
        assert "remember task" in second.primary.requests[0].messages[1].content
