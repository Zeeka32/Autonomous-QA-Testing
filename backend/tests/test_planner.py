import json
from types import SimpleNamespace

import pytest

from autonomous_qa.models import (
    ActionResult,
    CheckResult,
    InteractiveElement,
    PageObservation,
)
from autonomous_qa.planner import (
    DecisionStatus,
    GeneratedAction,
    GeneratedCriteria,
    GeneratedCriterion,
    GeneratedDecision,
    GeneratedPlan,
    PlannerError,
    generate_action_plan,
    generate_completion_criteria,
    generate_next_decision,
)
from autonomous_qa.plans import (
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
    ElementUncheckedAssertion,
    ElementValueEqualsAssertion,
    FillAction,
    NavigateAction,
    PressAction,
    SelectAction,
    UncheckAction,
    UrlContainsAssertion,
    WaitForAction,
)


def make_observation(*, disabled: bool = False) -> PageObservation:
    return PageObservation(
        elements=(
            InteractiveElement(
                selector="#search",
                tag="input",
                role="textbox",
                label="Search",
                input_type="text",
                disabled=False,
                href=None,
            ),
            InteractiveElement(
                selector="#terms",
                tag="input",
                role="checkbox",
                label="Accept terms",
                input_type="checkbox",
                disabled=False,
                href=None,
                checked=False,
            ),
            InteractiveElement(
                selector="#plan",
                tag="input",
                role="radio",
                label="Basic plan",
                input_type="radio",
                disabled=False,
                href=None,
                checked=False,
            ),
            InteractiveElement(
                selector="#country",
                tag="select",
                role="combobox",
                label="Country",
                input_type=None,
                disabled=False,
                href=None,
                options=("eg", "uk"),
            ),
            InteractiveElement(
                selector="#submit",
                tag="button",
                role="button",
                label="Search",
                input_type=None,
                disabled=disabled,
                href=None,
            ),
        ),
        truncated=False,
    )


class FakeResponses:
    def __init__(self, output_parsed) -> None:
        self.output_parsed = output_parsed
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=self.output_parsed)


class FakeOpenAI:
    def __init__(self, output_parsed) -> None:
        self.responses = FakeResponses(output_parsed)


class FakeGeminiCompletions:
    def __init__(self, output_parsed) -> None:
        self.output_parsed = output_parsed
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(parsed=self.output_parsed)
                )
            ]
        )


class FakeGemini:
    def __init__(self, output_parsed) -> None:
        self.completions = FakeGeminiCompletions(output_parsed)
        self.chat = SimpleNamespace(completions=self.completions)
        self.beta = SimpleNamespace(chat=self.chat)


