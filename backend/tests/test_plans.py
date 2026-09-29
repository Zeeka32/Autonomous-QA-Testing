import pytest

from autonomous_qa.plans import (
    ALLOWED_PRESS_KEYS,
    MAX_PLAN_ACTIONS,
    ActionPlan,
    CheckAction,
    ClickAction,
    CompletionCriteria,
    CriteriaSource,
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


def test_plan_accepts_supported_actions() -> None:
    plan = ActionPlan(
        actions=(
            NavigateAction(url="https://example.com"),
            FillAction(selector="#search", value="QA testing"),
            ClickAction(selector="button[type=submit]"),
            WaitForAction(selector="#results"),
            SelectAction(selector="#country", value="eg"),
            CheckAction(selector="#terms"),
            UncheckAction(selector="#newsletter"),
            PressAction(selector="#search", key="Enter"),
        )
    )

    assert len(plan.actions) == 8


def test_plan_accepts_supported_assertions() -> None:
    plan = ActionPlan(
        actions=(NavigateAction(url="https://example.com"),),
        assertions=(
            UrlContainsAssertion(value="example.com"),
            TitleContainsAssertion(value="Example"),
            ElementVisibleAssertion(selector="h1"),
            ElementHiddenAssertion(selector="#spinner"),
            ElementEnabledAssertion(selector="#submit"),
            ElementDisabledAssertion(selector="#cancel"),
            ElementCheckedAssertion(selector="#terms"),
            ElementUncheckedAssertion(selector="#newsletter"),
            ElementValueEqualsAssertion(
                selector="#name",
                value="Ada",
            ),
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
        ),
    )

    assert plan.assertions == (
        UrlContainsAssertion(value="example.com"),
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


@pytest.mark.parametrize(
    "url",
    ["", "example.com", "ftp://example.com", "not-a-url"],
)
def test_navigation_requires_an_absolute_http_url(url: str) -> None:
    with pytest.raises(PlanValidationError):
        NavigateAction(url=url)


@pytest.mark.parametrize(
    "action",
    [
        ClickAction,
        lambda selector: FillAction(selector=selector, value="text"),
        WaitForAction,
        lambda selector: SelectAction(selector=selector, value="eg"),
        CheckAction,
        UncheckAction,
        lambda selector: PressAction(selector=selector, key="Enter"),
    ],
)
def test_element_actions_reject_blank_selectors(action) -> None:
    with pytest.raises(PlanValidationError):
        action("   ")


def test_plan_must_not_be_empty() -> None:
    with pytest.raises(PlanValidationError, match="at least one"):
        ActionPlan(actions=())


def test_plan_has_a_step_limit() -> None:
    actions = tuple(
        ClickAction(selector=f"#button-{index}")
        for index in range(MAX_PLAN_ACTIONS + 1)
    )

    with pytest.raises(PlanValidationError, match="more than"):
        ActionPlan(actions=actions)


def test_plan_rejects_unknown_action_types() -> None:
    with pytest.raises(PlanValidationError, match="unsupported"):
        ActionPlan(actions=(object(),))


def test_plan_must_begin_with_navigation() -> None:
    with pytest.raises(PlanValidationError, match="begin with"):
        ActionPlan(actions=(ClickAction(selector="#submit"),))


@pytest.mark.parametrize(
    "assertion",
    [
        lambda: UrlContainsAssertion(value="   "),
        lambda: TitleContainsAssertion(value="   "),
        lambda: ElementVisibleAssertion(selector="   "),
        lambda: ElementHiddenAssertion(selector="   "),
        lambda: ElementEnabledAssertion(selector="   "),
        lambda: ElementDisabledAssertion(selector="   "),
        lambda: ElementCheckedAssertion(selector="   "),
        lambda: ElementUncheckedAssertion(selector="   "),
        lambda: ElementValueEqualsAssertion(
            selector="   ",
            value="Ada",
        ),
        lambda: ElementCountEqualsAssertion(selector="   ", count=1),
        lambda: ElementAttributeContainsAssertion(
            selector="#status",
            attribute="   ",
            value="complete",
        ),
        lambda: ElementAttributeContainsAssertion(
            selector="#status",
            attribute="class",
            value="   ",
        ),
        lambda: ElementTextContainsAssertion(
            selector="#result",
            value="   ",
        ),
    ],
)
def test_assertions_reject_blank_inputs(assertion) -> None:
    with pytest.raises(PlanValidationError, match="must not be blank"):
        assertion()


def test_element_value_assertion_accepts_an_empty_value() -> None:
    assertion = ElementValueEqualsAssertion(selector="#search", value="")

    assert assertion.value == ""


@pytest.mark.parametrize("count", [-1, 1.5, "1", True])
def test_element_count_assertion_requires_a_non_negative_integer(
    count,
) -> None:
    with pytest.raises(PlanValidationError, match="non-negative integer"):
        ElementCountEqualsAssertion(selector=".result", count=count)


def test_plan_rejects_unknown_assertion_types() -> None:
    with pytest.raises(PlanValidationError, match="unsupported assertion"):
        ActionPlan(
            actions=(NavigateAction(url="https://example.com"),),
            assertions=(object(),),
        )


def test_select_action_requires_a_string_value() -> None:
    with pytest.raises(PlanValidationError, match="must be a string"):
        SelectAction(selector="#country", value=42)


@pytest.mark.parametrize("key", sorted(ALLOWED_PRESS_KEYS))
def test_press_action_accepts_allowed_keys(key: str) -> None:
    action = PressAction(selector="#search", key=key)

    assert action.key == key


@pytest.mark.parametrize("key", ["", " ", "Control+A", "F12", "a"])
def test_press_action_rejects_unsupported_keys(key: str) -> None:
    with pytest.raises(PlanValidationError, match="press key"):
        PressAction(selector="#search", key=key)


def test_press_action_requires_a_string_key() -> None:
    with pytest.raises(PlanValidationError, match="must be a string"):
        PressAction(selector="#search", key=13)


def test_completion_criteria_require_evidence_for_nonempty_sources() -> None:
    with pytest.raises(PlanValidationError, match="at least one"):
        CompletionCriteria(
            assertions=(),
            source=CriteriaSource.AI_GENERATED,
            reason="Generated by the planner",
        )


def test_none_criteria_source_rejects_assertions() -> None:
    with pytest.raises(PlanValidationError, match="cannot contain"):
        CompletionCriteria(
            assertions=(UrlContainsAssertion(value="example.com"),),
            source=CriteriaSource.NONE,
            reason="No safe criteria were available",
        )
