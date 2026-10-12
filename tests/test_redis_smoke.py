"""Redis smoke checks use a fake socket transport; no database is contacted."""

import runpy
import socket
import ssl
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import pytest
from redis.connection import SSLConnection

SCRIPT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "examples/redis_memory_smoke.py"))
URL = "rediss://mock:private-placeholder@example.invalid:6379"


def unpack(data):
    """Decode mock transport frames locally; no arguments are printed or logged."""
    offset = 0
    commands = []
    while offset < len(data):
        end = data.index(b"\r\n", offset)
        count = int(data[offset + 1 : end])
        offset = end + 2
        args = []
        for _ in range(count):
            end = data.index(b"\r\n", offset)
            length = int(data[offset + 1 : end])
            offset = end + 2
            args.append(data[offset : offset + length])
            offset += length + 2
        commands.append(args)
    return commands


class MockRedisSocket:
    def __init__(self, data, events, legacy_auth_error=False):
        self.data = data
        self.events = events
        self.replies = bytearray()
        self.legacy_auth_error = legacy_auth_error
        self.closed = False

    def sendall(self, payload):
        for args in unpack(payload):
            name = args[0].decode()
            self.events.append(name)
            if name == "AUTH":
                self.replies += (
                    b"-ERR wrong number of arguments for 'auth' command\r\n"
                    if self.legacy_auth_error
                    else b"+OK\r\n"
                )
            elif name == "MULTI":
                self.replies += b"+OK\r\n"
            elif name == "RPUSH":
                self.data.setdefault(args[1], []).append(args[2])
                self.replies += b"+QUEUED\r\n"
            elif name == "LTRIM":
                self.data[args[1]] = self.data[args[1]][int(args[2]) :]
                self.replies += b"+QUEUED\r\n"
            elif name == "EXEC":
                self.replies += b"*2\r\n:1\r\n+OK\r\n"
            elif name == "LRANGE":
                values = self.data.get(args[1], [])[int(args[2]) :]
                self.replies += b"*" + str(len(values)).encode() + b"\r\n"
                for value in values:
                    self.replies += b"$" + str(len(value)).encode() + b"\r\n" + value + b"\r\n"
            else:
                raise AssertionError("Unexpected Redis command")

    def recv(self, size):
        if not self.replies:
            raise socket.timeout("No mock response available")
        reply = bytes(self.replies[:size])
        del self.replies[:size]
        return reply

    def gettimeout(self):
        return 5

    def settimeout(self, timeout):
        pass

    def shutdown(self, how):
        pass

    def close(self):
        self.closed = True


def mock_transport(monkeypatch, legacy_auth_error=False):
    data, events, sockets, connections = {}, [], [], []

    def connect(connection):
        connections.append(connection)
        sock = MockRedisSocket(data, events, legacy_auth_error)
        sockets.append(sock)
        return sock

    monkeypatch.setattr(SSLConnection, "_connect", connect)
    return data, events, sockets, connections


def test_one_save_reopen_load_and_measured_mock_frames(monkeypatch, capsys):
    data, events, sockets, connections = mock_transport(monkeypatch)
    audit = SCRIPT["CommandAudit"]()
    project = SCRIPT["check_memory"](URL, lambda url: SCRIPT["observed_backend"](url, audit), audit)
    assert events == ["AUTH", "MULTI", "RPUSH", "LTRIM", "EXEC", "AUTH", "LRANGE"]
    assert audit.completed == Counter(events) and not audit.uncertain
    assert len(data) == 1 and len(next(iter(data.values()))) == 1
    assert project.startswith("agentforge-upstash-smoke-")
    assert len(sockets) == 2 and all(sock.closed for sock in sockets)
    for connection in connections:
        assert connection.cert_reqs == ssl.CERT_REQUIRED and connection.check_hostname
        assert connection.retry.get_retries() == 0
        assert connection.health_check_interval == 0
        assert connection.driver_info is None and connection.protocol == 2
    audit.report()
    output = capsys.readouterr().out
    assert "7 frames" in output and "usage totals were not measured" in output
    assert "private-placeholder" not in output and URL not in output


def test_failed_save_stops_before_reopen_and_reports_error(monkeypatch, capsys):
    calls = []
    backend = Mock()
    backend.append.side_effect = RuntimeError("PRIVATE_DIAGNOSTIC")

    def factory(url, audit):
        calls.append(url)
        return backend

    monkeypatch.setitem(SCRIPT["main"].__globals__, "observed_backend", factory)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"](["--connect"]) == 1
    assert len(calls) == 1
    backend.append.assert_called_once()
    backend.load.assert_not_called()
    backend.close.assert_called_once()
    output = capsys.readouterr()
    assert "STOP:" in output.err and "during save" in output.err
    assert "Do not retry" in output.err
    assert "PRIVATE_DIAGNOSTIC" not in output.err and URL not in output.err


