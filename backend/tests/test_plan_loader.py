import json
from pathlib import Path

import pytest

from autonomous_qa.plan_loader import PlanLoadError, load_action_plan
from autonomous_qa.plans import (
    CheckAction,
    ClickAction,
    ElementAttributeContainsAssertion,
    ElementCheckedAssertion,
    ElementCountEqualsAssertion,
    ElementDisabledAssertion,
    ElementEnabledAssertion,
    ElementHiddenAssertion,
    ElementTextContainsAssertion,
    ElementUncheckedAssertion,
    ElementValueEqualsAssertion,
    ElementVisibleAssertion,
    FillAction,
    NavigateAction,
    PressAction,
    SelectAction,
    TitleContainsAssertion,
    UrlContainsAssertion,
    UncheckAction,
    WaitForAction,
)


def write_plan(tmp_path: Path, content: object) -> Path:
    path = tmp_path / "plan.json"
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_loads_a_valid_action_plan(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {"kind": "navigate", "url": "https://example.com"},
                {"kind": "fill", "selector": "#search", "value": "QA"},
                {"kind": "click", "selector": "#submit"},
                {"kind": "wait_for", "selector": "#results"},
                {"kind": "select", "selector": "#country", "value": "eg"},
                {"kind": "check", "selector": "#terms"},
                {"kind": "uncheck", "selector": "#newsletter"},
                {"kind": "press", "selector": "#search", "key": "Enter"},
            ]
        },
    )

    plan = load_action_plan(path)

    assert isinstance(plan.actions[0], NavigateAction)
    assert isinstance(plan.actions[1], FillAction)
    assert isinstance(plan.actions[2], ClickAction)
    assert isinstance(plan.actions[3], WaitForAction)
    assert isinstance(plan.actions[4], SelectAction)
    assert isinstance(plan.actions[5], CheckAction)
    assert isinstance(plan.actions[6], UncheckAction)
    assert isinstance(plan.actions[7], PressAction)
    assert plan.assertions == ()


def test_rejects_an_unsupported_press_key(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {"kind": "navigate", "url": "https://example.com"},
                {"kind": "press", "selector": "#search", "key": "F12"},
            ]
        },
    )

    with pytest.raises(PlanLoadError, match="press key"):
        load_action_plan(path)


def test_loads_a_plan_with_a_url_assertion(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {"kind": "navigate", "url": "https://example.com"}
            ],
            "assertions": [
                {"kind": "url_contains", "value": "example.com"}
            ],
        },
    )

    plan = load_action_plan(path)

    assert plan.assertions == (
        UrlContainsAssertion(value="example.com"),
    )


def test_loads_title_and_element_assertions(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {"kind": "navigate", "url": "https://example.com"}
            ],
            "assertions": [
                {"kind": "title_contains", "value": "Example"},
                {"kind": "element_visible", "selector": "h1"},
                {"kind": "element_hidden", "selector": "#spinner"},
                {"kind": "element_enabled", "selector": "#submit"},
                {"kind": "element_disabled", "selector": "#cancel"},
                {"kind": "element_checked", "selector": "#terms"},
                {
                    "kind": "element_unchecked",
                    "selector": "#newsletter",
                },
                {
                    "kind": "element_value_equals",
                    "selector": "#name",
                    "value": "Ada",
                },
                {
                    "kind": "element_count_equals",
                    "selector": ".result",
                    "count": 3,
                },
                {
                    "kind": "element_attribute_contains",
                    "selector": "#status",
                    "attribute": "class",
                    "value": "complete",
                },
                {
                    "kind": "element_text_contains",
                    "selector": "#result",
                    "value": "Complete",
                },
            ],
        },
    )

    plan = load_action_plan(path)

    assert plan.assertions == (
        TitleContainsAssertion(value="Example"),
        ElementVisibleAssertion(selector="h1"),
        ElementHiddenAssertion(selector="#spinner"),
        ElementEnabledAssertion(selector="#submit"),
        ElementDisabledAssertion(selector="#cancel"),
        ElementCheckedAssertion(selector="#terms"),
        ElementUncheckedAssertion(selector="#newsletter"),
        ElementValueEqualsAssertion(selector="#name", value="Ada"),
        ElementCountEqualsAssertion(selector=".result", count=3),
        ElementAttributeContainsAssertion(
            selector="#status",
            attribute="class",
            value="complete",
        ),
        ElementTextContainsAssertion(
            selector="#result",
            value="Complete",
        ),
    )


def test_rejects_invalid_json(tmp_path: Path) -> None:
    path = write_plan(tmp_path, '{"actions": [}')

    with pytest.raises(PlanLoadError, match="invalid JSON"):
        load_action_plan(path)


def test_rejects_unknown_action_kinds(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {"actions": [{"kind": "run_python", "code": "print('unsafe')"}]},
    )

    with pytest.raises(PlanLoadError, match="unknown action kind"):
        load_action_plan(path)


def test_rejects_missing_action_fields(tmp_path: Path) -> None:
    path = write_plan(tmp_path, {"actions": [{"kind": "navigate"}]})

    with pytest.raises(PlanLoadError, match="missing fields: url"):
        load_action_plan(path)


def test_rejects_extra_action_fields(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {
                    "kind": "navigate",
                    "url": "https://example.com",
                    "code": "unexpected",
                }
            ]
        },
    )

    with pytest.raises(PlanLoadError, match="unknown fields: code"):
        load_action_plan(path)


def test_rejects_wrong_field_types(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {"actions": [{"kind": "navigate", "url": 42}]},
    )

    with pytest.raises(PlanLoadError, match="URL must be a string"):
        load_action_plan(path)


def test_rejects_unknown_assertion_kinds(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {"kind": "navigate", "url": "https://example.com"}
            ],
            "assertions": [{"kind": "title_equals", "value": "Example"}],
        },
    )

    with pytest.raises(PlanLoadError, match="unknown assertion kind"):
        load_action_plan(path)


def test_rejects_missing_assertion_fields(tmp_path: Path) -> None:
    path = write_plan(
        tmp_path,
        {
            "actions": [
                {"kind": "navigate", "url": "https://example.com"}
            ],
            "assertions": [{"kind": "url_contains"}],
        },
    )

    with pytest.raises(
        PlanLoadError,
        match="Assertion 1 is missing fields: value",
    ):
        load_action_plan(path)
