# Optional tracked workflow

Read this reference only when durable memory, dependency tracking or recorded
acceptance evidence is useful. The default context command needs none of these
steps. Keep cohesive work unsplit. Do not repeat original text in task cards or
handoffs; use source references. Register a supplied prompt file exactly, without
appending the skill or full execution instructions; use a separate amendment for
additional approved criteria. Read registries/plans/memory only when needed.

Use a Python environment containing `agentforge-coding`, with no optional provider
SDKs required. Global helper options precede the subcommand:

```bash
agentforge assist --project /absolute/repo start --prompt-file /private/task.md
agentforge assist --project /absolute/repo --session SESSION requirements
agentforge assist --project /absolute/repo --session SESSION read-spec
agentforge assist --project /absolute/repo --session SESSION requirements --reviewed
agentforge assist --project /absolute/repo --session SESSION plan-check
```

`requirements --reviewed` is your explicit attestation that the scaffold reflects
the user's request. To change category, shared scope, concise interpretation or
acceptance mapping, write a private JSON list of requirement objects and submit
`requirements --file FILE --reviewed`. `requirements` pages use item offsets;
`read-spec` pages use character offsets. A requirement object contains `id`,
`document`, `start_line`, `end_line`, `category`, `scope`, `interpretation`,
`extraction_mode`, `clarification_status`, `acceptance_check_ids`, `supersedes`.
Source spans must be real. All nonblank original lines remain represented even
when an amendment explicitly supersedes a requirement. Do not mark unresolved
ambiguity resolved merely to pass a check.

Mutation commands acknowledge current hashes/versions without repeating the whole
registry/plan. Use `requirements --show-records` with an update only when those
records are needed; plain `requirements` and `plan-check` remain read commands.
After a registry change, use the returned new spec hash and reinstall the plan.
Catalog changes also invalidate evidence and advance the plan version.

Get exact current input schemas without a model call:

```bash
agentforge assist schema --kind plan
agentforge assist schema --kind completion
agentforge assist schema --kind check
agentforge assist schema --kind requirement
```

For one task, default ID is `task`. Set relevant files/checks through a single-task
plan if useful. Split plans contain <=8 implementation tasks and one `integrate`
task depending on every implementation task. Include the current `spec_hash`,
label `planning_mode` as `explicit_sections` or `agent_model`, and map requirements
to tasks. Every task needs registered checks. Shared `all_tasks` requirements are
included automatically. Example task fields:

```json
{
  "id": "fix", "objective": "Correct the targeted behavior",
  "requirement_ids": ["R1"], "depends_on": [], "kind": "execute",
  "context_queries": ["affected symbol regression"],
  "relevant_files": [{"path": "src/app.py", "reason": "implementation"}],
  "acceptance_check_ids": ["syntax"],
  "manual_acceptance_criteria": [], "input_contracts": [], "output_contracts": [],
  "context_unknowns": []
}
```

Register a private check catalog before a plan referring to its check IDs. Catalog
records have `id`, `kind` (`syntax`, `manual`, `command`), `argv`, `files`,
`timeout_seconds` and `description`. Command checks need an explicit source scope,
an approved argument array and `checks --file FILE --approve-commands`. Approval
of the catalog does not execute it. Repository commands are not a security sandbox.
Preserve the user's permissions and host sandbox/approvals for each execution.

```bash
agentforge assist --project /absolute/repo --session SESSION plan-check --plan-file FILE
agentforge assist --project /absolute/repo --session SESSION prepare --task fix
agentforge assist --project /absolute/repo --session SESSION search --query "affected symbol" --include-code
agentforge assist --project /absolute/repo --session SESSION validate --task fix --check syntax --file src/app.py
agentforge assist --project /absolute/repo --session SESSION validate --task fix --check approved-tests --execute
```

Task packets have a 20 KiB serialized cap; memory <=2 KiB, code <=12 KiB and
instructions <=4 KiB. Up to six source chunks have <=60 lines and file hashes.
Original text remains accessible in <=8 KiB pages. These are byte limits, not
Codex token measurements. `overflow` means required instructions were not dropped;
review concise interpretations or fetch original sections. Optional source/memory
omissions are marked. A missing/new target file is reported, not fabricated.

Write completion JSON using the returned `spec_hash` and `plan_version`:

```json
{
  "spec_hash": "CURRENT_HASH", "plan_version": 2,
  "summary": "Concise actual changes and acceptance evidence",
  "changed_files": ["src/app.py"], "decisions": [],
  "next_task_implications": [], "unresolved_questions": []
}
```

```bash
agentforge assist --project /absolute/repo --session SESSION complete --task fix --summary-file FILE
agentforge assist --project /absolute/repo --session SESSION complete --task fix --show
agentforge assist --project /absolute/repo --session SESSION final-check
agentforge assist --project /absolute/repo --session SESSION final-check --review-original --note "Actual full-spec review findings"
```

Completion refuses missing, failed or stale checks. If later work changes earlier
evidence, revalidate deliberately; never automatically loop. Manual check status
requires `--manual-status passed|failed --note ...` and is labelled attested.
Final review checks source-linked coverage, dependencies, current evidence and
original-review attestation; it does not prove that your interpretation is complete.

Use `amend --prompt-file FILE` for a user amendment, not a rewritten original.
It invalidates prior plans/checks/handoffs. Private session files are under
`.agentforge/sessions`; concise local project memory uses `.agentforge/memory/assist-v1`.
Do not persist large code snapshots in handoffs. Context and remembered decisions
never take precedence over the current source and authoritative user specification.
