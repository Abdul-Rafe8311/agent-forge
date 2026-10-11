"""Fresh base/server wheel and sdist checks; only dependency downloads use the network."""

import json
import os
import re
import subprocess
import sys
import tomllib
import venv
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ)
for key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_ADMIN_KEY",
    "REDIS_URL",
    "AGENTFORGE_SERVER_TOKEN",
):
    env.pop(key, None)
env["PYTHONNOUSERSITE"] = "1"
env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
env.pop("PYTHONPATH", None)


def run(command, cwd):
    completed = subprocess.run(
        [str(part) for part in command], cwd=cwd, env=env, capture_output=True, text=True
    )
    if completed.returncode:
        print(completed.stdout, end="", file=sys.stderr)
        print(completed.stderr, end="", file=sys.stderr)
        completed.check_returncode()
    if any(Path(str(part)).name == "check_installed.py" for part in command):
        print(completed.stdout, end="")


def find_artifacts(directory: Path, project: dict) -> tuple[Path, Path]:
    """Select this project's exact-version artifacts; reject missing/ambiguous wheel builds."""
    stem = re.sub(r"[-_.]+", "_", project["name"]).lower() + "-" + project["version"]
    wheels = sorted(directory.glob(stem + "-*.whl"))
    source = directory / (stem + ".tar.gz")
    if len(wheels) != 1 or not source.is_file():
        raise ValueError("Build exactly one matching wheel and sdist before checking installation")
    return wheels[0], source


def main():
    """Install the artifacts by absolute path outside checkout and test their real entry points."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wheel, source = find_artifacts(ROOT / "dist", project)
    with TemporaryDirectory(prefix="agentforge-distribution-") as directory:
        outside = Path(directory)
        for kind, artifact, server in (
            ("wheel", wheel, False),
            ("sdist", source, False),
            ("wheel-server", wheel, True),
            ("sdist-server", source, True),
        ):
            target = outside / kind
            venv.EnvBuilder(with_pip=True).create(target)
            binaries = target / ("Scripts" if os.name == "nt" else "bin")
            python = binaries / ("python.exe" if os.name == "nt" else "python")
            cli = binaries / ("agentforge.exe" if os.name == "nt" else "agentforge")
            requirement = str(artifact) + ("[server]" if server else "")
            run([python, "-m", "pip", "install", requirement], outside)
            run(
                [
                    python,
                    "-I",
                    ROOT / "scripts/check_installed.py",
                    project["name"],
                    project["version"],
                    *(["--server"] if server else []),
                ],
                outside,
            )
            run([cli, "--help"], outside)
            run([python, "-I", "-m", "agentforge", "--help"], outside)
            run([cli, "serve", "--help"], outside)
            data = subprocess.run(
                [
                    str(cli),
                    "run",
                    "--provider",
                    "fake",
                    "--model",
                    "fake",
                    "--task",
                    "fixture",
                    "--json",
                ],
                cwd=outside,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            assert json.loads(data.stdout)["success"] is True
            # All offline examples must run with only the base wheel, not optional extras.
            if kind == "wheel":
                for name in ("basic", "multi_step_project", "error_loop_demo", "decorator_demo"):
                    run([python, "-I", ROOT / "examples" / (name + ".py")], outside)
            print(kind + " installation/CLI checks passed")


if __name__ == "__main__":
    main()
