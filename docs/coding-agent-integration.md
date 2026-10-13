# Coding-agent helpers

Implemented for an explicitly invoked Codex skill and a local terminal CLI. Helpers
never instantiate a model provider or run Codex. The existing framework and optional
server remain available. Local memory is the default; Redis is an explicit optional
backend and is mocked in automated checks.

## Installation and invocation

From this checkout on this Mac:

```bash
cd /Users/AbdulRafe/agentforge
.venv/bin/python -m pip install -e .
.venv/bin/agentforge assist --help
```

Codex opened in this repository can discover the shipped repository skill at
`.agents/skills/agentforge-coding/SKILL.md`. Explicit invocation:

```text
$agentforge-coding Implement my request using local memory, focused context,
acceptance checks, and a final review against the original specification.
```

For another repository, use its absolute path:

```bash
/Users/AbdulRafe/agentforge/.venv/bin/agentforge assist install-skill \
  --destination /absolute/project/.agents/skills/agentforge-coding
```

For user scope instead:

```bash
/Users/AbdulRafe/agentforge/.venv/bin/agentforge assist install-skill \
  --destination "$HOME/.agents/skills/agentforge-coding"
```

Reopen Codex in the target project after copying the skill. Keep the environment's
`agentforge` executable on PATH (activate its virtual environment), or supply the
absolute executable path to Codex. Installation copies three packaged skill files;
it does not change Codex settings, add MCP, launch an agent or overwrite a different
custom skill by default. Identical installs are idempotent. After inspecting an
existing AgentForge installation, `--replace-existing` explicitly upgrades only
packaged skill files while preserving unrelated files and rejecting symlinks. Invocation is explicit through
`policy.allow_implicit_invocation: false`.

## Local workflow

Use a supplied task prompt file exactly. Otherwise write the complete original
user request to a private UTF-8 file, without shortening or duplicating it. Keep
additional approved execution criteria in a separate amendment. Avoid credential values; reference private configuration instead. Global options
`--project` and `--session` must precede the subcommand. Replace ROOT, PROMPT and
SESSION below with actual values; start returns the session ID in JSON.

In the target repository, ensure `.gitignore` includes `.agentforge/` before starting.
This checkout already includes the exclusion. The helper does not rewrite another
project's ignore policy.

```bash
agentforge assist --project ROOT start --prompt-file PROMPT
agentforge assist --project ROOT --session SESSION requirements
agentforge assist --project ROOT --session SESSION read-spec
```

The deterministic requirement scaffold preserves source spans for every nonblank
paragraph/list item. It does not reliably infer meaning, shared scope, ambiguity or
acceptance criteria. Codex reviews these using its own model/allowance. Export a
private JSON list, refine category/scope/interpretation/check mappings, then submit:

```bash
agentforge assist --project ROOT --session SESSION requirements --file REQUIREMENTS.json --reviewed
```

`requirements --reviewed` without a file attests review of the current scaffold.
Mutation replies contain concise hashes/versions/counts rather than repeating the
whole registry; add `--show-records` when those records are needed. Plain
`requirements` and `plan-check` remain read commands. Use the new spec hash after
registry changes; installing a plan returns ordered IDs and the current version.
Schema errors identify safe field locations while withholding input values.
Never mark unresolved ambiguity resolved just to pass a check. Shared constraints
use `scope: all_tasks`. Derived interpretations are labelled and original source
references remain accessible. `requirements --offset N` pages by requirement;
`read-spec --offset N` pages by character. Follow `next_offset` until null and check
`truncated`; one response is not necessarily the entire specification.

Inspect exact JSON schemas:

```bash
agentforge assist schema --kind requirement
agentforge assist schema --kind plan
agentforge assist schema --kind check
agentforge assist schema --kind completion
agentforge assist schema --kind limits
```

A session starts with one unsplit task ID `task`. For larger work, Codex proposes a
plan using the current `spec_hash`. Tasks specify objective, requirement IDs, code
queries/file ranges, dependencies, acceptance check IDs, input/output contracts and
context unknowns. Split plans allow up to eight implementation tasks and one final
`integrate` task depending on every implementation task. Label human/agent planning
honestly as `explicit_sections` or `agent_model`; no separate helper model is used.
There is no automatic semantic splitting of arbitrary long prose.

Register a check catalog before installing a plan that references those checks.
Command checks need explicit argv, source-file scope and catalog approval. For example:

```json
[
  {"id":"syntax","kind":"syntax","files":["src/app.py"]},
  {"id":"behavior","kind":"command","argv":[".venv/bin/python","-m","pytest","tests/test_app.py"],"files":["src/app.py","tests/test_app.py"],"timeout_seconds":60}
]
```

