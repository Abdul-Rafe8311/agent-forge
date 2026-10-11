import socket

import pytest
from conftest import offline_socketpair


def test_windows_socketpair_fallback_works_with_connections_blocked():
    first, second = offline_socketpair()
    try:
        first.sendall(b"offline")
        assert second.recv(7) == b"offline"
        assert first.getsockname()[0] == second.getsockname()[0] == "127.0.0.1"
        # The special pair must not change guards on these or any other sockets.
        for sock in (first, second):
            with pytest.raises(AssertionError, match="Remote network"):
                sock.connect(("127.0.0.1", 1))
            with pytest.raises(AssertionError, match="Remote network"):
                sock.connect_ex(("203.0.113.1", 443))
        with pytest.raises(AssertionError, match="Remote network"):
            socket.getaddrinfo("api.openai.com", 443)
        with pytest.raises(AssertionError, match="Remote network"):
            socket.create_connection(("203.0.113.1", 443))
    finally:
        first.close()
        second.close()


def test_offline_socketpair_rejects_non_stream_sockets():
    with pytest.raises(ValueError, match="local TCP"):
        offline_socketpair(type=socket.SOCK_DGRAM)
