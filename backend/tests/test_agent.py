from playwright.sync_api import Error as PlaywrightError

import pytest

from autonomous_qa import agent
from autonomous_qa.agent import AgentLoopError, AgentStatus, run_agent_loop
from autonomous_qa.models import ActionResult, CheckResult, PageObservation
from autonomous_qa.planner import DecisionStatus, PlannerDecision
from autonomous_qa.plans import (
    ClickAction,
    PlanAssertion,
    UrlContainsAssertion,
)


EMPTY_OBSERVATION = PageObservation(elements=(), truncated=False)


class FakeLocator:
    def __init__(self, page, selector: str) -> None:
        self.page = page
        self.selector = selector

    def click(self, timeout: int) -> None:
        self.page.events.append(("click", self.selector, timeout))
        if self.page.click_errors:
            error = self.page.click_errors.pop(0)
            if error is not None:
                raise error
            return
        if self.page.click_error is not None:
            raise self.page.click_error


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.com"
        self.events: list[tuple] = []
        self.click_error: PlaywrightError | None = None
        self.click_errors: list[PlaywrightError | None] = []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)


class FakePlanner:
    def __init__(self, decisions: list[PlannerDecision]) -> None:
        self.decisions = decisions
        self.calls: list[tuple] = []

    def __call__(
        self,
        goal: str,
        current_url: str,
        observation: PageObservation,
        previous_action_result: ActionResult | None,
        previous_verification_results: tuple[CheckResult, ...],
        completion_criteria: tuple[PlanAssertion, ...],
    ) -> PlannerDecision:
        self.calls.append(
            (
                goal,
                current_url,
                observation,
                previous_action_result,
                previous_verification_results,
                completion_criteria,
            )
        )
        return self.decisions.pop(0)


@pytest.fixture(autouse=True)
def fake_observation(monkeypatch) -> None:
    monkeypatch.setattr(
        agent,
        "observe_page",
        lambda page: EMPTY_OBSERVATION,
    )


def action_decision() -> PlannerDecision:
    return PlannerDecision(
        status=DecisionStatus.ACTION,
        action=ClickAction(selector="#continue"),
        reason="Continue to the next page",
    )


def terminal_decision(status: DecisionStatus) -> PlannerDecision:
    return PlannerDecision(
        status=status,
        action=None,
        reason=f"Planner returned {status}",
    )


def test_agent_reobserves_after_an_action_then_completes() -> None:
    page = FakePage()
    planner = FakePlanner(
        [
            action_decision(),
            terminal_decision(DecisionStatus.COMPLETE),
        ]
    )

    criterion = UrlContainsAssertion(value="/complete")
    reported_steps = []
    result = run_agent_loop(
        page,
        "Continue",
        planner,
        starting_step_number=2,
        completion_criteria=(criterion,),
        step_reporter=reported_steps.append,
    )

    assert result.status is AgentStatus.COMPLETE
    assert len(planner.calls) == 2
    assert len(result.steps) == 2
    assert result.steps[0].step_number == 2
    assert result.steps[0].action_kind == "click"
    assert result.steps[0].execution_status == "passed"
    assert result.steps[1].step_number == 3
    assert result.steps[1].decision_status is DecisionStatus.COMPLETE
    assert len(result.action_results) == 1
    assert result.action_results[0].step_number == 2
    assert planner.calls[0][3] is None
    assert planner.calls[1][3] == result.action_results[0]
    assert planner.calls[0][5] == (criterion,)
    assert planner.calls[1][5] == (criterion,)
    assert tuple(reported_steps) == result.steps
    assert page.events[0][0:2] == ("click", "#continue")


def test_agent_stops_when_the_planner_is_blocked() -> None:
    planner = FakePlanner(
        [terminal_decision(DecisionStatus.BLOCKED)]
    )

    result = run_agent_loop(FakePage(), "Continue", planner)

    assert result.status is AgentStatus.BLOCKED
    assert result.action_results == ()
    assert result.steps[0].execution_status is None


def test_agent_marks_completion_without_criteria_as_unverified() -> None:
    planner = FakePlanner(
        [terminal_decision(DecisionStatus.COMPLETE)]
    )

    result = run_agent_loop(
        FakePage(),
        "Continue",
        planner,
        completion_verifier=lambda page: (),
    )

    assert result.status is AgentStatus.UNVERIFIED
    assert "without any deterministic" in result.reason


def test_agent_replans_after_failed_completion_verification() -> None:
    failed_check = CheckResult(
        name="Expected URL",
        passed=False,
        message="Final URL does not contain /complete",
    )
    passed_check = CheckResult(
        name="Expected URL",
        passed=True,
        message="Final URL contains /complete",
    )
    verification_results = iter(
        [(failed_check,), (passed_check,)]
    )
    planner = FakePlanner(
        [
            terminal_decision(DecisionStatus.COMPLETE),
            action_decision(),
            terminal_decision(DecisionStatus.COMPLETE),
        ]
    )

    result = run_agent_loop(
        FakePage(),
        "Continue",
        planner,
        completion_verifier=lambda page: next(verification_results),
    )

    assert result.status is AgentStatus.COMPLETE
    assert result.verification_retries_used == 1
    assert planner.calls[1][4] == (failed_check,)
    assert planner.calls[2][4] == ()
    assert result.steps[0].verification_results == (failed_check,)
    assert result.steps[2].verification_results == (passed_check,)


