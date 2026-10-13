# AgentForge coding-agent integration plan

Status: **P1–P6 implemented; authorized three-run pilot completed on 2026-10-13**.
See [shipped commands and installation](coding-agent-integration.md),
[benchmark protocol](benchmarking.md), and [actual verification](verification.md).
Inspected baseline: `a808dff2e5f6a18837751e0c6be7a4fe3aa0069c`.
Official Codex documentation rechecked on 2026-10-13. The [pilot report](pilot-benchmark-2026-10-13.md)
records complete counters, equal acceptance outcomes and negative token savings.

## 1. Product objective and boundaries

AgentForge should help an existing coding agent, starting with Codex, select useful
project context, retain concise project knowledge, organize complex work, and
receive actionable validation feedback. Codex remains responsible for interpreting
the request, editing code, deciding which tools to use, and communicating with the
user. Success means correct completed work with less avoidable context or rework,
when measured; it does not mean merely returning a smaller helper response.

Helper operations are local file processing and subprocess/report handling. They
need no separate OpenAI/Anthropic model API, embeddings API, provider token-count
endpoint, or Redis connection. Local memory is the default. Redis remains optional
and explicitly configured; it is mocked during all development and automated
checks. Helpers and offline verification make no model calls. Separately, the user authorized
one account-backed Codex pilot run per A/B/C condition; those runs are complete.

AgentForge controls the size of **its own returned context**, not Codex's internal
context window, compaction, reasoning, token allowance, billing, or model routing.
Codex can read additional files or ignore a suggested packet. Skills, tool schemas,
planning, tool interpretation and final review also consume the agent's allowance.
A helper can reduce redundant material and still increase total usage or miss
necessary context. No general token-saving or code-quality improvement is established. The pilot
passed the same correctness checks in all conditions and used more tokens with helpers.

Preserve `agentforge-coding`, the `agentforge` import/CLI, existing memory data,
provider adapters, orchestration, server, JavaScript example, tests and documentation.
The implemented HTTP generation server becomes an optional existing capability;
it is not the Codex integration entry point. No deletion or public-API migration is
needed to begin. Keep new agent-helper contracts separate from provider accounting.

## 2. Supported Codex integration: start with a skill and local CLI

### Official mechanisms checked

| Mechanism | Supported role | Recommendation |
| --- | --- | --- |
| Local skill | `SKILL.md` instructions plus optional scripts/references; Codex loads skill detail when selected | First integration: explicitly invoke a repository skill backed by local CLI helpers |
| `AGENTS.md` | Persistent project instructions, with directory scope and precedence | Keep any pointer short; preserve existing guidance instead of replacing it with memory or task prompts |
| Local STDIO MCP | A local command exposes structured tools to Codex | Optional second adapter over the same helpers, after the CLI workflow works |
| Codex SDK/app-server automation | Programmatic operation of Codex | Defer; unnecessary for the first helper workflow and would add agent-execution lifecycle concerns |
| Existing AgentForge `/generate` API | AgentForge's own provider orchestration | Preserve, but do not use it to run a second paid model behind Codex |

The recommendation is an engineering choice, not an OpenAI requirement. A local
skill has the smallest setup for a coding agent already able to use its terminal.
It can call deterministic helpers and read referenced material on demand. Local
STDIO MCP is supported when named tools are preferable; it needs no HTTP listener
or hosted service. Availability in other surfaces must be checked separately.

Implemented skill: `.agents/skills/agentforge-coding/SKILL.md`, invoked as
`$agentforge-coding` in Codex CLI/IDE. Keep it concise, link detailed references,
and initially set `allow_implicit_invocation: false` in optional
`agents/openai.yaml` for deliberate use and comparable experiments. A repository skill and explicit packaged installer are shipped. The user skill was
installed and verified through fresh Codex discovery and actual pilot use; unrelated
skills/configuration were preserved. No persistent Codex settings were changed.

The skill's workflow: register the specification, fetch concise memory and source,
choose one task or a reviewed task plan, implement through Codex, run authorized
acceptance checks, inspect focused feedback, then record a compact handoff. Start
in one Codex conversation. New threads/subagents are not required, do not guarantee
context savings, and add startup/handoff overhead if chosen later.

