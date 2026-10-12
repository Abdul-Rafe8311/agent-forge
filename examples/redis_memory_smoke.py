"""Opt-in Redis save/load check: FakeProvider only, one new project, no deletion.

Enter REDIS_URL privately, then run this file with --connect. Without that flag,
the script does not read credentials or create a Redis client. Error details and
tracebacks are intentionally withheld because SDK exceptions may contain secrets.
"""

import argparse
import os
import sys
from collections import Counter
from uuid import uuid4

from agentforge import AgentWrapper
from agentforge.memory import RedisMemoryBackend, make_memory_entry

_COMMANDS = {
    b"AUTH",
    b"MULTI",
    b"RPUSH",
    b"LTRIM",
    b"EXEC",
    b"LRANGE",
    b"SELECT",
    b"PING",
    b"CLIENT",
    b"HELLO",
    b"QUIT",
}


def command_names(packed):
    """Extract only allowlisted command verbs, never arguments or credentials."""
    data = b"".join(packed)
    offset = 0
    names = []
    while offset < len(data):
        end = data.index(b"\r\n", offset)
        if data[offset : offset + 1] != b"*":
            raise ValueError("Unknown command framing")
        arguments = int(data[offset + 1 : end])
        if arguments < 1:
            raise ValueError("Empty command")
        offset = end + 2
        for index in range(arguments):
            end = data.index(b"\r\n", offset)
            if data[offset : offset + 1] != b"$":
                raise ValueError("Unknown argument framing")
            length = int(data[offset + 1 : end])
            offset = end + 2
            if length < 0 or data[offset + length : offset + length + 2] != b"\r\n":
                raise ValueError("Invalid argument length")
            if index == 0:
                verb = data[offset : offset + length].upper()
                names.append(verb.decode("ascii") if verb in _COMMANDS else "OTHER")
            offset += length + 2
    return names


class CommandAudit:
    """Local send observations, not proof of execution or Upstash quota usage."""

    def __init__(self):
        self.completed = Counter()
        self.uncertain = Counter()
        self.unparsed_sends = 0
        self.stage = "local fixture generation"
        self.project_id = None

    def report(self):
        if self.project_id:
            print("Test project:", self.project_id)
        counts = ", ".join(f"{name}={count}" for name, count in sorted(self.completed.items()))
        print(
            f"Completed client sends: {counts or 'none'} ({sum(self.completed.values())} frames)."
        )
        if self.uncertain:
            counts = ", ".join(f"{name}={count}" for name, count in sorted(self.uncertain.items()))
            print("Failed-send frames with unknown delivery:", counts)
        if self.unparsed_sends:
            print("Unparsed sends (command count unknown):", self.unparsed_sends)
        print("Server execution and Upstash usage totals were not measured.")


def observed_backend(redis_url, audit):
    """Instrument the backend's lazy TLS connection without extra Redis requests."""

    class ObservedBackend(RedisMemoryBackend):
        def _get(self):
            first = self._client is None
            client = super()._get()
            if first:
                from redis.exceptions import (
                    AuthenticationError,
                    AuthenticationWrongNumberOfArgsError,
                    ConnectionError,
                )

                pool = client.connection_pool
                original = pool.connection_class
                attempted = False

                class ObservedConnection(original):
                    def _connect(self):
                        nonlocal attempted
                        if attempted:
                            raise ConnectionError("Redis connection reattempt disabled")
                        attempted = True
                        return super()._connect()

                    def read_response(self, *args, **kwargs):
                        try:
                            return super().read_response(*args, **kwargs)
                        except AuthenticationWrongNumberOfArgsError as error:
                            # Prevent redis-py's legacy AUTH fallback from making a second request.
                            raise AuthenticationError(
                                "Legacy authentication retry disabled"
                            ) from error

                    def send_packed_command(self, command, check_health=True):
                        # SDK command packers produce byte fragments; retain none in the audit.
                        fragments = [command] if isinstance(command, bytes) else list(command)
                        try:
                            names = command_names(fragments)
                        except (ValueError, TypeError):
                            names = []
                            audit.unparsed_sends += 1
                        try:
                            super().send_packed_command(fragments, check_health=check_health)
                        except BaseException:
                            audit.uncertain.update(names)
                            raise
                        audit.completed.update(names)

                pool.connection_class = ObservedConnection
                pool.max_connections = 1
            return client

    return ObservedBackend(redis_url)


