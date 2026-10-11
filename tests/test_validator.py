import sys

import pytest
from conftest import generation

from agentforge.exceptions import ValidationFailedError
from agentforge.types import CodeArtifact
from agentforge.validator import CommandValidator, PythonSyntaxValidator, parse_generation


@pytest.mark.parametrize(
    "text",
    [
        "bad",
        '{"artifacts":[],"explanation":"x"}',
        '{"artifacts":[{"path":"a.py","content":42,"language":"python"}],"explanation":"x"}',
        generation().replace('"explanation"', '"unexpected"'),
        generation(path="../escape.py"),
    ],
)
def test_strict_generation_parsing(text):
    with pytest.raises(ValidationFailedError):
        parse_generation(text)


def test_fenced_object_and_duplicate_json_keys():
    assert parse_generation("```json\n" + generation() + "\n```")[0][0].path == "app.py"
    with pytest.raises(ValidationFailedError):
        parse_generation('{"artifacts":[],"artifacts":[]}')


def test_syntax_only_and_nonpython_structure_scope():
    validator = PythonSyntaxValidator()
    assert validator.validate([CodeArtifact("app.py", "import missing_module")]).passed
    failure = validator.validate([CodeArtifact("app.py", "def bad(:")])
    assert not failure.passed and failure.issues[0].line == 1
    result = validator.validate([CodeArtifact("app.js", "arbitrary language source", "javascript")])
    assert result.passed and "structure-only" in result.diagnostics


def test_optin_command_validation_exit_timeout_and_bounded_diagnostics():
    artifacts = [CodeArtifact("app.py", "x=1")]
    assert CommandValidator([sys.executable, "-c", "print('ok')"]).validate(artifacts).passed
    assert (
        not CommandValidator([sys.executable, "-c", "raise SystemExit(2)"])
        .validate(artifacts)
        .passed
    )
    result = CommandValidator([sys.executable, "-c", "import time; time.sleep(1)"], 0.02).validate(
        artifacts
    )
    assert not result.passed and result.issues[0].kind == "timeout"


def test_command_output_capture_is_bounded():
    result = CommandValidator(
        [sys.executable, "-c", "import sys; print('a'*100000); sys.stderr.write('b'*100000)"]
    ).validate([CodeArtifact("app.py", "x=1")])
    assert result.passed and len(result.diagnostics) <= 16384
