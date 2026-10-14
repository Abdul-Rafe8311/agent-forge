"""Offline benchmark preparation and collection commands."""

from pathlib import Path

import typer

from .metrics import collect_run, compare, prepare_benchmark
from .storage import encoded, read_json, write_private

app = typer.Typer(
    no_args_is_help=True,
    help="Prepare matched comparisons or read existing results; never run a coding agent.",
)


@app.command("prepare")
def prepare_command(
    ctx: typer.Context,
    tasks_file: Path = typer.Option(..., "--tasks-file"),
    settings_file: Path = typer.Option(..., "--settings-file"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    replicates: int = 1,
    workflow: str = typer.Option("tracked", help="tracked: A/B/C; context: ordinary A/context B"),
):
    from .cli import operation

    operation(
        ctx,
        "benchmark-prepare",
        lambda _session, _state: prepare_benchmark(
            read_json(tasks_file),
            read_json(settings_file),
            output_dir,
            replicates,
            workflow=workflow,
        ),
        needs_session=False,
    )


@app.command("collect")
def collect_command(
    ctx: typer.Context,
    manifest_file: Path = typer.Option(..., "--manifest-file"),
    outcome_file: Path = typer.Option(..., "--outcome-file"),
    output_file: Path = typer.Option(..., "--output-file"),
    log: list[Path] = typer.Option([], "--log"),
    helper_log: Path | None = None,
):
    from .cli import operation

    def work(_session, _state):
        result = collect_run(read_json(manifest_file), log, read_json(outcome_file), helper_log)
        write_private(output_file, encoded(result))
        return {
            "status": "ok",
            "output_file": str(output_file),
            "usage": result["usage"],
            "helpers": result["helpers"],
            "agent_runs_launched": 0,
        }

    operation(ctx, "benchmark-collect", work, needs_session=False)


@app.command("compare")
def compare_command(ctx: typer.Context, result: list[Path] = typer.Option(..., "--result")):
    from .cli import operation

    operation(
        ctx,
        "benchmark-compare",
        lambda _session, _state: compare([read_json(path) for path in result]),
        needs_session=False,
    )
