from dataclasses import dataclass
from time import perf_counter

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Response

from .models import ActionResult
from .plans import (
    ActionPlan,
    BrowserAction,
    CheckAction,
    ClickAction,
    FillAction,
    NavigateAction,
    PressAction,
    SelectAction,
    UncheckAction,
    WaitForAction,
)


ACTION_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class PlanExecutionResult:
    navigation_response: Response | None
    action_results: tuple[ActionResult, ...]


@dataclass(frozen=True)
class ActionExecutionResult:
    action_result: ActionResult
    navigation_response: Response | None = None


def _success_message(action) -> str:
    if isinstance(action, NavigateAction):
        return f'Navigated to "{action.url}"'
    if isinstance(action, ClickAction):
        return f'Clicked "{action.selector}"'
    if isinstance(action, WaitForAction):
        return f'Waited for "{action.selector}" to become visible'
    if isinstance(action, SelectAction):
        return f'Selected an option in "{action.selector}"'
    if isinstance(action, CheckAction):
        return f'Checked "{action.selector}"'
    if isinstance(action, UncheckAction):
        return f'Unchecked "{action.selector}"'
    if isinstance(action, PressAction):
        return f'Pressed {action.key} on "{action.selector}"'
    return f'Filled "{action.selector}"'


def execute_action(
    page: Page,
    action: BrowserAction,
    step_number: int,
) -> ActionExecutionResult:
    url_before = page.url
    navigation_response = None
    started_at = perf_counter()

    try:
        if isinstance(action, NavigateAction):
            navigation_response = page.goto(
                action.url,
                wait_until="domcontentloaded",
                timeout=ACTION_TIMEOUT_MS,
            )
        elif isinstance(action, ClickAction):
            page.locator(action.selector).click(timeout=ACTION_TIMEOUT_MS)
        elif isinstance(action, FillAction):
            page.locator(action.selector).fill(
                action.value,
                timeout=ACTION_TIMEOUT_MS,
            )
        elif isinstance(action, WaitForAction):
            page.locator(action.selector).wait_for(
                state="visible",
                timeout=ACTION_TIMEOUT_MS,
            )
        elif isinstance(action, SelectAction):
            page.locator(action.selector).select_option(
                value=action.value,
                timeout=ACTION_TIMEOUT_MS,
            )
        elif isinstance(action, CheckAction):
            page.locator(action.selector).check(timeout=ACTION_TIMEOUT_MS)
        elif isinstance(action, UncheckAction):
            page.locator(action.selector).uncheck(timeout=ACTION_TIMEOUT_MS)
        elif isinstance(action, PressAction):
            page.locator(action.selector).press(
                action.key,
                timeout=ACTION_TIMEOUT_MS,
            )
    except PlaywrightError as error:
        error_summary = str(error).splitlines()[0]
        result = ActionResult(
            step_number=step_number,
            kind=str(action.kind),
            status="failed",
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
            url_before=url_before,
            url_after=page.url,
            message=error_summary,
        )
    else:
        result = ActionResult(
            step_number=step_number,
            kind=str(action.kind),
            status="passed",
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
            url_before=url_before,
            url_after=page.url,
            message=_success_message(action),
        )

    return ActionExecutionResult(
        action_result=result,
        navigation_response=navigation_response,
    )


def execute_plan(page: Page, plan: ActionPlan) -> PlanExecutionResult:
    navigation_response = None
    action_results: list[ActionResult] = []
    earlier_action_failed = False

    for step_number, action in enumerate(plan.actions, start=1):
        url_before = page.url
        if earlier_action_failed:
            action_results.append(
                ActionResult(
                    step_number=step_number,
                    kind=str(action.kind),
                    status="skipped",
                    duration_ms=0.0,
                    url_before=url_before,
                    url_after=url_before,
                    message="Skipped because an earlier action failed",
                )
            )
            continue

        execution = execute_action(page, action, step_number)
        action_results.append(execution.action_result)
        if isinstance(action, NavigateAction):
            navigation_response = execution.navigation_response
        if execution.action_result.status == "failed":
            earlier_action_failed = True

    return PlanExecutionResult(
        navigation_response=navigation_response,
        action_results=tuple(action_results),
    )
