# Downloadable API server

The Python wheel includes an optional self-hosted FastAPI/Uvicorn server, launched through agentforge serve. Python and a running process are required; no standalone binary, Docker image, hosted SaaS, npm SDK or multi-tenant service is supplied.

## Offline setup

```bash
python -m pip install -e ".[server]"
# Set AGENTFORGE_SERVER_TOKEN privately (a local test value suffices for the fake demo).
agentforge serve --provider fake --model fake --project-id demo
# Separate backend-only Node.js 18+ process with the same service token:
AGENTFORGE_URL=http://127.0.0.1:8000 node examples/javascript_client.mjs
```

Each accepted fake request gets a fresh script; output is an offline fixture, not real generation. Stop with Ctrl-C. A local loopback JavaScript request was verified during this build, then the server was stopped.

For the built wheel, replace the editable install with:
```bash
python -m pip install "dist/agentforge_coding-0.1.0-py3-none-any.whl[server]"
```

The public-package equivalent `pip install "agentforge-coding[server,redis,anthropic]"` is valid only after agentforge-coding has been published. The unrelated agentforge distribution must not be installed in its place. Python import and CLI names remain agentforge.

## Real operator configuration (not tested live)

```bash
python -m pip install -e ".[server,redis,anthropic]"
# Set ANTHROPIC_API_KEY, REDIS_URL, AGENTFORGE_SERVER_TOKEN,
# AGENTFORGE_MODEL, and AGENTFORGE_CONTEXT_LIMIT privately.
agentforge serve --provider anthropic --model "$AGENTFORGE_MODEL" --project-id my-website --memory --memory-backend redis --model-context-limit "$AGENTFORGE_CONTEXT_LIMIT"
```

Use the Upstash read/write rediss TCP/TLS URL. OpenAI uses the openai extra and OPENAI_API_KEY instead. Exact model availability/context must be verified by the operator. Live OpenAI and Anthropic connections were not tested. The user reported a separate live Redis memory smoke-test success; that does not verify a live server/provider integration. See the [verification report](verification.md).

Serve flags include host/port (127.0.0.1:8000 default), model/provider, fixed project-id, memory/backend, decomposition, repairs, token budget/context window/output cap, and optional fixed codebase path/context reads. Token and provider/Redis credentials are environment-only. Token validation happens before socket binding. CORS is off; an explicit operator origins allowlist is available via ServerConfig. No wildcard origins.

## HTTP contract

GET /health -> 200 `{"status":"ok","version":"0.1.0"}`, no model/Redis requests.

POST /generate requires `Authorization: Bearer <private service token>` and application/json:
```json
{"task":"Create a greeting module"}
```

Only task is accepted (nonblank, maximum 16000 characters). Maximum raw body is 65536 bytes, including chunked requests. All configuration overrides are forbidden. Authenticate precedes body parsing. Returns the complete AgentResult schema from api.md, including code, artifacts, attempts, diagnostics, usage and status.

| HTTP | Meaning |
| --- | --- |
| 200 | Completed run; inspect success/status, including validation/budget failures |
| 401 | Missing/invalid bearer; WWW-Authenticate: Bearer |
| 413 | Body exceeds byte cap |
| 415 | Media type is not application/json |
| 422 | Invalid task/schema/extra fields |
| 429 | server_busy; one generation already active |
| 500 | Sanitized pre-run/internal failure |

Error objects have code,message,request_id; no raw exceptions/credentials. Successful generation responses use Cache-Control: no-store. The service returns files as artifact JSON, without writing or executing them. No command validator/export/memory-clear endpoints exist.

Synchronous calls run in worker threads so health remains responsive. One process-local nonblocking guard admits a generation and rejects overlap. Fresh wrappers preserve owned cleanup and run-scoped ledgers. Guard stays held until the actual worker completes, even when a caller disconnects. An in-flight provider operation may still incur usage. Keep workers=1 and reload=False; additional processes would bypass the guard.

## JavaScript and Next.js

examples/javascript_client.mjs uses built-in fetch, private environment token, HTTP checks, and result success/status checks. Its URL defaults to http://127.0.0.1:8000. Run it only from an application backend.

A Next.js server route can forward an already authorized task:
```javascript
// app/api/generate/route.js — backend only
export async function POST(request) {
  // Implement your app's session authentication, project authorization and per-user quota checks here.
  // Reject unauthenticated/unauthorized requests before spending the private project's budget.
  const session = await authenticateAndAuthorizeYourUser(request);
  if (!session) return new Response("Unauthorized", { status: 401 });
  const { task } = await request.json();
  const upstream = await fetch(new URL("/generate", process.env.AGENTFORGE_URL), {
    method: "POST",
    headers: { "Content-Type": "application/json",
               Authorization: `Bearer ${process.env.AGENTFORGE_SERVER_TOKEN}` },
    body: JSON.stringify({ task }),
  });
  return Response.json(await upstream.json(), { status: upstream.status });
}
```

The illustration assumes your app provides authenticateAndAuthorizeYourUser; it is not an authentication implementation. Browser code calls its own authenticated backend. Never expose provider/service tokens through NEXT_PUBLIC variables. One service token authorizes access to the fixed project; separate customers/projects require separate instances or a future authenticated tenant design. Remote service access needs private authenticated networking and HTTPS termination.
