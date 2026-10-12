# Private Upstash Redis save/load check with FakeProvider

This is an opt-in test that writes one memory entry to a new UUID project key.
The agent's preparation and review did not connect to Upstash. The user subsequently
reported a successful live cycle with seven completed client command frames;
Upstash quota usage is unmeasured. Do not repeat that completed check during review.
Never reuse a credential pasted
into chat; rotate that credential in Upstash first and use the replacement below.
Do not change your database plan for this test.

The inspected backend requires the read/write **TCP/TLS** URL
`rediss://username:password@hostname:port`. HTTPS REST tokens/URLs and URL query
overrides are rejected. It uses `ssl_cert_reqs="required"`,
`ssl_check_hostname=True`, and 5-second connect/read timeouts. Do not disable TLS
verification to work around a connection error.

SDK retries are explicitly zero, periodic health checks are off, RESP2 is selected,
and optional CLIENT SETINFO metadata is disabled. The opt-in test additionally
allows one connection attempt per save/load backend and stops legacy AUTH fallback.
Development, debugging and automated checks use mocked Redis only, with remote
connections blocked. Do not use `--connect` for those checks.

## macOS Python 3.14 certificate trust repair

On this Mac, the virtual environment uses the python.org framework installation
at `/Library/Frameworks/Python.framework/Versions/3.14` and includes system site
packages. Its default `etc/openssl/cert.pem` and certificate directory were missing,
and `ssl.create_default_context()` loaded zero trusted CA certificates. Certifi
2026.7.22 was already installed with a readable bundle containing 121 CA roots.
Redis correctly required certificate and hostname verification; the missing
Python trust store was the diagnosed local configuration problem.

