"""Windows asyncio wakeup sockets, without relaxing the offline connection guard."""

import socket

_connect = socket.socket.connect


def socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
    """Create only a connected loopback pair; never accept a caller-supplied address.

    Windows' stdlib fallback calls the patched socket.connect method. Retain the
    original method solely for connecting this function's own two local sockets.
    Other connect/connect_ex calls and DNS remain blocked, even in other threads.
    """
    if family not in (socket.AF_INET, socket.AF_INET6) or type != socket.SOCK_STREAM or proto:
        raise ValueError("Offline socketpair supports only local TCP stream pairs")
    host = "127.0.0.1" if family == socket.AF_INET else "::1"
    client = socket.socket(family, type, proto)
    server = None
    try:
        with socket.socket(family, type, proto) as listener:
            listener.bind((host, 0))
            listener.listen(1)
            listener.settimeout(5)
            client.settimeout(5)
            _connect(client, listener.getsockname())
            server, peer = listener.accept()
            if peer != client.getsockname():
                raise AssertionError("Unexpected peer in offline socketpair")
        client.settimeout(None)
        server.settimeout(None)
        return server, client
    except BaseException:
        client.close()
        if server is not None:
            server.close()
        raise
