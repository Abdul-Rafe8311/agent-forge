"""JSON helper commands; no generation, API credentials, or automatic Redis selection."""

import time
from contextlib import suppress
from pathlib import Path

import typer
from pydantic import ValidationError

from .contracts import (
    Check,
    Completion,
    Contract,
    Limits,
    Plan,
    RelevantFile,
    Requirement,
    TaskCard,
)
from .packets import prepare as prepare_packet
from .packets import spec_page
from .planning import check_plan, final_review, task_for, task_status
from .planning import complete as complete_task
from .requirements import excerpt
from .retrieval import Repository
from .sessions import Session, amend, update_requirements
from .sessions import start as start_session
from .storage import AssistError, encoded, read_json, redact, response
from .validation import register_checks, render_feedback
from .validation import validate as validate_task

app = typer.Typer(
    no_args_is_help=True, help="Local context, project memory and task helpers; no model calls."
)
from .benchmark_cli import app as benchmark_app  # noqa: E402

app.add_typer(benchmark_app, name="benchmark")


@app.callback()
def options(
    ctx: typer.Context,
    project: Path = typer.Option(Path("."), "--project"),
    session: str | None = typer.Option(None, "--session"),
):
    ctx.obj = {"project": project.resolve(), "session": session}


def emit(value):
    typer.echo(encoded(value).decode())


def operation(ctx, name, worker, limit=20480, *, needs_session=True):
    started = time.monotonic()
    session = None

    def emit_error(value):
        output = response(value, limit)
        if session is not None:
            with suppress(OSError, AssistError, ValueError):
                session.event(
                    name, output, elapsed_ms=round((time.monotonic() - started) * 1000, 3)
                )
        emit(output)

    try:
        if needs_session:
            if not ctx.obj["session"]:
                raise AssistError("Provide --session before the helper subcommand")
            session = Session(ctx.obj["project"], ctx.obj["session"])
            with session.transaction() as state:
                output = response(worker(session, state), limit)
                session.event(
                    name,
                    output,
                    elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                    files_read=output.get("code", output).get("files_read", 0),
                    bytes_read=output.get("code", output).get("bytes_read", 0),
                )
        else:
            output = response(worker(None, None), limit)
        emit(output)
        if output.get("status") in (
            "overflow",
            "blocked",
            "failed",
            "stale",
            "review_required",
            "not_run",
            "manual_review",
        ):
            raise typer.Exit(1)
    except AssistError as error:
        emit_error({"status": "error", "code": error.code, "message": redact(str(error))})
        raise typer.Exit(2) from None
    except ValidationError as error:
        known_fields = {
            key
            for contract in (Check, Completion, Limits, Plan, RelevantFile, Requirement, TaskCard)
            for key in contract.model_fields
        }
        issues = [
            {
                "field": [
                    part if type(part) is int or part in known_fields else "unrecognized_field"
                    for part in issue["loc"]
                ],
                "kind": issue["type"],
            }
            for issue in error.errors(include_input=False, include_url=False)[:5]
        ]
        emit_error(
            {
                "status": "error",
                "code": "invalid_schema",
                "message": "Check these fields against assist schema; input values withheld",
                "validation_issues": issues,
                "omitted_issues": max(0, error.error_count() - 5),
            }
        )
        raise typer.Exit(2) from None
    except (OSError, ValueError, KeyError, TypeError):
        emit_error(
            {
                "status": "error",
                "code": "invalid_input",
                "message": "Invalid input or unreadable private storage; details withheld",
            }
        )
        raise typer.Exit(2) from None


@app.command("start")
def start_command(
    ctx: typer.Context,
    prompt_file: Path = typer.Option(..., "--prompt-file"),
    memory_backend: str = typer.Option("local", "--memory-backend"),
    limits_file: Path | None = typer.Option(None, "--limits-file"),
):
    def work(_session, _state):
        limits = Limits(**(read_json(limits_file) if limits_file else {}))
        session = start_session(
            ctx.obj["project"],
            prompt_file,
            memory_backend=memory_backend,
            limits=limits.model_dump(),
        )
        with session.transaction() as state:
            output = response(
                {
                    "status": "ok",
                    "session": session.id,
                    "spec_hash": state["spec_hash"],
                    "plan_version": state["plan_version"],
                    "requirements": len(state["requirements"]),
                    "default_task": "task",
                    "memory_backend": memory_backend,
                    "original_preserved_verbatim": True,
                    "extraction": "mechanical scaffold; semantic review still required",
                }
            )
            session.event("start", output)
            return output

    operation(ctx, "start", work, needs_session=False)