def test_agent_stops_when_verification_retry_budget_is_exhausted() -> None:
    failed_check = CheckResult(
        name="Expected URL",
        passed=False,
        message="Final URL does not contain /complete",
    )
    planner = FakePlanner(
        [terminal_decision(DecisionStatus.COMPLETE) for _ in range(3)]
    )

    result = run_agent_loop(
        FakePage(),
        "Continue",
        planner,
        completion_verifier=lambda page: (failed_check,),
    )

    assert result.status is AgentStatus.VERIFICATION_FAILED
    assert result.verification_retries_used == 2
    assert result.reason == failed_check.message
    assert len(result.steps) == 3


def test_agent_stops_after_a_failed_action_when_recovery_is_disabled() -> None:
    page = FakePage()
    page.click_error = PlaywrightError("click timed out\ncall log")
    planner = FakePlanner([action_decision()])

    result = run_agent_loop(
        page,
        "Continue",
        planner,
        max_recoveries=0,
    )

    assert result.status is AgentStatus.FAILED
    assert result.reason == "click timed out"
    assert result.action_results[0].status == "failed"
    assert result.steps[0].execution_message == "click timed out"
    assert result.recoveries_used == 0
    assert len(planner.calls) == 1


def test_agent_replans_after_a_failed_action_and_recovers() -> None:
    page = FakePage()
    page.click_errors = [
        PlaywrightError("click timed out\ncall log"),
        None,
    ]
    planner = FakePlanner(
        [
            action_decision(),
            action_decision(),
            terminal_decision(DecisionStatus.COMPLETE),
        ]
    )

    result = run_agent_loop(page, "Continue", planner)

    assert result.status is AgentStatus.COMPLETE
    assert result.recoveries_used == 1
    assert [action.status for action in result.action_results] == [
        "failed",
        "passed",
    ]
    assert planner.calls[1][3] == result.action_results[0]
    assert planner.calls[2][3] == result.action_results[1]


def test_agent_stops_when_the_recovery_budget_is_exhausted() -> None:
    page = FakePage()
    page.click_error = PlaywrightError("click timed out\ncall log")
    planner = FakePlanner([action_decision(), action_decision()])

    result = run_agent_loop(
        page,
        "Continue",
        planner,
        max_recoveries=1,
    )

    assert result.status is AgentStatus.FAILED
    assert result.recoveries_used == 1
    assert len(result.action_results) == 2
    assert all(
        action.status == "failed"
        for action in result.action_results
    )


def test_agent_stops_at_the_step_limit() -> None:
    planner = FakePlanner([action_decision() for _ in range(3)])

    result = run_agent_loop(
        FakePage(),
        "Keep clicking",
        planner,
        max_steps=3,
    )

    assert result.status is AgentStatus.STEP_LIMIT_REACHED
    assert len(result.steps) == 3
    assert len(result.action_results) == 3
    assert result.reason == "Agent reached the limit of 3 action steps"


def test_agent_rejects_an_action_decision_without_an_action() -> None:
    planner = FakePlanner(
        [
            PlannerDecision(
                status=DecisionStatus.ACTION,
                action=None,
                reason="Invalid decision",
            )
        ]
    )

    with pytest.raises(AgentLoopError, match="did not include an action"):
        run_agent_loop(FakePage(), "Continue", planner)


def test_agent_rejects_a_terminal_decision_with_an_action() -> None:
    planner = FakePlanner(
        [
            PlannerDecision(
                status=DecisionStatus.COMPLETE,
                action=ClickAction(selector="#continue"),
                reason="Invalid decision",
            )
        ]
    )

    with pytest.raises(AgentLoopError, match="included an action"):
        run_agent_loop(FakePage(), "Continue", planner)


def test_agent_rejects_a_blank_decision_reason() -> None:
    planner = FakePlanner(
        [
            PlannerDecision(
                status=DecisionStatus.BLOCKED,
                action=None,
                reason="   ",
            )
        ]
    )

    with pytest.raises(AgentLoopError, match="reason must not be blank"):
        run_agent_loop(FakePage(), "Continue", planner)


@pytest.mark.parametrize(
    (
        "goal",
        "max_steps",
        "max_recoveries",
        "max_verification_retries",
        "starting_step_number",
        "message",
    ),
    [
        ("   ", 10, 2, 2, 1, "goal must not be blank"),
        ("Continue", 0, 2, 2, 1, "max_steps must be at least 1"),
        ("Continue", 10, -1, 2, 1, "max_recoveries must be at least 0"),
        (
            "Continue",
            10,
            2,
            -1,
            1,
            "max_verification_retries must be at least 0",
        ),
        (
            "Continue",
            10,
            2,
            2,
            0,
            "starting_step_number must be at least 1",
        ),
    ],
)
def test_agent_validates_its_bounds(
    goal,
    max_steps,
    max_recoveries,
    max_verification_retries,
    starting_step_number,
    message,
) -> None:
    planner = FakePlanner([])

    with pytest.raises(AgentLoopError, match=message):
        run_agent_loop(
            FakePage(),
            goal,
            planner,
            max_steps=max_steps,
            max_recoveries=max_recoveries,
            max_verification_retries=max_verification_retries,
            starting_step_number=starting_step_number,
        )
