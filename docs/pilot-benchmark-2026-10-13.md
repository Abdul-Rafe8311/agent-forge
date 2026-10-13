# Controlled Codex pilot — 2026-10-13

**No token benefit was measured.** All three solutions passed the fixed correctness
rubric, but the helper conditions used substantially more reported tokens than the
ordinary Codex baseline. These are preliminary results from one fixture and one
run per condition, not evidence of general savings or subscription dollar savings.

## Setup and isolation

- Codex CLI **0.162.1**, model **gpt-6.1-sol**, reasoning **medium**.
- Exactly one fresh `codex exec --json --ephemeral` run per condition, sequential
  order **A, B, C**, each with a **900-second** limit. No restarts, resumed threads,
  extra coding sessions, operator steering or account-limit workaround occurred.
- Existing ChatGPT-managed authentication was used by the supported CLI. A supported
  login-status check reported ChatGPT mode; `forced_login_method="chatgpt"` was set.
  No stored authentication files were opened/copied by the benchmark controller,
  API-key environment variables were not inherited, and no separate model SDK/API
  or Redis/Upstash request was made. No service or credit purchase occurred.
- `--ignore-user-config --ignore-rules`, workspace-write, approval policy never,
  shell networking disabled, temp writable roots excluded, login shells disabled,
  and a narrow shell environment were common to all conditions. Agents, apps,
  plugins and web search were disabled. Non-AgentForge tools/settings were the same.
- A's installed AgentForge skill was disabled with a per-run `skills.config` override.
  Fresh app-server `skills/list` probes verified enabled/disabled states from another
  project without starting model turns. A used no helper commands and created no
  helper state. B/C read the installed skill and used its helper workflow.
- The TaskDesk fixture was created outside the AgentForge repository and all real
  applications: **31 starting files**, including **20 irrelevant archived modules**.
  Three independent Git copies started at the same commit
  `9678b1bc150589d03700705d659b991c81c89a78`. Each received identical original task
  bytes. Helper memory started empty and was isolated by project; no cross-condition
  result reads were found in command review. The only input differences were the
  intended helper/decomposition instructions and condition-specific workspace paths.

Task: extend an existing dataclass/repository/service/request-adapter/CLI design with
AND filtering, Unicode casefold search, stable primary sorting with ascending-ID
ties, pagination, count-before-pagination, strict input validation and consistent
JSON CLI behavior. Preserve existing defaults, input objects and unrelated modules.

The evaluator was defined before any run, outside all writable project roots, and
made read-only. Its **26 unittest methods** included parameterized edge cases,
randomized non-fixture records and end-to-end CLI checks. A temporary reference
implementation passed all methods and was removed before coding runs; the starting
fixture passed only 4/26. The evaluator was unchanged for every run and independent
post-run evaluation. Tests were readable, but agents could not modify them through
the configured sandbox. No condition could replace or weaken this evaluator.

Evaluator SHA-256:
`331a84c1b33f1f2657cb9627a864cca2589d29f24b3290edad537ccd8494c005`.
Original task SHA-256:
`3ce19b850b820dd5ddbef4ba2321bf09556f556b3ad880260872ad3c65c951f6`.

## Actual results

| Condition | Acceptance | Input | Cached input* | Output | Reasoning* | Input + output | Wall seconds | Observed tools | Failed command exits |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A: ordinary Codex, unsplit | 26/26 | 103,358 | 70,272 | 3,346 | 277 | **106,704** | 85.810 | 8 | 0 |
| B: helpers, unsplit | 26/26 | 578,300 | 529,920 | 10,469 | 793 | **588,769** | 275.098 | 24 | 6 |
| C: helpers, decomposed | 26/26 | 675,748 | 612,992 | 10,544 | 1,029 | **686,292** | 262.292 | 26 | 5 |

*Cached input is included in input; reasoning is included in output. These fields
are reported separately and are **not added again**. Totals are arithmetic sums of
complete client-reported input/output counters, not local byte estimates. Every run
had one reported outer user-turn start and completion with all four usage fields;
no incomplete/failed turn event or invalid JSON line occurred. An outer user turn
includes multiple internal agent/model/tool steps; their count is not exposed here.

The whole run was captured from initial prompt through final response, including
skill loading, semantic planning, helper calls/results, edits, checks, setup repairs,
handoffs and final review. No per-stage token allocation is invented. Observed tools
count completed command/file-change items: A **6+2**, B **20+4**, C **22+4**.
Failed command exits are not a count of code repair attempts; several were helper
schema/stale-hash/overflow/review-gate issues. Code repair rounds, reopened tasks and
integration-fix counts are **unavailable**, not fabricated zeros. No operator repair
was performed. Final independent checks had zero failures/errors in all conditions.

