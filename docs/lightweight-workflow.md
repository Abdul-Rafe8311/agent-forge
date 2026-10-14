# Lightweight workflow after the pilot

## Existing-log findings (2026-10-14)

The initial lightweight revision launched no further coding benchmark. Inspection used the existing private event
logs, numeric helper telemetry and preserved specifications from the October 13
pilot. Raw logs, original prompts and project memory stay outside this repository.

All three conditions passed 26/26 fixed acceptance methods. Full-run input + output
was A **106,704**, B **588,769**, C **686,292** tokens. The old helper workflows used
more tokens. Cached input is a subset of input; reasoning is a subset of output.
The logs expose whole-run totals, not token attribution per helper/stage. Returned
byte counts below are not token counts or causal estimates.

| Sessioned operation | B calls / returned bytes | C calls / returned bytes |
| --- | ---: | ---: |
| start / amend | 2 / 593 | 1 / 361 |
| requirements | 8 / 29,672 | 8 / 42,042 |
| read-spec | 5 / 10,821 | 2 / 15,478 |
| checks | 1 / 1,081 | 1 / 1,765 |
| plan-check | 5 / 6,090 | 5 / 8,809 |
| prepare | 4 / 7,301 | 7 / 27,719 |
| validate | 5 / 10,500 | 9 / 15,031 |
| complete | 1 / 1,104 | 5 / 3,672 |
| final-check | 2 / 2,711 | 1 / 2,133 |
| **Total** | **33 / 69,873** | **39 / 117,010** |

Schema reads, installation/CLI argument failures and ordinary source reads are not
in session telemetry. Completed command items referencing `SKILL.md` occurred twice
in B and three times in C; this measures command occurrences, not all skill loading
or distinct file reads. Baseline had six command tools and two edit tools; B had
20+4 and C 22+4. Failed command exits were 0, 6 and 5 respectively. These are not
counts of code repair attempts.

### Avoidable work and setup failures

- Requirements were inspected/updated eight times per assisted run. Their serialized
  output was the largest helper category, including repeated full records and source
  previews. Both arms installed/rechecked plans five times. The prior post-pilot
  correction already shortened requirement/plan mutation acknowledgments; it was
  not part of the measured pilot. It does not eliminate explicit repeated reads.
- B had three required-instruction packet overflows and two session helper errors;
  C had two overflows and four session helper errors. Observed errors include stale
  specification hashes, unknown task IDs and a missing acceptance-check mapping.
  C also attempted registration from an input that was not a regular file. Its
  pre-session failure is absent from session telemetry. B had a generic invalid
  input/storage error whose precise cause is unavailable from that response.
  B's pending original-review gate caused an additional stop. The check was working
  as designed, but unnecessary setup transitions added work on this cohesive task.
- Source retrieval telemetry measured B 4 file reads/939 bytes and C 14/14,385,
  including repeated ignore/source reads. Most helper calls were tracking/validation,
  not retrieval. Baseline already located the three relevant modules and completed
  correctly despite the irrelevant files; the pilot demonstrated no selection or
  correctness advantage for helpers on this fixture.
- B kept the exact 2,850-byte original and a separate 1,384-byte amendment. C stored
  a 7,213-byte expanded original: **one** exact task followed by execution instructions
  and the full skill text. Reinspection found each substantial task line once.
  This corrects the prior report's unsupported assertion that the task was copied
  twice. Embedding the skill in requirements still repeated context unnecessarily.
- C's three cards added dependency/schema/check-catalog work, repeated preparation,
  completion submissions and handoffs. Five completion calls include a read and
  re-submissions, not five distinct task completions. The old C-B difference combines
  these effects and the expanded snapshot; it cannot isolate decomposition overhead.

Some acceptance validation and original review are necessary for correctness.
The avoidable component is requiring helper bookkeeping for every small task and
repeatedly returning material the agent already has. Exact savings from removing
any one call are **unavailable**: model reasoning, history reuse and caching interact,
and no per-step usage was exposed. Code rework remains unavailable rather than zero.

## Implemented default