The missing default CA symlink was repaired offline using the existing Certifi
bundle. This is the trust-store link created by Python's supplied
`/Applications/Python 3.14/Install Certificates.command`, without that command's
dependency download or upgrade. [Python's macOS installation instructions](https://docs.python.org/3.14/using/mac.html)
describe the certificate installation step. No system Apple Python was changed.

Exact idempotent repair commands (already applied; writing under `/Library`
requires appropriate filesystem permission):

```zsh
env -u REDIS_URL -u SSL_CERT_FILE -u SSL_CERT_DIR \
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 - <<'PY'
import os
from pathlib import Path
import ssl
import certifi

bundle = Path(certifi.where()).resolve(strict=True)
assert ssl.create_default_context(cafile=str(bundle)).cert_store_stats()['x509_ca'] > 0
cafile = Path(ssl.get_default_verify_paths().openssl_cafile)
if cafile.is_symlink() and cafile.resolve() == bundle:
    print('Default CA link is already correct.')
elif cafile.exists() or cafile.is_symlink():
    raise SystemExit('Existing CA file requires review; no replacement performed.')
else:
    cafile.symlink_to(os.path.relpath(bundle, cafile.parent))
    print('Created the missing default CA link.')
context = ssl.create_default_context()
assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
assert context.cert_store_stats()['x509_ca'] > 0
print('Trusted CA certificates:', context.cert_store_stats()['x509_ca'])
PY
```

Verify from the virtual environment without opening a socket:

```zsh
cd /Users/AbdulRafe/agentforge
env -u REDIS_URL -u SSL_CERT_FILE -u SSL_CERT_DIR .venv/bin/python - <<'PY'
import ssl
context = ssl.create_default_context()
assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
assert context.cert_store_stats()['x509_ca'] > 0
print('Trusted CA certificates:', context.cert_store_stats()['x509_ca'])
print('Certificate and hostname verification enabled.')
PY
```

After repair, offline inspection verified both the virtual environment's default
SSL context and Redis's SSL context loaded 121 CA roots with verification enabled.
Redis's socket wrapping was mocked, and connections/DNS were blocked. No live TLS
handshake, Redis smoke retry or Upstash command was performed by the agent. The
user later reported a successful live save/reopen/load cycle. That user-reported
result is recorded in the [verification report](verification.md); no live check
will be repeated during review or automated tests.

## Command estimate and measurement

For the normal database-0 TCP/TLS URL and two successful connections:

| Phase | Expected Redis protocol commands |
| --- | --- |
| First connection | AUTH |
| One save transaction | MULTI, RPUSH, LTRIM, EXEC |
| Close/reopen connection | AUTH |
| One load | LRANGE |
| Total | 7 command frames: 5 data/transaction commands + 2 AUTH |

Closing the clients sends no Redis command. No empty-project pre-read, AgentWrapper
memory pre-read, PING, CLIENT SETINFO, scan, polling or deletion is performed. A
nonzero database URL would add SELECT on each connection; use your normal Upstash
database-0 URL. This estimate assumes successful sends; a failed connection may
send fewer commands, while a partially failed send has unknown delivery.

The mocked SDK transport observed exactly `AUTH, MULTI, RPUSH, LTRIM, EXEC, AUTH,
LRANGE`. This is a measured **mock** sequence, not evidence of live Upstash usage.
The test's local observer reports command names and counts only after a completed
client send, plus separate failed-send frames whose delivery is unknown. It does
not retain arguments, keys, payloads or credentials. A completed client send does
not prove server execution or the Free plan's metering total. No extra Redis or
dashboard request is made to obtain statistics.

[Upstash's public pricing FAQ](https://upstash.com/pricing/redis) says AUTH and
other operational commands are not charged. That statement does not establish
the measured Free-plan quota increment for this test. The user's successful live
check reported seven completed client frames, without a per-command transcript.
The expected/mock sequence above is not independently observed live telemetry.
Upstash dashboard usage and quota accounting remain unmeasured.

## 1. Install from this checkout

The distribution has not been published; install its Redis extra locally:

```zsh
cd /Users/AbdulRafe/agentforge
# Only needed if this checkout has no virtual environment:
# python3 -m venv .venv
.venv/bin/python -m pip install -e '.[redis]'
```

## 2. Enter the rotated URL privately in your own terminal

These commands target macOS/zsh. Use a private terminal without screen recording.
The `read -s` prompt hides input and does not put the pasted URL in shell history.
Never paste it into a command assignment, `.env`, chat, source or `.pypirc`.

```zsh
set +x
unset OPENAI_API_KEY OPENAI_ADMIN_KEY ANTHROPIC_API_KEY
unset REDIS_URL
read -rs 'REDIS_URL?Paste rotated Upstash read/write rediss:// URL (hidden): '
printf '\n'
export REDIS_URL
```

Paste the complete replacement TCP/TLS URL at that prompt. Do not run `echo`,
`env`, `printenv`, `set`, shell tracing or credential-bearing diagnostic commands
afterward. The environment variable is only for this terminal session and its
child process. Do not share that terminal with untrusted processes.

## 3. Run the opt-in test and unset the URL

```zsh
.venv/bin/python examples/redis_memory_smoke.py --connect
unset REDIS_URL
```

Run `unset REDIS_URL` even if the test fails or is interrupted. Closing this
terminal also discards its environment. The Python script removes the URL from
its child environment after reading it, never displays it, and suppresses error
details and exception chains that might contain credentials.

The script first prints its estimate. On success, output includes `PASS`, a
nonsecret project ID such as `agentforge-upstash-smoke-<UUID>` and observed command
counts. It runs FakeProvider locally with memory disabled, converts the result to
one standard memory entry, appends that entry, closes the backend, and loads once
through a new Redis connection. It checks task, session, project, success and
artifacts. No real model client is constructed. The UUID avoids shared project
keys without spending a command on an empty-project check.

Redis commands are limited to the unique test key under
`agentforge:v1:memory:<project hash>`: bounded LRANGE reads and a transactional
RPUSH/LTRIM write. Closing connections is not data deletion. The test retains one
small record; it issues no DELETE, FLUSHDB, FLUSHALL, SCAN or unrelated-key command.
No plan changes, cleanup commands or automatic retry loops are included. A failed
save stops before reopening/loading; a failed load is not repeated. An ambiguous
save outcome may leave the single test record behind. Do not automatically rerun
the script after failure: report its sanitized error stage and command summary,
review the cause privately, and obtain explicit approval before another live attempt.

Without `--connect`, the script makes no connection and does not read REDIS_URL.
If it fails, check the replacement URL, read/write permissions, database status
and trusted certificate configuration privately. Do not share raw exceptions,
connection strings or debug logs.

Live AI calls remain untested and prohibited for this check. Preparing or testing
this script with mocked Redis clients does not verify your live Upstash database.
