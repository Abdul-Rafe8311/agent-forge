// Backend-only Node.js 18+ example. Never ship the service token to browser code.
const base = process.env.AGENTFORGE_URL ?? "http://127.0.0.1:8000";
const token = process.env.AGENTFORGE_SERVER_TOKEN;
if (!base || !token) throw new Error("Set AGENTFORGE_URL and AGENTFORGE_SERVER_TOKEN privately");
const response = await fetch(new URL("/generate", base), {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ task: process.argv[2] ?? "Create a greeting module" }),
  signal: AbortSignal.timeout(120000),
});
const payload = await response.json();
if (!response.ok) throw new Error(`AgentForge HTTP ${response.status}: ${payload.code ?? "error"}`);
if (payload.success !== true || payload.status !== "success")
  throw new Error(`AgentForge computation stopped: ${payload.status}`);
if (!Array.isArray(payload.artifacts) || payload.artifacts.length === 0)
  throw new Error("AgentForge response has no artifacts");
console.log(JSON.stringify(payload, null, 2));