Sources: [Build skills](https://learn.chatgpt.com/docs/build-skills),
[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
These document the mechanisms; the repository now ships the local skill/CLI integration.

## 3. Repository audit: reuse and required adaptations

| Existing module | Reusable foundation | Limits or adaptation needed |
| --- | --- | --- |
| `agentforge/memory.py`: `MemoryBackend`, `LocalMemoryBackend` | Project namespaces, versioned JSON, locks, atomic replacement, bounded retention | Existing records store run outcomes and artifacts. Add concise decision/handoff records separately, with schema version and source evidence; do not silently rewrite old records |
| `RedisMemoryBackend` | Optional lazy TCP/TLS storage, required certificate/hostname verification, explicit zero SDK retries | Keep it optional. Local mode must not resolve REDIS_URL or instantiate Redis. Do not repeat the completed live smoke test |
| `build_memory_context` | Deterministic relevance/recency selection and rejection of failed artifact state | It serializes full records/artifacts and uses a coarse estimator. New selection should return summaries, evidence paths and stale-state warnings, not old source snapshots by default |
| `make_memory_entry` | Bounded/redacted outcome serialization | It truncates task/summary to 512 characters and can omit artifacts. It cannot preserve a long authoritative specification; use a dedicated specification store |
| `agentforge/compressor.py`: `ContextCompressor` | Lexical ranking, path weighting, Python AST windows, 60-line chunks, line references, ignore support and symlink exclusions | Add aggregate I/O and output-byte limits, positive-match filtering, explicit requested ranges, file hashes and incomplete-scan indicators. Review nested ignore/negation behavior; current `any(match)` does not provide full Git override semantics |
| `agentforge/decomposer.py`: `parse_plan` | Strict IDs, dependency validation, stable topological ordering, cycle rejection, final integration dependency | Reuse/extract the pure graph checks. `Step` lacks requirement/context/acceptance fields; introduce separate task contracts without changing the old schema |
| `TaskDecomposer.decompose` | Existing provider-orchestrated planning, retained for its current API | It calls `router.generate`; do not invoke it for agent helpers. Semantic proposals come from Codex itself, not a new paid provider |
| `PythonSyntaxValidator`, `ValidationIssue`, `ValidationResult` | Syntax checks and structured path/line diagnostics | Adapt already-edited repository files to these contracts. Syntax is not correctness and other languages need configured checks |
| `CommandValidator` | Argument arrays, timeout, bounded retained stdout/stderr, redacted diagnostics | It stages only supplied artifacts in an empty temp directory. Real-project tests need repository/worktree context and existing dependencies; add an explicit repository-check adapter, not silent behavior changes |
| `agentforge/artifacts.py`, `utils.py` | Safe path helpers, stable project keys, strict JSON parsing and diagnostic redaction | Reuse applicable helpers. Redaction is not universal secret detection. Current `estimate_tokens` is UTF-8 bytes plus 16, not a Codex tokenizer measurement |
| `types.py` | Context chunks and validation contracts | Add independent helper/session/task/usage-observation contracts, rather than claiming provider `TokenUsage` describes all Codex usage |
| `prompts.py`, `core.py`, `router.py` | Completed provider orchestration and accounting | Preserve. `build_step_messages` currently includes the full original task and full accepted artifacts on each step; new task packets must not use that template |
| `decorators.py` | Python callback augmentation, with documented opaque accounting limits | A Python callback decorator is not a supported way to intercept a running Codex UI. Do not market `optimize` as Codex integration |
| `cli.py`, `server.py`, examples, packaging/CI | Existing delivery and regression coverage | Add `agentforge assist` commands alongside `run`/`serve`; preserve their behavior. Helpers do not construct provider clients or call generation/counting endpoints |

Retrieval is currently lexical, not semantic embedding search. It can fill output
with zero-score chunks, and scan/read bounds are not an aggregate context-service
budget. With its defaults, up to 2,000 files could each be considered for a 256 KiB
read; a small returned bundle does not imply cheap or focused retrieval.

## 4. Proposed local workflow and data contracts

The following design contracts are implemented. For exact shipped CLI option order,
use [the workflow](coding-agent-integration.md): global `--project`/`--session` precede
the command. JSON schemas are available with `assist schema`.

| Design command | Result / side effect |
| --- | --- |
| `agentforge assist --project ROOT start --prompt-file FILE` | Register immutable specification reference/snapshot and a local session; no generation |
| `agentforge assist --project ROOT --session ID requirements` | Enumerate original source spans and explicit checklist items; flag unclear/inferred items |
| `agentforge assist --project ROOT --session ID prepare --task TASK_ID` | One bounded packet: task instructions, relevant requirements, cross-task constraints, memory, code ranges and checks |
| `agentforge assist --project ROOT --session ID read-spec --requirement R1` | Fetch a requirement's authoritative source span; bounded range/section paging also available |
| `agentforge assist --project ROOT --session ID plan-check --plan-file FILE` | Validate an agent-authored or explicit deterministic plan and coverage; no model call |
| `agentforge assist --project ROOT --session ID validate --task TASK_ID --check CHECK_ID` | Syntax feedback or one authorized check from a pre-agreed catalog; no autonomous repair |
| `agentforge assist --project ROOT --session ID complete --task TASK_ID --summary-file FILE` | Store compact completion/evidence; reject incompatible specification version or invalid dependency state |
| `agentforge assist --project ROOT --session ID final-check` | Requirement/evidence coverage and integration-check manifest; Codex must review against the original text |

Use a new `agentforge/assist/` package with adapters to existing components. It
must not depend on `ModelRouter`, `TaskDecomposer.decompose`, provider SDK clients,
HTTP server startup or the provider token ledger. Default dependencies remain
local Python tooling. The optional future MCP adapter invokes these same functions;
it must not expose `/generate` as a hidden model call.

### Memory

Use local storage by default. Define a versioned compact record with project ID,
repository revision/file fingerprints, decision or known pitfall, evidence,
validation status, task/spec IDs and timestamp. Proposed saved record limit:
2 KiB. Retrieve at most five candidates, returning a total of at most 2 KiB of
selected memory including provenance. Current source and the original user request
take precedence over memory. Changed evidence hashes mark records stale; missing
or corrupted memory should produce a clear warning and allow work without memory.

Do not pretend to summarize old records semantically using a deterministic
serializer. Surface existing summaries/provenance with their known limitations,
and let Codex author a concise new completion record as part of its normal work.
Do not include old artifact bodies unless explicitly requested. Read memory once
per task preparation and cache within the session; do not poll. A run-wide switch
selects local or explicitly enabled Redis; environment presence alone never selects
Redis. Future Redis checks stay mocked and no live check is repeated here.

### Relevant code and explicit size limits

Proposed initial defaults below are engineering limits, **not measured optimal
values or Codex token limits**. UTF-8 byte counts include returned JSON metadata:

| Item | Proposed bound / behavior |
| --- | --- |
| Combined task packet | 20 KiB maximum |
| Memory portion | 2 KiB total |
| Code portion | 12 KiB total; at most six chunks, each at most 60 lines |
| Instructions/requirements/checks | 4 KiB, with remaining packet space for metadata |
| File/range search metadata | 4 KiB; return paths/symbols before bodies when helpful |
| Original-spec retrieval | 8 KiB per page with original line ranges and continuation |
| Validation feedback | 4 KiB rendered feedback, at most ten distinct issues; full logs retained privately with bounded storage |
| Completion handoff | 2 KiB maximum, source references instead of pasted code |
| Repository discovery | At most 1,000 examined files, depth 12, 256 KiB per file and 8 MiB aggregate content read; configured deadline, initially 5 seconds |

Use deterministic matching for paths, symbols, identifiers, acceptance-test names
and task terms; existing path-weighted lexical ranking is the starting point.
Combine explicit paths, nearby imports/interfaces and relevant tests. Exclude
zero-score chunks unless explicitly selected. Return a valid, complete snippet
with path, line range and file hash; report omitted candidates and insufficient
coverage rather than padding with irrelevant code. Expand missing dependency
context on demand, within new bounded requests; lexical matching can miss important
callers and must not be presented as comprehensive semantic understanding.

Honour root/nested ignore policy, `.agentforgeignore`, credential exclusions,
symlink/root boundaries, binary checks and generated-file exclusions. Record scan
limits hit and changed-file hashes. Cache deterministic results by task/query and
file state; invalidate after edits. Retrieved source/memory are data, not a way to
override user or Codex instructions. Approved repository instructions keep their
existing Codex scope and precedence.

Do not silently drop a mandatory constraint to fit a packet, cut JSON mid-record,
or cut code in the middle of a relevant unit without marking its range. If required
instructions exceed the budget, return an explicit overflow result and retrieve
the necessary authoritative sections separately. The original spec is never
truncated to satisfy a packet budget.

### Focused instructions and targeted validation

Each packet states what to change, which requirements apply, what must remain
unchanged, which relevant interfaces/tests to inspect and how success is checked.
Do not ask for entire-file replacement or resend every accepted artifact.

Default validation is a deterministic syntax/structure check on selected files.
User/project-approved lint, type and test commands live in a check catalog with
IDs, argv, working directory, timeout and scope. Execute one explicitly requested
check; no hidden test loop or model-driven repair. Never turn arbitrary prompt or
retrieved text into a shell command. Repository-check execution must preserve Codex
approvals/sandbox boundaries and is not itself a security sandbox. An explicit
worktree/repository adapter is needed because the existing temp-directory validator
does not contain the real project or dependency environment.

Return check ID, scope, exit status, actionable file/line failures, deduplicated
diagnostics, timeouts and truncation flags. Keep pending/manual checks distinct from
passed ones. Syntax success cannot satisfy behavioral acceptance. Every feedback
round and retry is recorded for comparison, with repairs performed by Codex.

## 5. Long-prompt decomposition without losing the specification

### Preserve authority and traceability

Keep the user's original prompt verbatim as the authoritative task specification,
subject to applicable higher-priority instructions. Store its hash and source path;
an optional private snapshot lives in ignored
`.agentforge/sessions/<session>/spec/original.md` with restrictive permissions.
Never put it into `MemoryEntry.task`, whose existing truncation loses requirements.
Do not commit local prompts, memory, transcripts or logs. Avoid returning secrets
in packets; never silently rewrite the authoritative prompt to hide that problem.

Capture user amendments as separately versioned, ordered source records, with
explicit supersession links; keep the original intact. A hash mismatch invalidates
old task packets/check evidence until the affected requirements are reviewed.
Derived summaries and plans reference the original and never replace it. On a
conflict or ambiguity, fetch the original span and ask for clarification rather
than inventing a weakened interpretation.

Create a requirement registry with:

```text
requirement_id, source_document_hash, source_lines, source_excerpt
category: objective | shared_constraint | acceptance
scope: all_tasks | selected_tasks
interpretation, extraction_mode: explicit | agent_inferred
acceptance_check_ids, clarification_status, supersedes_id
```

Extract shared requirements, prohibited actions, compatibility/security constraints
and acceptance criteria once. Every task references the applicable requirement
IDs and includes a compact shared-constraint block. Keep global interface decisions
in a versioned manifest; changes require revalidating dependent tasks. Include the
actual concise mandatory constraints, not merely opaque IDs that Codex cannot see.
Resolve proposed acceptance tests with the user/agent; do not invent product
requirements merely to make extraction easy.

### Deterministic versus agent-model planning

* **Deterministic helper work:** store/hash the original; enumerate headings,
  numbered/checklist items and explicit dependency declarations; preserve source
  spans; validate schema, IDs, DAG order, coverage references and size bounds.
  Mechanical extraction is not reliable semantic interpretation of arbitrary prose.
* **Semantic work by Codex:** interpret free-form shared constraints, infer sensible
  boundaries/dependencies, choose relevant acceptance criteria and resolve ambiguous
  requirements. Codex can propose the registry/plan using its existing model. This
  consumes the agent's allowance, even without a separately billed helper API.
* **Default:** keep a small/cohesive task unsplit. Explicit user sections can form
  a deterministic scaffold. For long multi-deliverable prompts, ask Codex to draft
  a compact plan, then validate it locally; label inferred interpretations. No
  background model call, automatic paid planner or recursive subdivision.

Length alone is not a reason to split. A one-file fix with one coherent acceptance
check can remain one task even with a long explanation. Split only when independent
deliverables, interfaces or staged acceptance make dependencies useful. Proposed
default ceiling: eight implementation tasks plus one final integration check;
exceeding it requires a deliberate revised plan, not silent extra subtasks.

### Required task and completion contracts

```text
TaskCard:
  task_id, objective, spec_hash/version
  relevant_requirement_ids + compact authoritative excerpts
  shared_constraint_ids + concise mandatory constraint text
  required_context_queries, relevant_files/ranges + reasons
  context_unknowns (unverified file guesses are labelled)
  depends_on, input_contracts, output_contracts
  acceptance_check_ids, manual_acceptance_criteria
  status: pending | ready | blocked | failed | complete

CompletionSummary:
  task_id, spec_hash/version, status
  concise changes and decisions; interface/input-output facts
  changed paths + hashes/revision; acceptance evidence and failures
  unresolved questions/risks; next-task implications
```

Require each requirement to map to a task or final check and each shared constraint
to map to all affected tasks. Reject missing IDs, cycles, self/unknown dependencies,
duplicate tasks and an integration task that does not depend on all implementation
tasks. Structural coverage cannot prove that semantic extraction found every
requirement; that is why original-text review remains mandatory.

Do not start dependent tasks before predecessor checks pass or an explicit,
recorded waiver changes their status. A concise completion summary supplies
interfaces and validation evidence to subsequent tasks, not the original prompt
or every changed file. Reopen relevant current source ranges after handoff rather
than trusting a stale summary. Store summaries as data, not executable instructions.

At task execution, deliver only its TaskCard, compact shared constraints, relevant
code/memory and necessary predecessor summaries. Give the original spec reference
and `read-spec` path for questions. Codex may reread the original when needed. In
a single conversation, the initial prompt can remain in Codex's internal history;
AgentForge cannot remove it, and not resending it is not proof of fewer billed tokens.

### Final integration against the original

For a split plan, add one final integration check dependent on all implementation
tasks. For an unsplit task, do the same review inline without creating needless
task objects. Codex checks the entire original specification and approved amendments
against the final repository state, including omitted or misinterpreted requirements
and cross-task interfaces. Reading the original again, if needed, counts as part of
the workflow's usage. Execute the agreed integration/regression checks and record
per-requirement `passed`, `failed`, `not_run`, `manual_review` or `blocked` evidence.
Completion is not accepted merely because all task summaries say done.

## 6. Concrete implementation work packages

The work-package design and dependency order are retained below. Implementation
completion handoffs follow the table. All work packages retain the shared constraints
in section 1: existing APIs preserved, local default, no helper model calls, bounded
outputs, no secrets in logs, mocked Redis tests and no Codex-budget-control claims.

| Task / objective and requirements | Context / relevant files | Dependencies | Acceptance checks | Completion handoff for subsequent work |
| --- | --- | --- | --- | --- |
| P1: Define independent helper/session/spec contracts and source-linked requirements | Read `types.py`, `utils.py`, `memory.py`, `decomposer.py`; add `assist/contracts.py`, `sessions.py`, `requirements.py`, schema fixtures | None | Original bytes/hash preserved; amendments versioned; missing/ambiguous requirements exposed; old contracts/data untouched; graph validation accepts single-task plans and rejects invalid DAGs | Contract/schema versions, storage paths, source-span convention and unresolved semantic questions |
| P2: Concise project memory and bounded relevant-source retrieval | Read `memory.py`, `compressor.py`, `config.py`, their tests; add `assist/memory.py`, `retrieval.py`, targeted tests | P1 | Local mode never constructs Redis/provider clients; old records readable; provenance/staleness handled; per-reply and aggregate scan limits enforced; exclusions/ignore overrides tested; no irrelevant padding; missing context explicit | Retrieval API, actual byte limits, ranking behavior, cache invalidation and memory compatibility decisions |
| P3: Repository-aware validation and focused feedback | Read `validator.py`, `artifacts.py`, existing validator tests; add `assist/validation.py`, `feedback.py`, approved-check fixtures | P1 | Syntax results separated from behavior; check catalog uses argv/timeouts with explicit execution; failures/partial logs bounded; no autonomous repair; validation operates in the intended repo/worktree | Check IDs, diagnostic schema, timeout/process handling and scope limits |
| P4: Long-prompt task packets, plan checking and handoffs | Read `decomposer.py`, `prompts.py`, P1-P3 APIs; add `assist/planning.py`, `packets.py`, decomposition fixtures | P1, P2, P3 | Shared constraints survive all tasks; source-linked requirement coverage; no whole-prompt/artifact repetition; small task remains unsplit; deterministic scaffolds labelled; agent proposals validated; dependencies and final integration enforced | Task/summary schema, readiness rules, original-spec access, coverage gaps and planning-cost provenance |
| P5: Codex skill and local helper CLI | Read `cli.py`, official skill docs and P1-P4 contracts; add `assist/cli.py`, `.agents/skills/agentforge-coding/SKILL.md` plus short references | P2, P3, P4 | Commands operate without model/Redis credentials; skill triggers deliberately; existing `run`/`serve` behavior preserved; complete local workflow demonstrable through mocked/manual fixtures; install instructions identify proposed vs shipped features | Invocation/setup procedure, supported Codex surface/version, command schema and remaining integration risks |
| P6: Regression protection and comparison instrumentation | Read tests, packaging checks, `.github/workflows/ci.yml`, usage docs; add `assist/metrics.py`, `scripts/compare_agent_runs.py`, evaluation protocol/fixtures | P5 | Offline/mocked suite, base installs and optional extras remain valid; logs detect missing/partial usage; comparison includes every stage and correctness; no benchmark agent call or Redis connection in CI | What was actually checked, benchmark manifests, usage-field coverage and pending authorized trials |

P1-P6 are staged implementation units, not a requirement to open six model sessions
or spawn subagents. Keep related changes together where that is simpler. Deliver
the skill/CLI path before proposing an optional STDIO MCP adapter; the latter
reuses service functions and adds no generation behavior. Future MCP tool candidates
are `prepare_task`, `search_code`, `read_spec`, `check_plan`, `validate_task` and
`record_completion`; writes and check execution are clearly labelled. MCP is deferred; no registration or new MCP dependency was added.

### Implemented completion handoffs

| Package | Completed output for subsequent work |
| --- | --- |
| P1 | Strict version-1 contracts; immutable private UTF-8 original/amendment snapshots with hashes; source-line registry; lock/atomic state; reviewed requirements invalidate prior plans/checks/handoffs |
| P2 | Separate `assist-v1` concise-memory namespace over existing backends; local default ignores Redis configuration; lexical bounded I/O/replies; nested ignore overrides, 60-line source provenance, stale/redacted data and missing-context flags |
| P3 | Repository validation in `validation.py` (feedback kept here instead of an extra module); approved argv catalogs, explicit execution, scoped source hashes, timeout/process cleanup, bounded redacted private logs, syntax versus manual/behavioral evidence |
| P4 | Default unsplit card; reviewed agent/explicit-section plan input; pure existing DAG validation, coverage/shared constraints, readiness, current evidence, compact predecessor summaries, final full-original attestation |
| P5 | `agentforge assist` JSON CLI alongside unchanged run/serve; canonical packaged skill and byte-identical repository mirror; explicit idempotent installer refusing custom overwrite; detailed schemas/workflow |
| P6 | Offline regressions, installed base/server workflow checks, skill resources in wheel/sdist; three-arm manifest preparation, existing-log numeric usage collection, incomplete measurements, correctness/rework and paired comparison tooling |

Semantic extraction/planning is performed by the coding agent, not automatically by
these deterministic helpers. No independent semantic completeness proof or benchmark
improvement is claimed. Command evidence tracks explicitly selected files, not every
possible dependency. Direct helper failures before a valid session and additional
Codex file reads are outside the helper log. Detailed limits and actual results are
in the linked workflow/report; future MCP and automatic execution remain deferred.

## 7. Fair comparison against an unsplit baseline

The approved pilot ran once per condition. See the report for observed increases
in usage and limits. The protocol below remains the design for future authorized
repetitions; no additional run is authorized by this document.
Design the experiment first, then run it only with explicit authorization to consume
the coding agent's allowance. FakeProvider can verify helper mechanics but cannot
establish real coding-agent quality, token savings or quota consumption.

### Paired experiment

Use the same fixed tasks, original prompts, acceptance criteria, base commit,
dependencies, fixtures, model/version, reasoning setting, sandbox/approvals, enabled
tools, agent version, network permissions and maximum operator correction policy.
Provide an identical initial memory snapshot to helper arms, or start all without
learned memory; do not let results from one arm leak into another. Use isolated
checkouts/worktrees and fresh conversations with no residual task state.

| Arm | Workflow | Purpose |
| --- | --- | --- |
| A | Codex with original prompt, ordinary tools, unsplit; no AgentForge skill/helpers | Product baseline |
| B | Same original prompt and Codex settings; AgentForge memory/context/validation, unsplit | Isolate helper/context effect |
| C | Same as B plus a reviewed split plan, focused task packets and final integration | Compare decomposition against the unsplit helper baseline and against A |

Set decomposition mode externally for B/C so differing agent choices do not make
the comparison ambiguous. Keep original requirements and test information available
to every arm. Disable helper skill activation in A; invocation differences are
the treatment, not different task content. Include small-task controls to detect
unnecessary splitting and overhead, along with long multi-file prompts, bug fixes,
interface changes and tasks with cross-cutting constraints. Proposed pilot: six
fixed tasks with three independent paired repetitions per arm; this is an initial
experimental design, not a power analysis or a measurement already performed.

Randomize/counterbalance arm order and record times, service version changes and
cache conditions. Cached-input differences can affect observed results. Evaluate
requirements/tests from the same frozen rubric, with a blind human review of
maintainability where practical. Use no paid model as a grader. Do not weaken
acceptance criteria to suit the derived task plan.

### Measurements and honest limits

| Quantity | Source / status |
| --- | --- |
| Helper response UTF-8 bytes, files/ranges read, helper calls, local durations | Directly measurable by local instrumentation; include metadata, repeated reads and failures |
| Input, cached-input, output and reasoning-output counters | Capture supported Codex usage events if the chosen client exposes them; retain fields with client/version and coverage metadata |
| Desktop/UI sessions without per-run counters | Report exact usage unavailable; use exposed usage summaries only at their supported granularity |
| Local token estimate | Optional labelled heuristic/tokenizer estimate, with method/version; never present bytes or `estimate_tokens` as actual Codex tokens |
| Subscription allowance/credit decrement, dollars, internal compaction allocation | Unavailable unless the client/account actually exposes an attributable measurement; do not infer from message counts or helper byte reduction |
| Correctness | Mandatory requirements satisfied, agreed tests, regressions and cross-task constraints; syntax pass alone is insufficient |
| Rework | Failed checks, repair/edit rounds, reopened tasks, integration fixes, operator interventions and time to accepted completion |

Official [Codex non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
describes `codex exec --json` and a `turn.completed` usage event with input,
cached-input, output and reasoning-output fields. That is a supported future
measurement route, not proof this session or every Codex surface supplies those
fields. The benchmark collector must validate its event schema/semantics against
the chosen client version and mark unavailable fields explicitly. Do not execute
`codex exec` during implementation or offline preparation or silently switch to paid API-key access to
obtain measurements.

Capture **the whole workflow**: initial prompt/skill loading, semantic extraction
and planning, retrieval calls and their outputs, each implementation task,
completion summaries, validation interpretation, repairs/retries, original-spec
rereads and final integration. New sessions/subagents, if explicitly used later,
must contribute their reported usage too. Where stages share one model turn, do
not invent a token allocation per stage; record full-turn totals and separate
observable stage events.

Sum only non-overlapping, schema-validated usage events across all turns/threads.
Do not add cached tokens again if they are included in reported input tokens, or
reasoning tokens again if included in output. Preserve raw reported categories;
derive a total only when field semantics are established. Mark cumulative/missing
events and incomplete transcripts as partial, not zero. A displayed app usage
percentage or message counter is not an exact per-task token count.

Compare paired end-to-end totals for C versus B (decomposition effect), B versus
A (helper effect), and C versus A (combined result). Show input/cache/output
separately, correctness pass rates and rework distributions; do not select only
the cheapest successful runs or omit failed runs. Report usage until the same
acceptance criteria are met, and record failures that reach the fixed correction
limit. Publish medians, paired differences and variability for the pilot without
claiming statistical certainty. A smaller context packet with equal or higher
overall usage is not token savings.

Adopt decomposition by default only if repeated paired observations support its
usefulness for the relevant task class without a correctness regression. If it
helps correctness but costs more allowance, say that. If measurements are missing,
state that savings are unestablished and retain an unsplit mode.

## 8. Decision for the first implementation

The approved implementation delivers a local skill plus `agentforge assist` helpers, with concise local memory,
bounded source retrieval, explicit checks and source-linked task plans. Semantic
planning is performed by Codex when needed and counted in evaluation. Preserve
all completed provider/server/Redis work. Defer MCP packaging, programmatic Codex
execution, publication and savings claims until authorized comparison trials. Runtime helpers and the skill are implemented;
no MCP registration, separate paid model API, Redis connection or package
publication occurred. The three authorized Codex allowance runs are recorded
separately; post-pilot helper corrections have only offline verification.
