from dataclasses import FrozenInstanceError

import pytest

from autonomous_qa.models import ActionResult, CheckResult, PageSnapshot


@pytest.mark.parametrize(
    "model",
    [
        PageSnapshot(url="https://example.com", status=200, title="Example"),
        ActionResult(
            step_number=1,
            kind="navigate",
            status="passed",
            duration_ms=1.5,
            url_before="about:blank",
            url_after="https://example.com",
            message="Navigation completed",
        ),
        CheckResult(name="Page title", passed=True, message="Title is present"),
    ],
)
def test_models_are_immutable(model) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(model, next(iter(model.__dataclass_fields__)), "changed")