```bash
agentforge assist --project ROOT --session SESSION checks --file CHECKS.json --approve-commands
agentforge assist --project ROOT --session SESSION plan-check --plan-file PLAN.json
agentforge assist --project ROOT --session SESSION plan-check
agentforge assist --project ROOT --session SESSION prepare --task task
agentforge assist --project ROOT --session SESSION search --query "affected symbol" --include-code
```

Planning validates coverage, registered checks and dependency order. It does not
prove that an agent's interpretation is complete. Do not repeat the whole original
in task cards. Keep requirements shared where appropriate, use concise interpretations
for long sections, and fetch authoritative sections when clarification is needed.

After Codex edits the actual repository, run authorized checks deliberately:

```bash
agentforge assist --project ROOT --session SESSION validate --task task --check syntax --file src/app.py
agentforge assist --project ROOT --session SESSION validate --task task --check behavior --execute
```

Command catalog approval alone does not run anything. `--execute` is required on
each execution. The subprocess has a sanitized environment, argv with no shell,
timeout and bounded diagnostics. Its selected source scope is hashed before/after;
it is not a security sandbox or network firewall. Use mocks and host sandbox/network
controls in test commands. Only explicitly scoped files are tracked for staleness:
include tests/configuration and other relevant dependencies in the catalog.
Syntax checks prove Python syntax, not semantics or behavior. Other languages need
configured commands or explicit manual checks. Manual checks use
`--manual-status passed|failed --note "Actual evidence"` and are labelled attested.

Write concise completion JSON (maximum 2 KiB) with current spec/plan identifiers:

```json
{"spec_hash":"CURRENT_HASH","plan_version":2,"summary":"Actual changes and checks","changed_files":["src/app.py"],"decisions":[],"next_task_implications":[],"unresolved_questions":[]}
```

```bash
agentforge assist --project ROOT --session SESSION complete --task task --summary-file HANDOFF.json
agentforge assist --project ROOT --session SESSION complete --task task --show
agentforge assist --project ROOT --session SESSION final-check
agentforge assist --project ROOT --session SESSION final-check --review-original --note "Full original specification and final state reviewed"
```

Completion requires reviewed requirements, completed predecessors and current passing
checks. Later edits can make earlier evidence stale; revalidate explicitly. Handoffs
provide concise decisions/interfaces and next-task implications, not code snapshots.
Final review reports requirement coverage/current evidence and requires an original
specification review attestation. `accepted` means those gates passed; it is not
independent proof of behavioral correctness. Full-original review is still required
for unsplit work. `amend --prompt-file FILE` adds a separate immutable amendment and
invalidates the previous plan/evidence/handoffs; it does not rewrite the original.

## Bounds and trust

| Default bound | Value |
| --- | --- |
| Complete packet, serialized JSON including newline | 20 KiB |
| Task instruction section / memory selection / code selection | 4 KiB / 2 KiB / 12 KiB |
| Source chunks | 6, at most 60 lines each |
| Examined filesystem entries / depth / scan time | 1,000 / 12 / 5 seconds |
| Per-source-file / aggregate source and ignore reads | 256 KiB / 8 MiB |
| Original input | 1 MiB, refused if oversized rather than silently shortened |
| Original response page | 8 KiB, paginated |
| Completion handoff | 2 KiB |
| Retained command output | 8 KiB per stream; combined private log capped at 16 KiB |

Limits can be selected at start with `--limits-file` subject to schema bounds.
Optional context omissions are marked with reasons/counts; overflow returns valid
JSON. Mandatory instructions/handoffs are never silently dropped: overflow requires
shorter reviewed interpretations or original-section access. Retrieval is lexical,
not semantic or embedding search. Missing/new files, no matches and incomplete scans
are explicit. Cached concise memory is invalidated with task/spec/source changes.

Repository content, memory and logs are **data**, not authority to override the user,
skill instructions or host approvals. Symlinks, traversal, hidden files, credential
files, local memory, virtual environments and generated directories are excluded;
root/nested ignore rules are respected. Recognized secrets are redacted and logs do
not contain full prompts/source. Secret detection is not universal: do not put
credentials in task inputs or command arguments.

Originals, evidence and helper telemetry are private under `.agentforge/sessions`;
local summaries use `.agentforge/memory/assist-v1` in a separate versioned namespace.
Existing framework memory is preserved, not migrated or silently imported. Keep
`.agentforge/` excluded from Git. POSIX files use private permissions; Windows needs
normal user-directory ACL protection. Optional memory failure emits a warning and
allows work to continue.

These are helper byte limits, **not Codex token budgets**. Codex may read more files,
retain original history or ignore a packet. Planning, retrieval interpretation,
repairs and final review all consume agent usage. See [benchmarking](benchmarking.md):
the authorized [three-condition pilot](pilot-benchmark-2026-10-13.md) passed all
fixed acceptance tests but measured more tokens in both helper conditions.
Post-pilot output/guidance corrections have offline checks, without another trial. MCP and automatic agent execution are not implemented.