@app.command("amend")
def amend_command(ctx: typer.Context, prompt_file: Path = typer.Option(..., "--prompt-file")):
    def work(session, state):
        amend(session, state, prompt_file)
        return {
            "status": "ok",
            "spec_hash": state["spec_hash"],
            "spec_version": state["spec_version"],
            "plan_version": state["plan_version"],
            "notice": "Prior plan and evidence invalidated; original retained",
        }

    operation(ctx, "amend", work)


@app.command("requirements")
def requirements_command(
    ctx: typer.Context,
    file: Path | None = typer.Option(None, "--file"),
    reviewed: bool = typer.Option(False, "--reviewed"),
    offset: int = 0,
    show_records: bool = False,
):
    def work(session, state):
        if file or reviewed:
            values = read_json(file) if file else state["requirements"]
            if reviewed:
                values = [
                    {**r, "clarification_status": "resolved"}
                    if r.get("clarification_status") != "needs_clarification"
                    else r
                    for r in values
                ]
            update_requirements(session, state, values)
            if not show_records:
                return {
                    "status": "ok",
                    "requirements_updated": len(state["requirements"]),
                    "spec_hash": state["spec_hash"],
                    "plan_version": state["plan_version"],
                    "pending_review": sum(
                        r["clarification_status"] != "resolved" for r in state["requirements"]
                    ),
                    "notice": "Original requirements retained; read requirements for records",
                }
        if offset < 0 or offset > len(state["requirements"]):
            raise AssistError("Invalid requirement offset")
        documents = session.documents(state)
        selected: list[dict] = []
        for value in state["requirements"][offset:]:
            item = {
                **value,
                "source_preview": redact(excerpt(Requirement(**value), documents))[:160],
            }
            if len(encoded(selected + [item])) > 6500:
                break
            selected.append(item)
        next_offset = offset + len(selected)
        return {
            "status": "ok",
            "requirements": selected,
            "offset": offset,
            "next_offset": next_offset if next_offset < len(state["requirements"]) else None,
            "truncated": next_offset < len(state["requirements"]),
            "spec_hash": state["spec_hash"],
            "plan_version": state["plan_version"],
            "notice": "Source previews are abbreviated; use read-spec for authoritative text",
        }

    operation(ctx, "requirements", work, 8192)


@app.command("read-spec")
def read_spec(
    ctx: typer.Context, document: str = "original", requirement: str | None = None, offset: int = 0
):
    operation(
        ctx,
        "read-spec",
        lambda session, state: spec_page(
            session, state, document=document, requirement=requirement, offset=offset
        ),
        8192,
    )


@app.command("checks")
def checks_command(
    ctx: typer.Context,
    file: Path | None = None,
    approve_commands: bool = False,
    show_records: bool = False,
):
    def work(_session, state):
        if file:
            register_checks(state, read_json(file), approve_commands=approve_commands)
            if not show_records:
                return {
                    "status": "ok",
                    "checks_registered": len(state["checks"]),
                    "plan_version": state["plan_version"],
                    "commands_approved": state["commands_approved"],
                }
        return {
            "status": "ok",
            "checks": state["checks"],
            "plan_version": state["plan_version"],
            "commands_approved": state["commands_approved"],
        }

    operation(ctx, "checks", work)


@app.command("plan-check")
def plan_command(ctx: typer.Context, plan_file: Path | None = None):
    def work(session, state):
        if plan_file:
            check_plan(state, read_json(plan_file))
            return {
                "status": "ok",
                "spec_hash": state["spec_hash"],
                "plan_version": state["plan_version"],
                "ordered_task_ids": [t["id"] for t in state["plan"]["tasks"]],
                "notice": "Plan installed; use prepare for task context or plan-check to inspect",
            }
        return {
            "status": "ok",
            "plan": state["plan"],
            "plan_version": state["plan_version"],
            "task_statuses": {
                t.id: task_status(session, state, t) for t in Plan(**state["plan"]).tasks
            },
            "notice": "Agent planning uses its allowance; helpers make no model calls",
        }

    operation(ctx, "plan-check", work)