def safe_error_category(error):
    """Classify known causes without rendering exception text or connection strings."""
    categories = {
        "AuthenticationError": "Redis authentication failed",
        "TimeoutError": "Redis connection, write or read timed out",
        "ConnectionError": "Redis connection failed",
        "SSLCertVerificationError": "TLS certificate verification failed",
        "SSLError": "TLS handshake failed",
        "ResponseError": "Redis rejected a command",
        "ConfigurationError": "Redis configuration or dependency is invalid",
    }
    category = "Memory save/load validation failed"
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        category = categories.get(type(error).__name__, category)
        error = error.__cause__ or error.__context__
    return category


def check_memory(redis_url, backend_factory=RedisMemoryBackend, audit=None):
    """Generate locally, append once, close/reopen, load once; never retry or pre-read."""
    project_id = "agentforge-upstash-smoke-" + uuid4().hex
    if audit:
        audit.project_id = project_id
    task = "Remember this FakeProvider memory smoke-test fixture."
    with AgentWrapper("fake", provider="fake", memory=False, project_id=project_id) as agent:
        result = agent.run(task)
    if not result.success:
        raise RuntimeError("FakeProvider run failed")
    entry = make_memory_entry(task, result)
    if audit:
        audit.stage = "save"
    backend = backend_factory(redis_url)
    saved = False
    try:
        backend.append(entry)
        saved = True
    finally:
        if audit and saved:
            audit.stage = "close saved connection"
        backend.close()

    if audit:
        audit.stage = "reopen and load"
    reader = backend_factory(redis_url)
    try:
        entries = reader.load(project_id, limit=1)
        if len(entries) != 1:
            raise RuntimeError("Expected exactly one persisted memory entry")
        saved = entries[0]
        if (
            saved.project_id != project_id
            or saved.session_id != result.session_id
            or saved.task != task
            or not saved.success
            or saved.artifacts != result.artifacts
        ):
            raise RuntimeError("Loaded memory differs from the saved run")
    finally:
        reader.close()
    return project_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Read/write the Redis database in REDIS_URL using verified TLS; no AI calls",
    )
    args = parser.parse_args(argv)
    if not args.connect:
        print("No connection made. Enter REDIS_URL privately and pass --connect to run.")
        return 0
    print("Estimated for database 0: MULTI, RPUSH, LTRIM, EXEC, LRANGE + 2 AUTH = 7 frames.")
    print("One save/load cycle; no pre-read, health polling or automatic retries.")
    for name in ("OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(name, None)
    redis_url = os.environ.pop("REDIS_URL", None)
    if not redis_url:
        print("REDIS_URL is missing. Enter it through a hidden terminal prompt.", file=sys.stderr)
        return 1
    audit = CommandAudit()
    try:
        check_memory(redis_url, lambda url: observed_backend(url, audit), audit)
    except KeyboardInterrupt:
        print("Memory test interrupted; no error details displayed.", file=sys.stderr)
        audit.report()
        return 130
    except Exception as error:
        print(
            f"STOP: {safe_error_category(error)} during {audit.stage}. "
            "Raw error details withheld. Do not retry before reviewing the failure.",
            file=sys.stderr,
        )
        audit.report()
        return 1
    print("PASS: FakeProvider memory saved and loaded through a fresh Redis connection.")
    print("One test entry retained; no data was deleted. No real AI requests were made.")
    audit.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
