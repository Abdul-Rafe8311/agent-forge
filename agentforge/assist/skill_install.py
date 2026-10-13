"""Explicit installation of packaged skill resources; existing custom skills are preserved."""

from importlib.resources import files
from pathlib import Path

from .storage import AssistError, digest, private_dir, read_bytes, write_private


def install(destination: Path, *, replace_existing=False):
    source = files("agentforge.assist").joinpath("skill")
    pending = []

    def walk(resource, parts=()):
        for child in resource.iterdir():
            relative = (*parts, child.name)
            if child.is_dir():
                walk(child, relative)
            else:
                data = child.read_bytes()
                target = destination.joinpath(*relative)
                if any(parent.is_symlink() for parent in [target, *target.parents]):
                    raise AssistError("Skill installation symlinks are refused", "unsafe_path")
                if target.exists() or target.is_symlink():
                    if digest(read_bytes(target)) != digest(data) and not replace_existing:
                        raise AssistError(
                            "Destination has a different skill; choose another destination"
                        )
                pending.append((target, data))

    walk(source)
    private_dir(destination)
    for target, data in pending:
        if replace_existing or not target.exists():
            write_private(target, data, immutable=not target.exists())
    return {
        "status": "ok",
        "destination": str(destination),
        "files": len(pending),
        "invocation": "$agentforge-coding",
        "notice": "No Codex settings or model runs changed",
    }