@app.command("prepare")
def prepare_command(ctx: typer.Context, task: str = "task"):
    operation(
        ctx, "prepare", lambda session, state: prepare_packet(session, state, task_for(state, task))
    )


@app.command("search")
def search_command(
    ctx: typer.Context,
    query: str = typer.Option(..., "--query"),
    file: list[str] = typer.Option([], "--file"),
    include_code: bool = False,
):
    def work(session, state):
        repository = Repository(session.root, Limits(**state["limits"]))
        result = repository.retrieve(
            query, [RelevantFile(path=path) for path in file], metadata_only=not include_code
        )
        result["status"] = "ok"
        result["truncated"] = result["truncated"] or False
        limit = 16384 if include_code else 4096
        while len(encoded(result)) + 100 > limit and result["chunks"]:
            result["chunks"].pop()
            result["omitted_chunks"] += 1
            result["truncated"] = True
        return result

    operation(ctx, "search", work, 16384 if include_code else 4096)


@app.command("context")
def context_command(
    ctx: typer.Context,
    query: str = typer.Option(..., "--query"),
    file: list[str] = typer.Option([], "--file"),
    max_bytes: int = typer.Option(4096, min=1024, max=16384),
    max_chunks: int = typer.Option(3, min=1, max=6),
    start_line: int | None = None,
    end_line: int | None = None,
):
    """Retrieve bounded source without a session, plan or memory writes."""
    from .context import context

    operation(
        ctx,
        "context",
        lambda _session, _state: context(
            ctx.obj["project"],
            query,
            file,
            max_bytes=max_bytes,
            max_chunks=max_chunks,
            start_line=start_line,
            end_line=end_line,
        ),
        max_bytes,
        needs_session=False,
    )


@app.command("validate")
def validate_command(
    ctx: typer.Context,
    task: str = "task",
    check: str = "syntax",
    execute: bool = False,
    file: list[str] = typer.Option([], "--file"),
    manual_status: str | None = None,
    note: str = "",
):
    operation(
        ctx,
        "validate",
        lambda session, state: render_feedback(
            validate_task(
                session,
                state,
                task_for(state, task),
                check,
                execute=execute,
                files=file,
                manual_status=manual_status,
                note=note,
            )
        ),
        4096,
    )


@app.command("complete")
def complete_command(
    ctx: typer.Context, task: str = "task", summary_file: Path | None = None, show: bool = False
):
    def work(session, state):
        if show:
            return {"status": "ok", "completion": state["completions"].get(task)}
        if not summary_file:
            raise AssistError("Provide --summary-file")
        result = complete_task(session, state, task_for(state, task), read_json(summary_file))
        return {
            "status": result["status"],
            "task_id": task,
            "handoff_saved": True,
            "warning": result["warning"],
        }

    operation(ctx, "complete", work)


@app.command("final-check")
def final_command(ctx: typer.Context, review_original: bool = False, note: str = ""):
    operation(
        ctx,
        "final-check",
        lambda session, state: final_review(session, state, reviewed=review_original, note=note),
    )


@app.command("schema")
def schema_command(ctx: typer.Context, kind: str = "plan"):
    contracts: dict[str, type[Contract]] = {
        "plan": Plan,
        "requirement": Requirement,
        "check": Check,
        "completion": Completion,
        "limits": Limits,
    }

    def work(_session, _state):
        if kind not in contracts:
            raise AssistError("Unknown schema kind")
        return {"status": "ok", "schema": contracts[kind].model_json_schema()}

    operation(ctx, "schema", work, needs_session=False)


@app.command("install-skill")
def install_skill_command(
    ctx: typer.Context,
    destination: Path = typer.Option(..., "--destination"),
    replace_existing: bool = typer.Option(
        False, "--replace-existing", help="Replace only packaged skill files after inspection."
    ),
):
    from .skill_install import install

    operation(
        ctx,
        "install-skill",
        lambda _session, _state: install(destination, replace_existing=replace_existing),
        needs_session=False,
    )