`agentforge assist --project ROOT context --query "affected behavior"` retrieves
relevant code directly. There is no mandatory setup, session, memory, plan, registry,
check catalog, decomposition or handoff. The short explicit skill routes directly
here and links optional tracking instructions without loading them by default.
Original requirements and acceptance checks remain accessible in the conversation
or supplied file; the agent uses normal authorized checks and reviews the original.
Tracked mode can still preserve a file verbatim and provide local memory, source
references, dependencies, handoffs and evidence. Existing framework/server/provider
integrations are preserved. Redis is never selected implicitly.

Replies default to 4 KiB/three snippets of up to 20 lines, with path/range/hash,
data-only policy and explicit incomplete flags. Focus a known file to avoid scanning;
request missing ranges only as needed. Limits are serialized bytes, not tokens.
Automatic context search skips Markdown; explicit file selection still permits
original requirement/docs access when needed. Check catalog updates and completion
saves now return concise acknowledgments.
Their full data remain available through explicit read commands.

## Matched comparison setup

A private preparation directory contains fresh A/B projects copied from the same
TaskDesk starting commit `9678b1bc150589d03700705d659b991c81c89a78`, exact original
prompt snapshots and two `prepared_not_run` manifests. The original 26-method
read-only evaluator remains outside both writable projects, hash
`331a84c1b33f1f2657cb9627a864cca2589d29f24b3290edad537ccd8494c005`.
Original prompt hash:
`3ce19b850b820dd5ddbef4ba2321bf09556f556b3ad880260872ad3c65c951f6`.
No result code, logs or helper memory from the prior arms is copied.

The following controls were planned before the separately authorized attempts;
see the actual outcome below:

- A: ordinary unsplit Codex, installed AgentForge skill explicitly disabled, no
  helper calls. B: same task with short explicit skill/context helper; no required
  tracking or decomposition. Preserve identical full requirements/acceptance command.
- Both fresh sessions use planned Codex 0.162.1, gpt-6.1-sol, medium reasoning,
  workspace-write, approvals never, same tools/network restrictions, 900-second
  wall limit. Version/model availability and skill enable/disable must be reverified
  at launch; preparation does not assert they are currently active. No API-key
  billing or credential inspection is permitted. Never restart a failed run.
- Planned order B→A for this matched follow-up. Both need fresh runs; old A is only
  historical context. Cache effects remain uncontrolled; one reversed-order pair
  would still not be counterbalancing or proof of general savings. More trials
  require separate authorization and a predefined order/task sample.
- Start with no helper state in either project. Agent isolation denies access to
  the old arms and the other condition. Use the same read-only evaluator, compare
  changes for hardcoding/test tampering/unrelated edits, and retain failures.
- Capture the whole run, including skill load, context commands, normal checks and
  any retries. Collect only complete per-turn counters with documented semantics;
  derive input + output once, reporting cached/reasoning subsets separately. Report
  missing counters as unavailable. Count tools/failed commands separately from
  inferred repairs; record observed repair rounds consistently or leave unavailable.
- Accept correctness first. Only complete comparable counters support signed
  `(A_total - B_total) / A_total * 100`; negative savings mean greater usage.
  Do not equate token differences with subscription dollars or quota percentages.

## Remaining overhead and limits

The skill still has a discovery/reading cost; each helper call adds a tool turn and
JSON/provenance text. Repeated retrieval can repeat source context; no cross-call
cache suppresses it automatically. Lexical ranking can miss relevant symbols, and
short windows may require another range/file read. Ordinary tools may already be
more direct when the relevant files are known. Optional tracked mode still incurs
semantic planning and schema/evidence setup using the coding agent's allowance.

Offline tests establish bounds, source provenance, exclusions, installed behavior
and preparation mechanics. They do not establish coding quality or token savings.
**No token benefit has been measured for this revision.**

## Authorized A/B attempts — 2026-10-14

The user authorized one launch per condition. Both were attempted once in B→A
order; both failed before thread creation because the sandboxed instruction
loader could not execute Codex. No retries or additional coding runs occurred.
Token counters are unavailable, not zero, and no comparison can be calculated.
The unchanged starting code passed 4/26 fixed acceptance methods in each copy;
this is initial incompleteness, not a completed solution or an efficiency result.
See [the failed-pilot report](lightweight-pilot-2026-10-14.md) for actual counts,
setup diagnosis and remaining work.