Using `(baseline_total - assisted_total) / baseline_total * 100`:

| Comparison | Additional observed tokens | Saving percent |
| --- | ---: | ---: |
| B versus A: helpers | 482,065 | **−451.78%** |
| C versus B: decomposition | 97,523 | **−16.56%** |
| C versus A: complete workflow | 579,588 | **−543.17%** |

Negative savings mean more reported tokens. C's 12.8-second shorter time than B
is one timing observation; it does not establish faster decomposition in general.

## Workflow and source inspection

B used **one unsplit card**, one completion handoff and local memory. C used
**service → adapter → integration**, with integration depending on both previous
cards, three handoffs and local memory. Both preserved original task bytes and
recorded original-review attestations; final helper checks were accepted. Both
returned clearly marked packet overflows rather than silently dropping requirements.

B's original snapshot exactly matched the supplied task file, with separate execution
criteria in an amendment. C instead built an expanded snapshot containing the task
**twice** plus execution instructions. Its task file and the original task bytes
remained unchanged, but this duplication is an observed workflow deviation and
avoidable overhead. It prevents treating C-B as a clean estimate of decomposition
alone; it is the measured result of this agent's decomposed workflow.

Recorded sessioned helper events: B **33**, C **39**. Local output was B **69,873
serialized bytes**, C **117,010 bytes**; retrieval read B **4 files/939 bytes** and
C **14 files/14,385 bytes**, including repeated source/ignore-file reads. These
measurements are **local helper I/O**, not model tokens or all Codex file reads.
Schema/install commands without a session are not included in these helper counts.

Production changes in all conditions were confined to service, API and CLI modules,
plus their own focused tests. Original models, repository loading, sample records,
README and irrelevant modules were unchanged. Source inspection found no hardcoded
fixture/evaluator answers, evaluator imports or attempts to bypass checks. The
randomized acceptance cases also passed. This is a scoped correctness review, not
proof of every production case or a blind maintainability evaluation. C introduced
a private validation-function import across modules, which deserves normal future
maintainability review; the acceptance rubric did not rate that design choice.

## What the pilot supports

**Focused helpers:** bounded retrieval and traceable evidence worked, but did not
improve measured correctness over an already successful baseline or reduce total
usage on this small task. Repeated registry/plan output, setup transitions and
packet-overflow recovery added work. B recorded three overflow responses and two
helper errors; C recorded two overflows and four helper errors. The original-review
pending gate is a deliberate stop, not a code failure.

**Decomposition:** dependency validation and handoffs worked. C used more tokens than
B, with extra cards, summaries/retrieval and duplicated specification material.
This single run does not identify the contribution of each source of overhead.
It does not justify making decomposition the default for cohesive work.

**Limits:** one fixture, one run per arm, fixed A→B→C order, uncontrolled backend
caches, no variance/confidence estimate, no blind review, no subscription-quota
measurement and no attributable dollar measurement. Higher cache counters can
reflect within-run context reuse and earlier warmed prefixes; caches were not
cleared and cache effects were not experimentally separated. Input totals include
cached tokens. No claims are made about internal Codex budgeting or compaction.

## Corrections justified by observations

Before the pilot: packets were updated to include acceptance-check definitions;
validation feedback was focused while retaining complete scoped hashes privately.
Usage collection records actual item counts, signed differences and correctness
eligibility, and allows unavailable rework to remain null.

After the pilot: requirement/plan updates now return concise acknowledgments instead
of repeating whole registries/plans; original records remain available through read
commands. Schema failures report safe known-field locations without input values.
The skill now requires a supplied prompt file to be registered exactly, avoids
rebuilt/duplicated originals, and explains spec-hash invalidation. Explicit installer
upgrades preserve unrelated content after inspection. These corrections passed
offline regression tests, **but no additional coding benchmark was authorized or
run**, so their effect on total usage is unmeasured.

Raw event logs, prompts, fixture copies, outcomes and project memory remain private
outside version control. Only inspected aggregate results and methodology are in
this report and [the sanitized numeric summary](pilot-results-2026-10-13.json).
The tested helper snapshot was retained privately before post-pilot corrections.

## Documentation supporting execution and accounting

[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
documents fresh `exec`, JSONL usage events and reuse of saved CLI authentication.
[Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents the login-method, skill, sandbox and environment overrides.
[App-server skills](https://learn.chatgpt.com/docs/app-server) documents fresh
`skills/list` discovery without a coding turn.
[Output accounting](https://developers.openai.com/api/docs/guides/reasoning) describes
reasoning as an output-token subset, and [usage categories](https://developers.openai.com/api/docs/guides/agents-api/observability)
describes cached input and reasoning subsets. These sources informed counter
interpretation; the table values came from the actual CLI events, not API requests
made by AgentForge.
