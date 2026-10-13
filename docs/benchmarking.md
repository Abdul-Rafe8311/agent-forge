# Three-arm comparison protocol

The offline tooling prepares manifests and collects existing logs. It never launches
Codex, model SDKs, Redis or a coding run. The authorized [2026-10-13 pilot](pilot-benchmark-2026-10-13.md) measured no token
benefit: all conditions passed, and both helper conditions used more tokens.
Synthetic fixture counts in automated tests still validate mechanics only.
This tooling does not authorize additional coding runs.

| Arm | Workflow |
| --- | --- |
| A | Same original task and agent settings; ordinary unsplit agent, no helpers |
| B | Same task/settings; local memory, bounded retrieval and validation, unsplit |
| C | Same task/settings/helpers; reviewed decomposition and final integration |

Use identical base commits, complete original prompt bytes, frozen acceptance checks,
agent version/model/reasoning, sandbox, approvals, network and tools. Seed memory
identically for B/C, separately record retrieval and planning, and do not share
run outputs or learned memory across arms. Isolate worktrees/session state and agent
threads. Counterbalance arm order across tasks/replicates; do not test only easy tasks
or omit failures. Include small work that should remain unsplit, a targeted bug fix,
a cross-module change, and long prompts with shared constraints and ambiguous details.

## Prepare manifests only

Create a private task JSON list (absolute prompt path; full prompt, no credentials):

```json
[{"id":"bugfix","prompt_file":"/private/bugfix.md","base_commit":"FULL_COMMIT_ID","acceptance_criteria":["Frozen behavior test passes","No interface regression"]}]
```

Record settings in private JSON. Replace placeholders with the actual intended values;
these manifests record choices but cannot enforce a future agent's settings:

```json
{"agent_version":"ACTUAL_VERSION","model":"ACTUAL_MODEL","reasoning":"ACTUAL_SETTING","sandbox":"ACTUAL_SETTING","approval_policy":"ACTUAL_SETTING","network":"offline","tools":["terminal"],"memory_seed":"empty-isolated","usage_semantics":"unknown"}
```

```bash
agentforge assist benchmark prepare --tasks-file /private/tasks.json \
  --settings-file /private/settings.json \
  --output-dir /private/experiment --replicates 3
```

This copies originals privately with SHA-256 hashes and writes one manifest per
arm/task/replicate, all `prepared_not_run` with `agent_runs_launched: 0`. Use a fresh
output directory; immutable existing files are not overwritten. Authorization for
coding runs is a separate later step. No run commands are provided here.

## Collect after separately authorized runs

Preserve available structured usage events from start through final integration,
including semantic planning, context retrieval/interpretation, retries and rework.
Include all agent threads/log files. Don't collect only the implementation stage.
Do not paste transcripts or credentials into public reports. Collection hashes source
logs and returns numeric fields, not transcript text. One input log is limited to
32 MiB; larger logs must be split into complete JSONL files.

Record outcome JSON from frozen checks and actual operator observations:

```json
{"final_status":"accepted","mandatory_passed":2,"mandatory_total":2,"regressions":0,"failed_checks":0,"repair_rounds":0,"reopened_tasks":0,"integration_fixes":0,"operator_interventions":0,"elapsed_seconds":120}
```

These outcomes are operator supplied, not an automatic correctness grader.
Unknown repair/reopened/integration/intervention counts may be null; do not invent
zeros. Counts are nonnegative integers and durations must be finite. Include
failed/blocked runs and actual rework. Count each repair round consistently in all
arms; freeze the rubric before running. Run durations include every stage.

```bash
agentforge assist benchmark collect \
  --manifest-file /private/experiment/bugfix-1-B.manifest.json \
  --outcome-file /private/outcome-B.json \
  --log /private/run-B.jsonl \
  --helper-log ROOT/.agentforge/sessions/SESSION/helper-events.jsonl \
  --output-file /private/result-B.json
agentforge assist benchmark compare \
  --result /private/result-A.json --result /private/result-B.json \
  --result /private/result-C.json
# Equivalent numeric report from previously collected result files:
python scripts/compare_agent_runs.py /private/result-A.json /private/result-B.json /private/result-C.json
```

Omit `--helper-log` for A. Repeat `--log` for additional threads. Helper telemetry
measures returned bytes (including repeat retrieval), source files/bytes read and
local duration; it is not model token usage. Its I/O counters cover context retrieval
only, not specification/state/memory reads or arbitrary additional file reads by Codex. Errors before a valid session and
CLI argument parsing are not recorded; report this helper-log coverage limit. A
bounded history that drops events is explicitly partial.

## Measurement rules

- Collect available `turn.completed.usage` fields: input, cached input, output and
  reasoning output. Record unavailable fields as null, not zero.
- Set `usage_semantics: per_turn` only after confirming that the actual agent/version
  reports disjoint per-turn usage. Default unknown and cumulative schemas do not
  produce a summed total. Duplicate whole files are skipped; event IDs are used
  where present. Overlapping logs without stable turn IDs cannot be reliably deduped:
  supply disjoint complete logs and record this limitation.
- Complete totals require start/completion coverage and no failures/invalid events;
  partial runs still retain their observed fields but have no derived total. This
  cannot detect wholly omitted threads; operator capture scope must be documented.
- Input plus output is derived only when coverage and semantics permit. Cached input
  and reasoning output are reported separately, not added again. No dollar-cost,
  quota-consumption or Codex internal-budget claims are inferred.
- Compare paired B-A (helper contribution), C-B (decomposition contribution), and
  C-A (total workflow difference). Reports include all outcomes and median available
  observed token differences. Missing measurements produce null differences. Signed `saving_percent` uses
  `(baseline - assisted) / baseline * 100` when complete comparable totals and a
  positive baseline exist. `correctness_comparable` must also be true before
  interpreting an observed reduction as an efficiency result; an incorrect solution
  is not an efficiency win. Completed tool items and failed command exits are
  reported separately from unavailable inferred repair attempts.
- Judge mandatory correctness, regression count and rework alongside usage. Smaller
  packets or lower reported usage alone are not success. Report trial count/spread
  and capture limitations; timing/order noise and unmeasured allowance changes remain.

FakeProvider/mock tests establish helper and collection correctness, not real coding
ability. Live OpenAI/Anthropic integrations have not been tested. No Redis or paid
model connections are part of this benchmark preparation.