def test_planner_converts_structured_output_to_internal_plan() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="fill",
                    selector="#search",
                    value="QA testing",
                ),
                GeneratedAction(kind="click", selector="#submit", value=""),
            ]
        )
    )

    plan = generate_action_plan(
        goal="Search for QA testing",
        starting_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert isinstance(plan.actions[0], NavigateAction)
    assert isinstance(plan.actions[1], FillAction)
    assert isinstance(plan.actions[2], ClickAction)
    assert client.responses.request["model"] == "test-model"
    supplied_input = json.loads(client.responses.request["input"][1]["content"])
    assert supplied_input["goal"] == "Search for QA testing"
    assert supplied_input["observation"]["elements"][0]["selector"] == "#search"


def test_gemini_planner_converts_structured_output_to_internal_plan() -> None:
    client = FakeGemini(
        GeneratedPlan(
            actions=[
                GeneratedAction(kind="click", selector="#submit", value="")
            ]
        )
    )

    plan = generate_action_plan(
        goal="Click search",
        starting_url="https://example.com",
        observation=make_observation(),
        model="gemini-test-model",
        provider="gemini",
        client=client,
    )

    assert isinstance(plan.actions[0], NavigateAction)
    assert isinstance(plan.actions[1], ClickAction)
    assert client.completions.request["model"] == "gemini-test-model"
    supplied_input = json.loads(client.completions.request["messages"][1]["content"])
    assert supplied_input["goal"] == "Click search"


def test_planner_converts_a_wait_action() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="wait_for",
                    selector="#submit",
                    value="",
                )
            ]
        )
    )

    plan = generate_action_plan(
        goal="Wait for search",
        starting_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert isinstance(plan.actions[1], WaitForAction)


def test_planner_rejects_a_wait_with_a_value() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="wait_for",
                    selector="#submit",
                    value="unexpected",
                )
            ]
        )
    )

    with pytest.raises(PlannerError, match="empty value"):
        generate_action_plan(
            "Wait for search",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_planner_converts_a_select_action_with_an_observed_value() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="select",
                    selector="#country",
                    value="eg",
                )
            ]
        )
    )

    plan = generate_action_plan(
        goal="Select Egypt",
        starting_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert plan.actions[1] == SelectAction(selector="#country", value="eg")


def test_planner_rejects_an_unobserved_select_value() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="select",
                    selector="#country",
                    value="invented",
                )
            ]
        )
    )

    with pytest.raises(PlannerError, match="unobserved option"):
        generate_action_plan(
            "Select a country",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


@pytest.mark.parametrize(
    ("kind", "selector", "expected_type"),
    [
        ("check", "#terms", CheckAction),
        ("check", "#plan", CheckAction),
        ("uncheck", "#terms", UncheckAction),
    ],
)
def test_planner_converts_check_actions(kind, selector, expected_type) -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(kind=kind, selector=selector, value="")
            ]
        )
    )

    plan = generate_action_plan(
        goal="Change the choice",
        starting_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert isinstance(plan.actions[1], expected_type)


@pytest.mark.parametrize(
    ("kind", "selector", "message"),
    [
        ("check", "#submit", "non-checkable"),
        ("uncheck", "#plan", "non-checkbox"),
    ],
)
def test_planner_rejects_check_actions_for_wrong_elements(
    kind,
    selector,
    message,
) -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(kind=kind, selector=selector, value="")
            ]
        )
    )

    with pytest.raises(PlannerError, match=message):
        generate_action_plan(
            "Change the choice",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


@pytest.mark.parametrize("kind", ["check", "uncheck"])
def test_planner_rejects_check_actions_with_a_value(kind) -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind=kind,
                    selector="#terms",
                    value="unexpected",
                )
            ]
        )
    )

    with pytest.raises(PlannerError, match="empty value"):
        generate_action_plan(
            "Change the choice",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_planner_converts_an_allowed_press_action() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="press",
                    selector="#search",
                    value="Enter",
                )
            ]
        )
    )

    plan = generate_action_plan(
        goal="Submit the search",
        starting_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert plan.actions[1] == PressAction(selector="#search", key="Enter")


def test_planner_rejects_an_unsupported_press_key() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="press",
                    selector="#search",
                    value="Control+A",
                )
            ]
        )
    )

    with pytest.raises(PlannerError, match="unsupported press key"):
        generate_action_plan(
            "Select all text",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def make_link_observation() -> PageObservation:
    return PageObservation(
        elements=(
            InteractiveElement(
                selector="#learn-more",
                tag="a",
                role="link",
                label="Learn more",
                input_type=None,
                disabled=False,
                href="https://www.iana.org/help/example-domains",
            ),
        ),
        truncated=False,
    )


def test_generates_grounded_completion_criteria() -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[
                GeneratedCriterion(
                    kind="url_contains",
                    selector="",
                    attribute="",
                    value="iana.org",
                )
            ],
            reason="The observed Learn more link targets IANA",
        )
    )

    criteria = generate_completion_criteria(
        goal="Open the Learn more link",
        current_url="https://example.com",
        page_title="Example Domain",
        observation=make_link_observation(),
        model="test-model",
        client=client,
    )

    assert criteria == CompletionCriteria(
        assertions=(UrlContainsAssertion(value="iana.org"),),
        source=CriteriaSource.AI_GENERATED,
        reason="The observed Learn more link targets IANA",
    )
    assert client.responses.request["text_format"] is GeneratedCriteria
    supplied_input = json.loads(client.responses.request["input"][1]["content"])
    assert supplied_input["goal"] == "Open the Learn more link"
    assert supplied_input["page_title"] == "Example Domain"


@pytest.mark.parametrize(
    ("kind", "assertion_type"),
    [
        ("element_hidden", ElementHiddenAssertion),
        ("element_enabled", ElementEnabledAssertion),
        ("element_disabled", ElementDisabledAssertion),
        ("element_checked", ElementCheckedAssertion),
        ("element_unchecked", ElementUncheckedAssertion),
    ],
)
def test_criteria_generator_supports_element_state_checks(
    kind,
    assertion_type,
) -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[
                GeneratedCriterion(
                    kind=kind,
                    selector="#terms",
                    attribute="",
                    value="",
                )
            ],
            reason="The final control state proves the goal",
        )
    )

    criteria = generate_completion_criteria(
        goal="Change the terms control",
        current_url="https://example.com",
        page_title="Example Domain",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert criteria.assertions == (assertion_type(selector="#terms"),)


@pytest.mark.parametrize(
    ("kind", "attribute", "value", "expected"),
    [
        (
            "element_value_equals",
            "",
            "Ada",
            ElementValueEqualsAssertion(
                selector="#search",
                value="Ada",
            ),
        ),
        (
            "element_count_equals",
            "",
            "1",
            ElementCountEqualsAssertion(
                selector="#search",
                count=1,
            ),
        ),
        (
            "element_attribute_contains",
            "aria-label",
            "Search",
            ElementAttributeContainsAssertion(
                selector="#search",
                attribute="aria-label",
                value="Search",
            ),
        ),
    ],
)
def test_criteria_generator_supports_general_element_checks(
    kind,
    attribute,
    value,
    expected,
) -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[
                GeneratedCriterion(
                    kind=kind,
                    selector="#search",
                    attribute=attribute,
                    value=value,
                )
            ],
            reason="The final element data proves the goal",
        )
    )

    criteria = generate_completion_criteria(
        goal="Change the search control",
        current_url="https://example.com",
        page_title="Example Domain",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert criteria.assertions == (expected,)


def test_criteria_generator_rejects_invalid_element_count() -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[
                GeneratedCriterion(
                    kind="element_count_equals",
                    selector="#search",
                    attribute="",
                    value="many",
                )
            ],
            reason="Count matching elements",
        )
    )

    with pytest.raises(PlannerError, match="non-negative"):
        generate_completion_criteria(
            goal="Count search controls",
            current_url="https://example.com",
            page_title="Example Domain",
            observation=make_observation(),
            model="test-model",
            client=client,
        )


