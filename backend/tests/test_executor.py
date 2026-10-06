from playwright.sync_api import Error as PlaywrightError

from autonomous_qa.browser.executor import (
    ACTION_TIMEOUT_MS,
    NAVIGATION_TIMEOUT_MS,
    execute_action,
    execute_plan,
)
from autonomous_qa.plans import (
    ActionPlan,
    CheckAction,
    ClickAction,
    FillAction,
    NavigateAction,
    PressAction,
    SelectAction,
    UncheckAction,
    WaitForAction,
)


class FakeLocator:
    def __init__(self, selector: str, events: list[tuple]) -> None:
        self.selector = selector
        self.events = events

    def click(self, timeout: int) -> None:
        self.events.append(("click", self.selector, timeout))

    def fill(self, value: str, timeout: int) -> None:
        self.events.append(("fill", self.selector, value, timeout))

    def wait_for(self, state: str, timeout: int) -> None:
        self.events.append(("wait_for", self.selector, state, timeout))

    def select_option(self, value: str, timeout: int) -> None:
        self.events.append(("select", self.selector, value, timeout))

    def check(self, timeout: int) -> None:
        self.events.append(("check", self.selector, timeout))

    def uncheck(self, timeout: int) -> None:
        self.events.append(("uncheck", self.selector, timeout))

    def press(self, key: str, timeout: int) -> None:
        self.events.append(("press", self.selector, key, timeout))


class FakePage:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.response = object()
        self.url = "about:blank"

    def goto(self, url: str, wait_until: str, timeout: int):
        self.events.append(("navigate", url, wait_until, timeout))
        self.url = url
        return self.response

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector, self.events)


def test_execute_action_runs_one_action_and_records_its_result() -> None:
    page = FakePage()

    execution = execute_action(
        page,
        NavigateAction(url="https://example.com"),
        step_number=4,
    )

    assert execution.navigation_response is page.response
    assert execution.action_result.step_number == 4
    assert execution.action_result.kind == "navigate"
    assert execution.action_result.status == "passed"
    assert execution.action_result.url_before == "about:blank"
    assert execution.action_result.url_after == "https://example.com"
    assert page.events == [
        (
            "navigate",
            "https://example.com",
            "domcontentloaded",
            NAVIGATION_TIMEOUT_MS,
        )
    ]


def test_execute_action_returns_a_failed_result_for_playwright_errors() -> None:
    page = FakePage()

    def fail_to_navigate(url: str, wait_until: str, timeout: int):
        raise PlaywrightError("navigation timed out\ninternal call log")

    page.goto = fail_to_navigate

    execution = execute_action(
        page,
        NavigateAction(url="https://example.com"),
        step_number=1,
    )

    assert execution.navigation_response is None
    assert execution.action_result.status == "failed"
    assert execution.action_result.message == "navigation timed out"


def test_executor_runs_actions_in_order() -> None:
    page = FakePage()
    plan = ActionPlan(
        actions=(
            NavigateAction(url="https://example.com"),
            FillAction(selector="#search", value="QA testing"),
            ClickAction(selector="#submit"),
            WaitForAction(selector="#results"),
            SelectAction(selector="#country", value="eg"),
            CheckAction(selector="#terms"),
            UncheckAction(selector="#newsletter"),
            PressAction(selector="#search", key="Enter"),
        )
    )

    execution = execute_plan(page, plan)

    assert execution.navigation_response is page.response
    assert page.events == [
        (
            "navigate",
            "https://example.com",
            "domcontentloaded",
            NAVIGATION_TIMEOUT_MS,
        ),
        ("fill", "#search", "QA testing", ACTION_TIMEOUT_MS),
        ("click", "#submit", ACTION_TIMEOUT_MS),
        ("wait_for", "#results", "visible", ACTION_TIMEOUT_MS),
        ("select", "#country", "eg", ACTION_TIMEOUT_MS),
        ("check", "#terms", ACTION_TIMEOUT_MS),
        ("uncheck", "#newsletter", ACTION_TIMEOUT_MS),
        ("press", "#search", "Enter", ACTION_TIMEOUT_MS),
    ]
    assert [result.kind for result in execution.action_results] == [
        "navigate",
        "fill",
        "click",
        "wait_for",
        "select",
        "check",
        "uncheck",
        "press",
    ]
    assert all(result.status == "passed" for result in execution.action_results)
    assert all(
        result.duration_ms >= 0
        for result in execution.action_results
    )
    assert execution.action_results[0].url_before == "about:blank"
    assert execution.action_results[0].url_after == "https://example.com"
    assert execution.action_results[3].message == (
        'Waited for "#results" to become visible'
    )
    assert execution.action_results[4].message == (
        'Selected an option in "#country"'
    )
    assert execution.action_results[5].message == 'Checked "#terms"'
    assert execution.action_results[6].message == 'Unchecked "#newsletter"'
    assert execution.action_results[7].message == (
        'Pressed Enter on "#search"'
    )


def test_executor_records_a_wait_timeout_and_skips_later_actions() -> None:
    page = FakePage()

    class TimingOutLocator(FakeLocator):
        def wait_for(self, state: str, timeout: int) -> None:
            raise PlaywrightError("Timeout 10000ms exceeded\ncall log")

    page.locator = lambda selector: TimingOutLocator(selector, page.events)
    plan = ActionPlan(
        actions=(
            NavigateAction(url="https://example.com"),
            WaitForAction(selector="#results"),
            ClickAction(selector="#result"),
        )
    )

    execution = execute_plan(page, plan)

    assert [result.status for result in execution.action_results] == [
        "passed",
        "failed",
        "skipped",
    ]
    assert execution.action_results[1].message == "Timeout 10000ms exceeded"


def test_executor_records_the_failing_step_and_stops() -> None:
    page = FakePage()

    def fail_to_navigate(url: str, wait_until: str, timeout: int):
        raise PlaywrightError("navigation timed out\ninternal call log")

    page.goto = fail_to_navigate
    plan = ActionPlan(
        actions=(
            NavigateAction(url="https://example.com"),
            ClickAction(selector="#never-reached"),
        )
    )

    execution = execute_plan(page, plan)

    assert execution.navigation_response is None
    assert len(execution.action_results) == 2
    failure = execution.action_results[0]
    assert failure.step_number == 1
    assert failure.kind == "navigate"
    assert failure.status == "failed"
    assert failure.message == "navigation timed out"
    skipped = execution.action_results[1]
    assert skipped.status == "skipped"
    assert skipped.duration_ms == 0
    assert skipped.message == "Skipped because an earlier action failed"
    assert page.events == []