def test_failed_auth_does_not_repeat_or_load(monkeypatch, capsys):
    data, events, sockets, connections = mock_transport(monkeypatch, legacy_auth_error=True)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"](["--connect"]) == 1
    assert events == ["AUTH"] and not data
    assert len(connections) == 1 and all(sock.closed for sock in sockets)
    assert "authentication failed" in capsys.readouterr().err


def test_connection_failure_is_one_attempt_with_no_sends(monkeypatch, capsys):
    from redis.exceptions import ConnectionError

    connect = Mock(side_effect=ConnectionError("PRIVATE_CONNECTION_DIAGNOSTIC"))
    monkeypatch.setattr(SSLConnection, "_connect", connect)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"](["--connect"]) == 1
    connect.assert_called_once()
    output = capsys.readouterr()
    assert "0 frames" in output.out and "connection failed" in output.err
    assert "PRIVATE_CONNECTION_DIAGNOSTIC" not in output.err


def test_no_connect_flag_never_constructs_client(monkeypatch, capsys):
    factory = Mock(side_effect=AssertionError("Unexpected client construction"))
    monkeypatch.setitem(SCRIPT["main"].__globals__, "observed_backend", factory)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"]([]) == 0
    factory.assert_not_called()
    assert "No connection made" in capsys.readouterr().out


def test_failed_load_stops_without_retry(monkeypatch, capsys):
    data, events, sockets, connections = mock_transport(monkeypatch)
    original = MockRedisSocket.recv

    def recv(sock, size):
        if events and events[-1] == "LRANGE":
            raise socket.timeout("PRIVATE_TIMEOUT_DIAGNOSTIC")
        return original(sock, size)

    monkeypatch.setattr(MockRedisSocket, "recv", recv)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"](["--connect"]) == 1
    assert events == ["AUTH", "MULTI", "RPUSH", "LTRIM", "EXEC", "AUTH", "LRANGE"]
    assert len(connections) == 2 and all(sock.closed for sock in sockets)
    assert len(data) == 1
    output = capsys.readouterr()
    assert "timed out" in output.err and "7 frames" in output.out
    assert "PRIVATE_TIMEOUT_DIAGNOSTIC" not in output.err


def test_failed_write_reports_unknown_delivery_without_retry(monkeypatch, capsys):
    data, events, sockets, connections = mock_transport(monkeypatch)
    original = MockRedisSocket.sendall

    def sendall(sock, payload):
        if unpack(payload)[0][0] == b"MULTI":
            raise socket.timeout("PRIVATE_WRITE_DIAGNOSTIC")
        return original(sock, payload)

    monkeypatch.setattr(MockRedisSocket, "sendall", sendall)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"](["--connect"]) == 1
    assert events == ["AUTH"] and not data
    assert len(connections) == 1 and all(sock.closed for sock in sockets)
    output = capsys.readouterr()
    assert "1 frames" in output.out and "unknown delivery" in output.out
    assert "EXEC=1" in output.out and "LRANGE" not in output.out.split("Failed-send")[1]
    assert "PRIVATE_WRITE_DIAGNOSTIC" not in output.err


def test_pool_reconnect_fallback_cannot_make_another_attempt(monkeypatch, capsys):
    from redis.exceptions import ConnectionError

    data, events, sockets, connections = mock_transport(monkeypatch)
    original = MockRedisSocket.recv

    def recv(sock, size):
        if not sock.replies:
            raise ConnectionError("PRIVATE_SOCKET_DIAGNOSTIC")
        return original(sock, size)

    monkeypatch.setattr(MockRedisSocket, "recv", recv)
    monkeypatch.setenv("REDIS_URL", URL)
    assert SCRIPT["main"](["--connect"]) == 1
    assert len(connections) == 1 and events == ["AUTH"] and not data
    assert all(sock.closed for sock in sockets)
    assert "PRIVATE_SOCKET_DIAGNOSTIC" not in capsys.readouterr().err


def test_audit_parser_never_exposes_arguments_or_unknown_verbs():
    assert SCRIPT["command_names"]([b"*2\r\n$4\r\nAUTH\r\n$6\r\nsecret\r\n"]) == ["AUTH"]
    assert SCRIPT["command_names"]([b"*1\r\n$6\r\nsecret\r\n"]) == ["OTHER"]
    with pytest.raises(ValueError):
        SCRIPT["command_names"]([b"not RESP"])


def test_remote_network_is_still_blocked():
    with pytest.raises(AssertionError, match="Remote network"):
        socket.create_connection(("203.0.113.1", 6379))