def test_criteria_generator_rejects_state_checks_with_values() -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[
                GeneratedCriterion(
                    kind="element_checked",
                    selector="#terms",
                    attribute="",
                    value="true",
                )
            ],
            reason="The control should be checked",
        )
    )

    with pytest.raises(PlannerError, match="empty value"):
        generate_completion_criteria(
            goal="Accept the terms",
            current_url="https://example.com",
            page_title="Example Domain",
            observation=make_observation(),
            model="test-model",
            client=client,
        )


def test_criteria_generator_can_report_unverified() -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="unverified",
            criteria=[],
            reason="No deterministic outcome can be inferred",
        )
    )

    criteria = generate_completion_criteria(
        goal="Make the site better",
        current_url="https://example.com",
        page_title="Example Domain",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert criteria == CompletionCriteria(
        assertions=(),
        source=CriteriaSource.NONE,
        reason="No deterministic outcome can be inferred",
    )


def test_criteria_generator_rejects_an_ungrounded_url() -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[
                GeneratedCriterion(
                    kind="url_contains",
                    selector="",
                    attribute="",
                    value="invented.example",
                )
            ],
            reason="Use a destination URL",
        )
    )

    with pytest.raises(PlannerError, match="not grounded"):
        generate_completion_criteria(
            goal="Open the destination",
            current_url="https://example.com",
            page_title="Example Domain",
            observation=make_link_observation(),
            model="test-model",
            client=client,
        )


def test_criteria_generator_rejects_empty_criteria_status() -> None:
    client = FakeOpenAI(
        GeneratedCriteria(
            status="criteria",
            criteria=[],
            reason="No criteria supplied",
        )
    )

    with pytest.raises(PlannerError, match="at least one"):
        generate_completion_criteria(
            goal="Open the destination",
            current_url="https://example.com",
            page_title="Example Domain",
            observation=make_link_observation(),
            model="test-model",
            client=client,
        )


def test_next_decision_converts_one_validated_action() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="action",
            kind="click",
            selector="#submit",
            value="",
            reason="Submit the search form",
        )
    )

    decision = generate_next_decision(
        goal="Search the site",
        current_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
    )

    assert decision.status is DecisionStatus.ACTION
    assert decision.action == ClickAction(selector="#submit")
    assert decision.reason == "Submit the search form"
    assert client.responses.request["text_format"] is GeneratedDecision
    supplied_input = json.loads(client.responses.request["input"][1]["content"])
    assert supplied_input["current_url"] == "https://example.com"
    assert supplied_input["completion_criteria"] == []
    assert supplied_input["previous_action_result"] is None
    assert supplied_input["previous_verification_results"] == []


def test_next_decision_supplies_frozen_completion_criteria() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="action",
            kind="click",
            selector="#submit",
            value="",
            reason="Use the observed control to satisfy the URL criterion",
        )
    )

    generate_next_decision(
        goal="Open the destination",
        current_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
        completion_criteria=(
            UrlContainsAssertion(value="iana.org"),
        ),
    )

    supplied_input = json.loads(client.responses.request["input"][1]["content"])
    assert supplied_input["completion_criteria"] == [
        {"value": "iana.org", "kind": "url_contains"}
    ]


