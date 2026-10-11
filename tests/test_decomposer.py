import json

import pytest
from conftest import plan

from agentforge.decomposer import parse_plan
from agentforge.exceptions import PlanningFailedError


def test_stable_dependency_order():
    steps = json.loads(plan())["steps"]
    result = parse_plan(plan(list(reversed(steps))))
    assert [s.id for s in result.steps] == ["build", "integrate"]


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown", "self", "cycle", "no_integration", "too_many", "extra"]
)
def test_invalid_dependency_plans(mutation):
    steps = json.loads(plan())["steps"]
    if mutation == "duplicate":
        steps[1]["id"] = "build"
    if mutation == "unknown":
        steps[0]["depends_on"] = ["unknown"]
    if mutation == "self":
        steps[0]["depends_on"] = ["build"]
    if mutation == "cycle":
        steps[0]["depends_on"] = ["integrate"]
    if mutation == "no_integration":
        steps[1]["kind"] = "execute"
    if mutation == "extra":
        steps[0]["surprise"] = True
    with pytest.raises(PlanningFailedError):
        parse_plan(plan(steps), 1 if mutation == "too_many" else 10)


@pytest.mark.parametrize("text", ["prose {}", '{"steps":[]}', "{", "```json\n{}"])
def test_malformed_plan(text):
    with pytest.raises(PlanningFailedError):
        parse_plan(text)
