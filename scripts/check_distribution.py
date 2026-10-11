"""Fresh base wheel/sdist installation checks. Dependency downloads only; no provider calls."""

import json
import os
import subprocess
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
env.pop("PYTHONPATH", None)


def run(command, cwd):
    subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)


def main():
    """Install the artifacts by absolute path outside checkout and test their real entry points."""
    wheel = next((ROOT / "dist").glob("agentforge-*.whl"))
    source = next((ROOT / "dist").glob("agentforge-*.tar.gz"))
    with TemporaryDirectory(prefix="agentforge-distribution-") as directory:
        outside = Path(directory)
        for kind, artifact in (("wheel", wheel), ("sdist", source)):
            target = outside / kind
            venv.EnvBuilder(with_pip=True).create(target)
            binaries = target / ("Scripts" if os.name == "nt" else "bin")
            python = binaries / ("python.exe" if os.name == "nt" else "python")
            cli = binaries / ("agentforge.exe" if os.name == "nt" else "agentforge")
            run([python, "-m", "pip", "install", artifact], outside)
            run([python, "-I", ROOT / "scripts/check_installed.py"], outside)
            run([cli, "--help"], outside)
            run([python, "-I", "-m", "agentforge", "--help"], outside)
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
