"""Typer CLI with lazy optional serving and safe status/exit semantics."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .config import AgentConfig
from .core import AgentWrapper
from .exceptions import AgentForgeError, ConfigurationError

app = typer.Typer(no_args_is_help=True)


def _version(value: bool):
    if value:
        typer.echo("AgentForge " + __version__)
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
):
    """Orchestrate coding workflows or start the private single-project server."""


@app.command()
def run(
    model: Annotated[str, typer.Option("--model")],
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    task: Annotated[str | None, typer.Option("--task")] = None,
    task_file: Annotated[Path | None, typer.Option("--task-file")] = None,
    memory: bool = False,
    memory_backend: str = "local",
    memory_path: Path | None = None,
    redis_url: str | None = None,
    project_id: str | None = None,
    decompose: bool = False,
    max_steps: int = 10,
    error_loop: bool = False,
    max_retries: int = 3,
    token_budget: int = 50000,
    fallback_model: str | None = None,
    fallback_provider: str | None = None,
    fallback_threshold: float = 0.8,
    strict_budget: bool = False,
    compress_context: bool = False,
    codebase_path: Path | None = None,
    model_context_limit: int | None = None,
    fallback_context_limit: int | None = None,
    max_output_tokens: int = 4096,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    output_dir: Path | None = None,
    overwrite: bool = False,
):
    """Generate accepted artifacts; files are written only through an explicit output directory."""
    try:
        if (task is None) == (task_file is None):
            raise ConfigurationError("Choose exactly one of --task or --task-file")
        instruction = task
        if instruction is None:
            assert task_file is not None
            instruction = task_file.read_text(encoding="utf-8")
        with AgentWrapper(
            model,
            provider=provider,
            memory=memory,
            memory_backend=memory_backend,
            memory_path=memory_path,
            redis_url=redis_url,
            project_id=project_id,
            task_decompose=decompose,
            max_steps=max_steps,
            error_loop=error_loop,
            max_retries=max_retries,
            token_budget=token_budget,
            fallback_model=fallback_model,
            fallback_provider=fallback_provider,
            fallback_threshold=fallback_threshold,
            strict_budget=strict_budget,
            context_compression=compress_context,
            codebase_path=codebase_path,
            model_context_limit=model_context_limit,
            fallback_context_limit=fallback_context_limit,
            max_output_tokens=max_output_tokens,
        ) as wrapper:
            result = wrapper.run(instruction)
        exits = {
            "success": 0,
            "context_limit_exceeded": 2,
            "budget_exceeded": 3,
            "validation_failed": 4,
            "planning_failed": 4,
            "provider_error": 5,
            "memory_error": 5,
        }
        code = exits[result.status]
        if output_dir is not None and result.success:
            try:
                result.write_to(output_dir, overwrite=overwrite)
            except (AgentForgeError, OSError):
                result.warnings.append("Requested artifact export failed")
                code = 5
        typer.echo(json.dumps(result.to_dict()) if json_output else result.code)
        typer.echo(
            f"{result.status}; {result.tokens_used} {result.token_usage.accounting} tokens",
            err=True,
        )
        for warning in result.warnings:
            typer.echo(warning, err=True)
        for error in result.errors:
            typer.echo(error, err=True)
        raise typer.Exit(code)
    except (ConfigurationError, OSError) as exc:
        typer.echo(
            str(exc) if isinstance(exc, ConfigurationError) else "Input file could not be read",
            err=True,
        )
        raise typer.Exit(2) from exc


@app.command()
def serve(
    model: Annotated[str, typer.Option("--model")],
    provider: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    project_id: str | None = None,
    memory: bool = False,
    memory_backend: str = "local",
    decompose: bool = False,
    error_loop: bool = False,
    token_budget: int = 50000,
    model_context_limit: int | None = None,
    max_output_tokens: int = 4096,
    codebase_path: Path | None = None,
    compress_context: bool = False,
):
    """Start the authenticated single-project server with one worker and no automatic reload."""
    try:
        token = os.environ.get("AGENTFORGE_SERVER_TOKEN")
        if not token:
            raise ConfigurationError("Set AGENTFORGE_SERVER_TOKEN privately before serving")
        try:
            import uvicorn

            from .server import ServerConfig, create_app
        except ImportError as exc:
            raise ConfigurationError(
                'Install "agentforge[server]" (checkout: pip install -e ".[server]")'
            ) from exc
        agent = AgentConfig(
            model=model,
            provider=provider,
            project_id=project_id,
            memory=memory,
            memory_backend=memory_backend,
            task_decompose=decompose,
            error_loop=error_loop,
            token_budget=token_budget,
            model_context_limit=model_context_limit,
            max_output_tokens=max_output_tokens,
            codebase_path=codebase_path,
            context_compression=compress_context,
        )
        config = ServerConfig(agent, token, host, port)
        config.validate_settings()
        uvicorn.run(create_app(config), host=host, port=port, workers=1, reload=False)
    except ConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


def main() -> None:
    """Console entry point; no server or provider client is initialized for help."""
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(130)
