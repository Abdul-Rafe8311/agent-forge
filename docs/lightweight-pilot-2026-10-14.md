# Lightweight A/B pilot attempts — 2026-10-14

**The matched comparison could not run.** Both authorized launches failed before
Codex created a thread. No token counters or coding results were emitted. This
is a runner setup error, not evidence for or against the lightweight helpers.
Exactly two launches were attempted, in **B→A** order, with **no restarts** or
additional coding runs. No Redis, separate model API, purchase or publication occurred.

## Matched setup and verification

Both projects began at commit `9678b1bc150589d03700705d659b991c81c89a78`, with identical
original task bytes, 31 starting files including 20 irrelevant archived modules,
and the same external read-only 26-method evaluator. The fixture was isolated from
the AgentForge checkout and real applications. Memory was empty and stayed empty.
No outputs or memory from the earlier A/B/C pilot were reused.

- Codex **0.162.1**, requested model **gpt-6.1-sol**, reasoning **medium**.
- Existing ChatGPT-managed authentication was confirmed through the supported CLI.
  No stored login credentials were read/copied by the controller; API-key variables
  were not inherited. `forced_login_method="chatgpt"` was set.
- Fresh app-server `skills/list` with `forceReload` discovered the updated skill's
  exact description and SHA-256: enabled for B, disabled for A, no discovery errors,
  no model turns. This verifies discovery, not successful coding use.
- Both attempted `codex exec --json --ephemeral`, ignoring user configuration and
  execution rules; approval never; same tools and **900-second** wall limit.
  Apps/plugins/web search/subagents were disabled. Only treatment instructions and
  the active workspace/other-workspace paths differed.
- The common permission profile granted own-project writes, evaluator/runtime reads,
  denied the other condition and old pilot paths, and disabled tool networking.
  Python sandbox probes passed own writes, context retrieval, cross-run read denial
  and evaluator write denial. They did not test Codex's nested instruction loader.
- B requested focused `assist context` retrieval and the short skill only. No
  decomposition, tracking, memory, cards or handoffs were required. A disabled the
  installed skill and prohibited helper use. Original requirements/acceptance checks
  were identical, authoritative and accessible in `TASK.md`.

Original task SHA-256:
`3ce19b850b820dd5ddbef4ba2321bf09556f556b3ad880260872ad3c65c951f6`.
Evaluator SHA-256:
`331a84c1b33f1f2657cb9627a864cca2589d29f24b3290edad537ccd8494c005`.
Skill SHA-256:
`b005e2a81cd76c9f75484e7be5ba417869d18eae8fc367d8a2adde8d6e9940e8`.

## Actual outcomes

| Metric | A: ordinary Codex | B: lightweight AgentForge |
| --- | ---: | ---: |
| Outer launch attempts / restarts | 1 / 0 | 1 / 0 |
| Launch exit status | 1: setup failure | 1: setup failure |
| Thread creation | failed | failed |
| Fixed acceptance after attempt | 4/26 | 4/26 |
| Task completed | no | no |
| Input tokens | unavailable | unavailable |
| Cached input tokens | unavailable | unavailable |
| Uncached input tokens | unavailable | unavailable |
| Output tokens | unavailable | unavailable |
| Reasoning tokens | unavailable | unavailable |
| Total input + output | unavailable | unavailable |
| Outer process wall seconds | 1.425 | 0.610 |
| Helper calls observed in run events | 0 | 0 |
| Agent command tools / failed command exits observed | 0 / 0 | 0 / 0 |
| Failed outer launches | 1 | 1 |
| JSONL event bytes / reported turn starts / completions | 0 / 0 / 0 | 0 / 0 / 0 |
| Production changes / helper memory created | none / no | none / no |

The independent evaluator remained unchanged and each project stayed clean at its
starting commit. Their 22 unmet acceptance methods are the starting fixture's
missing implementation; they are not regressions introduced by edits. No hardcoded
answers, test tampering or unrelated changes were introduced because no agent edited
anything. The two outer failures are distinct from agent command failures.
Elapsed values measure failed process startup, not coding performance.

## Blocker and next preparation step

Both stderr diagnostics report `thread/start` failure while loading `AGENTS.md`:
the filesystem sandbox helper's `execvp` of the installed Codex executable was
rejected with `Operation not permitted` (sandbox helper exit 71, RPC -32603).
The custom permission profile omitted the launcher from its readable roots and
denied the `.codex` subtree that contains its resolved standalone executable.
This was a benchmark-controller configuration error. The independent Python probes
missed the extra executable used internally by Codex's instruction loader.

Preserve the recorded failed settings. For a future preparation, resolve the actual
Codex executable and add **that exact path and its resolved target** as `read` entries
in the complete `permissions.pilot.filesystem` table. Keep credential/state paths denied while granting only the executable/code paths;
a broad `.codex` deny also covers the installed executable. Verify local ephemeral
`thread/start` and `skills/list` under the same settings **without `turn/start`**,
in addition to command isolation probes. A fresh process merely listing skills is
not enough to prove a coding session can start. Do not relax verification, network
or cross-run/credential isolation to work around this problem.

Two subsequent local ephemeral-thread probes made **no `turn/start` calls** and
did not restart either condition. Adding launcher/target read grants, then narrowing
the `.codex` deny to auth/config files, still did not permit the nested executable.
The proposed permission repair is therefore **not verified**. The probes also logged
model-catalog refresh connection failures/timeouts; these were Codex metadata
requests, not coding generation. Further filesystem/exec-policy diagnosis and a
successful zero-turn thread preflight remain necessary. No credentials were exposed.

No condition was retried after this diagnosis. Any future coding run requires new
authorization; these two failed attempts cannot be silently replaced.

## Measurement limits

No usage events exist. All token counters, including uncached input and total, remain
null/unavailable. Absent events cannot prove zero subscription allowance consumption.
For a future completed run, uncached input is input minus cached input only when
both complete counters are available and cached input is a valid subset. Total is
input plus output; cached input and reasoning output are not added again. Preserve
full-run capture including skill load, retrieval, tests and any repair activity.

There is no eligible savings calculation, no demonstrated token benefit, and no
coding correctness comparison. Do not interpret missing output as an efficiency win
or infer dollars/quota use. Fixed B→A order and uncontrolled caches would still limit
a completed one-pair pilot. Raw prompts, stderr/events, fixture copies, environment,
helper artifacts and memory remain private outside version control.

## Official interface references

Fresh non-interactive JSON events and ephemeral sessions are supported by
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
Discovery reloads and local thread creation are documented in
[Codex app-server](https://learn.chatgpt.com/docs/app-server).
The runner's explicit access rules follow
[Codex permissions](https://learn.chatgpt.com/docs/permissions).
These documents establish interfaces, not measured results or account charges.