def test_next_decision_supplies_previous_action_feedback() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="blocked",
            kind="none",
            selector="",
            value="",
            reason="No alternative observed control can make progress",
        )
    )
    failed_action = ActionResult(
        step_number=2,
        kind="click",
        status="failed",
        duration_ms=10_000.0,
        url_before="https://example.com",
        url_after="https://example.com",
        message="Selector timed out",
    )

    generate_next_decision(
        goal="Submit the form",
        current_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
        previous_action_result=failed_action,
    )

    supplied_input = json.loads(client.responses.request["input"][1]["content"])
    assert supplied_input["previous_action_result"] == {
        "step_number": 2,
        "kind": "click",
        "status": "failed",
        "duration_ms": 10_000.0,
        "url_before": "https://example.com",
        "url_after": "https://example.com",
        "message": "Selector timed out",
    }


def test_next_decision_supplies_failed_verification_feedback() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="action",
            kind="click",
            selector="#submit",
            value="",
            reason="Try submitting the form again",
        )
    )
    failed_check = CheckResult(
        name="Expected URL",
        passed=False,
        message="Final URL does not contain /complete",
    )

    generate_next_decision(
        goal="Submit the form",
        current_url="https://example.com",
        observation=make_observation(),
        model="test-model",
        client=client,
        previous_verification_results=(failed_check,),
    )

    supplied_input = json.loads(client.responses.request["input"][1]["content"])
    assert supplied_input["previous_verification_results"] == [
        {
            "name": "Expected URL",
            "passed": False,
            "message": "Final URL does not contain /complete",
        }
    ]


@pytest.mark.parametrize("status", ["complete", "blocked"])
def test_next_decision_converts_terminal_decisions(status: str) -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status=status,
            kind="none",
            selector="",
            value="",
            reason="No more browser action is needed",
        )
    )

    decision = generate_next_decision(
        "Open the dashboard",
        "https://example.com/dashboard",
        make_observation(),
        "test-model",
        client,
    )

    assert decision.status is DecisionStatus(status)
    assert decision.action is None


def test_next_decision_rejects_an_action_on_terminal_status() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="complete",
            kind="click",
            selector="#submit",
            value="",
            reason="The task is complete",
        )
    )

    with pytest.raises(PlannerError, match="must not include an action"):
        generate_next_decision(
            "Submit the form",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_next_decision_requires_an_action_for_action_status() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="action",
            kind="none",
            selector="",
            value="",
            reason="Continue working",
        )
    )

    with pytest.raises(PlannerError, match="must include an action kind"):
        generate_next_decision(
            "Submit the form",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_next_decision_requires_a_nonblank_reason() -> None:
    client = FakeOpenAI(
        GeneratedDecision(
            status="blocked",
            kind="none",
            selector="",
            value="",
            reason="   ",
        )
    )

    with pytest.raises(PlannerError, match="reason must not be blank"):
        generate_next_decision(
            "Submit the form",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_gemini_planner_requires_an_api_key_without_injected_client(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(PlannerError, match="GEMINI_API_KEY is not set"):
        generate_action_plan(
            goal="Click search",
            starting_url="https://example.com",
            observation=make_observation(),
            model="gemini-test-model",
            provider="gemini",
        )


def test_planner_rejects_unobserved_selectors() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(kind="click", selector="#invented", value="")
            ]
        )
    )

    with pytest.raises(PlannerError, match="unobserved selector"):
        generate_action_plan(
            "Click submit",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_planner_rejects_disabled_elements() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[GeneratedAction(kind="click", selector="#submit", value="")]
        )
    )

    with pytest.raises(PlannerError, match="disabled element"):
        generate_action_plan(
            "Click submit",
            "https://example.com",
            make_observation(disabled=True),
            "test-model",
            client,
        )


def test_planner_rejects_blank_goals_without_calling_api() -> None:
    client = FakeOpenAI(GeneratedPlan(actions=[]))

    with pytest.raises(PlannerError, match="must not be blank"):
        generate_action_plan(
            "   ",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )

    assert client.responses.request is None


def test_planner_rejects_missing_parsed_output() -> None:
    client = FakeOpenAI(None)

    with pytest.raises(PlannerError, match="did not return"):
        generate_action_plan(
            "Click submit",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )


def test_structured_output_schema_does_not_use_one_of() -> None:
    plan_schema = json.dumps(GeneratedPlan.model_json_schema())
    criteria_schema = json.dumps(GeneratedCriteria.model_json_schema())
    decision_schema = json.dumps(GeneratedDecision.model_json_schema())

    assert '"oneOf"' not in plan_schema
    assert '"oneOf"' not in criteria_schema
    assert '"oneOf"' not in decision_schema


def test_planner_rejects_a_click_with_a_value() -> None:
    client = FakeOpenAI(
        GeneratedPlan(
            actions=[
                GeneratedAction(
                    kind="click",
                    selector="#submit",
                    value="unexpected",
                )
            ]
        )
    )

    with pytest.raises(PlannerError, match="empty value"):
        generate_action_plan(
            "Click submit",
            "https://example.com",
            make_observation(),
            "test-model",
            client,
        )
