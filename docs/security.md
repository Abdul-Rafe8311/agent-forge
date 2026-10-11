# Security and operational limits

Provider keys, Redis URL and service bearer token belong in private environment variables or secret stores. .env files, private keys, credential files, caches, local memory and generated artifacts are ignored. .env.example contains placeholders only. The library does not auto-load it. Diagnostics redact recognized patterns without promising complete secret detection. Applications must keep arbitrary task/artifact data private; generated code may itself contain sensitive content.

Codebase retrieval excludes hidden files, .env*, known secrets, binaries, caches, build output, memory and symlinks. It respects root/nested gitignore patterns and bounds depth, files and UTF-8 reads. Retrieved content and memory are untrusted prompt data, not authorized instructions. Selection is deterministic lexical retrieval, not semantic proof.

Default validation uses AST and schema/path checks without executing generated code. Explicit CommandValidator stages files and runs shell=False with a restricted environment, timeout, and bounded retained stdout/stderr. A subprocess is not a sandbox; code/tests can access files/network and spawn other processes. Only run such commands in an appropriate operator-managed isolation environment. Killing the direct process does not promise to contain descendants.

Artifact export rejects traversal, absolute/drive/UNC paths, reserved names, separator tricks, case/path collisions and pre-existing symlinks. Preflight precedes writes. Replacement is atomic per file; there is no multi-file transaction or guarantee against hostile concurrent filesystem mutation.

Local memory uses file locks, versioned JSON and atomic replacement, and refuses corrupt data without deletion. Failure entries preserve status and never promote failed code. Redis uses verified TLS, bounded retention, hashed namespaces and timeouts; project hashes organize memory, they are not access control.

The server defaults to loopback, required constant-time bearer authentication and no CORS. It is one project/owner per process, not multi-tenant security or billing. Clients cannot supply paths/project/keys/budgets. Deploy remote access through private authenticated HTTPS termination. Keep one worker/no reload for the process-local concurrency guard. Never place the token or model keys in browser bundles or NEXT_PUBLIC variables.

Disconnect does not prove an in-flight provider request is canceled/refunded. Capacity remains held until its worker finishes and accounts/persists outcomes. No HTTP export, code execution or memory-clear route exists. See server.md for body limits and error contracts.

All verification during this build blocks remote provider/Redis operations and removes inherited provider credentials. The only HTTP demo is local loopback with a non-provider test service token.
