"""Mechanical source-span scaffolds, not semantic understanding of prose."""

import re

from .contracts import Requirement
from .storage import AssistError


def scaffold(text: str, document="original", first_id=1):
    lines = text.splitlines()
    spans = []
    start = None
    for index, line in enumerate(lines, 1):
        if line.strip():
            if start is None:
                start = index
            elif re.match(r"\s*(?:[-*]|\d+[.)])\s", line):
                spans.append((start, index - 1))
                start = index
        elif start is not None:
            spans.append((start, index - 1))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    if not spans:
        raise AssistError("Specification must contain nonblank text")
    return [
        Requirement(id=f"R{first_id + i}", document=document, start_line=a, end_line=b)
        for i, (a, b) in enumerate(spans)
    ]


def excerpt(requirement, documents):
    lines = documents[requirement.document].splitlines()
    if requirement.end_line < requirement.start_line or requirement.end_line > len(lines):
        raise AssistError("Requirement source range is invalid")
    text = "\n".join(lines[requirement.start_line - 1 : requirement.end_line])
    if not text.strip():
        raise AssistError("Requirement source range is empty")
    return text


def active_requirements(requirements):
    superseded = {r for req in requirements for r in req.supersedes}
    return [r for r in requirements if r.id not in superseded]
