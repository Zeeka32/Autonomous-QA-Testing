import json
from pathlib import Path

from .plans import (
    ActionPlan,
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
    PlanValidationError,
    PressAction,
    SelectAction,
    TitleContainsAssertion,
    UrlContainsAssertion,
    UncheckAction,
    WaitForAction,
)


class PlanLoadError(ValueError):
    """Raised when a JSON action plan cannot be loaded or parsed."""


def _require_fields(
    raw_action: dict,
    expected_fields: set[str],
    step_number: int,
    item_name: str = "Step",
) -> None:
    actual_fields = set(raw_action)
    missing_fields = expected_fields - actual_fields
    extra_fields = actual_fields - expected_fields

    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise PlanLoadError(
            f"{item_name} {step_number} is missing fields: {missing}"
        )
    if extra_fields:
        extra = ", ".join(sorted(extra_fields))
        raise PlanLoadError(
            f"{item_name} {step_number} has unknown fields: {extra}"
        )


def _parse_action(raw_action: object, step_number: int):
    if not isinstance(raw_action, dict):
        raise PlanLoadError(f"Step {step_number} must be a JSON object")

    kind = raw_action.get("kind")

    try:
        if kind == "navigate":
            _require_fields(raw_action, {"kind", "url"}, step_number)
            return NavigateAction(url=raw_action["url"])
        if kind == "click":
            _require_fields(raw_action, {"kind", "selector"}, step_number)
            return ClickAction(selector=raw_action["selector"])
        if kind == "fill":
            _require_fields(
                raw_action,
                {"kind", "selector", "value"},
                step_number,
            )
            return FillAction(
                selector=raw_action["selector"],
                value=raw_action["value"],
            )
        if kind == "wait_for":
            _require_fields(raw_action, {"kind", "selector"}, step_number)
            return WaitForAction(selector=raw_action["selector"])
        if kind == "select":
            _require_fields(
                raw_action,
                {"kind", "selector", "value"},
                step_number,
            )
            return SelectAction(
                selector=raw_action["selector"],
                value=raw_action["value"],
            )
        if kind == "check":
            _require_fields(raw_action, {"kind", "selector"}, step_number)
            return CheckAction(selector=raw_action["selector"])
        if kind == "uncheck":
            _require_fields(raw_action, {"kind", "selector"}, step_number)
            return UncheckAction(selector=raw_action["selector"])
        if kind == "press":
            _require_fields(
                raw_action,
                {"kind", "selector", "key"},
                step_number,
            )
            return PressAction(
                selector=raw_action["selector"],
                key=raw_action["key"],
            )
    except PlanValidationError as error:
        raise PlanLoadError(f"Step {step_number}: {error}") from error

    raise PlanLoadError(f'Step {step_number} has unknown action kind: "{kind}"')


def _parse_assertion(raw_assertion: object, assertion_number: int):
    if not isinstance(raw_assertion, dict):
        raise PlanLoadError(
            f"Assertion {assertion_number} must be a JSON object"
        )

    kind = raw_assertion.get("kind")

    try:
        if kind == "url_contains":
            _require_fields(
                raw_assertion,
                {"kind", "value"},
                assertion_number,
                "Assertion",
            )
            return UrlContainsAssertion(value=raw_assertion["value"])
        if kind == "title_contains":
            _require_fields(
                raw_assertion,
                {"kind", "value"},
                assertion_number,
                "Assertion",
            )
            return TitleContainsAssertion(value=raw_assertion["value"])
        if kind == "element_visible":
            _require_fields(
                raw_assertion,
                {"kind", "selector"},
                assertion_number,
                "Assertion",
            )
            return ElementVisibleAssertion(
                selector=raw_assertion["selector"]
            )
        state_assertions = {
            "element_hidden": ElementHiddenAssertion,
            "element_enabled": ElementEnabledAssertion,
            "element_disabled": ElementDisabledAssertion,
            "element_checked": ElementCheckedAssertion,
            "element_unchecked": ElementUncheckedAssertion,
        }
        if kind in state_assertions:
            _require_fields(
                raw_assertion,
                {"kind", "selector"},
                assertion_number,
                "Assertion",
            )
            return state_assertions[kind](
                selector=raw_assertion["selector"]
            )
        if kind == "element_value_equals":
            _require_fields(
                raw_assertion,
                {"kind", "selector", "value"},
                assertion_number,
                "Assertion",
            )
            return ElementValueEqualsAssertion(
                selector=raw_assertion["selector"],
                value=raw_assertion["value"],
            )
        if kind == "element_count_equals":
            _require_fields(
                raw_assertion,
                {"kind", "selector", "count"},
                assertion_number,
                "Assertion",
            )
            return ElementCountEqualsAssertion(
                selector=raw_assertion["selector"],
                count=raw_assertion["count"],
            )
        if kind == "element_attribute_contains":
            _require_fields(
                raw_assertion,
                {"kind", "selector", "attribute", "value"},
                assertion_number,
                "Assertion",
            )
            return ElementAttributeContainsAssertion(
                selector=raw_assertion["selector"],
                attribute=raw_assertion["attribute"],
                value=raw_assertion["value"],
            )
        if kind == "element_text_contains":
            _require_fields(
                raw_assertion,
                {"kind", "selector", "value"},
                assertion_number,
                "Assertion",
            )
            return ElementTextContainsAssertion(
                selector=raw_assertion["selector"],
                value=raw_assertion["value"],
            )
    except PlanValidationError as error:
        raise PlanLoadError(
            f"Assertion {assertion_number}: {error}"
        ) from error

    raise PlanLoadError(
        f'Assertion {assertion_number} has unknown assertion kind: "{kind}"'
    )


def load_action_plan(path: Path) -> ActionPlan:
    try:
        raw_plan = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PlanLoadError(f'Could not read plan "{path}": {error}') from error
    except json.JSONDecodeError as error:
        raise PlanLoadError(
            f'Plan "{path}" contains invalid JSON at line {error.lineno}'
        ) from error

    if not isinstance(raw_plan, dict):
        raise PlanLoadError("plan must be a JSON object")
    if "actions" not in raw_plan:
        raise PlanLoadError('plan must contain an "actions" field')
    unknown_fields = set(raw_plan) - {"actions", "assertions"}
    if unknown_fields:
        unknown = ", ".join(sorted(unknown_fields))
        raise PlanLoadError(f"plan has unknown fields: {unknown}")
    if not isinstance(raw_plan["actions"], list):
        raise PlanLoadError('plan field "actions" must be a JSON array')
    raw_assertions = raw_plan.get("assertions", [])
    if not isinstance(raw_assertions, list):
        raise PlanLoadError('plan field "assertions" must be a JSON array')

    actions = tuple(
        _parse_action(raw_action, step_number)
        for step_number, raw_action in enumerate(raw_plan["actions"], start=1)
    )
    assertions = tuple(
        _parse_assertion(raw_assertion, assertion_number)
        for assertion_number, raw_assertion in enumerate(
            raw_assertions,
            start=1,
        )
    )

    try:
        return ActionPlan(actions=actions, assertions=assertions)
    except PlanValidationError as error:
        raise PlanLoadError(f"Invalid plan: {error}") from error
