from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .agent import (
    AgentLoopError,
    AgentRunResult,
    AgentStatus,
    AgentStepReporter,
    DecisionPlanner,
    run_agent_loop,
)
from .assertions import evaluate_assertions
from .executor import execute_action, execute_plan
from .models import PageObservation, PageSnapshot
from .observation import observe_page
from .plans import (
    ActionPlan,
    CompletionCriteria,
    CriteriaSource,
    NavigateAction,
    PlanAssertion,
)


class PageInspectionError(RuntimeError):
    """Raised when Playwright cannot inspect a webpage."""


CriteriaGenerator = Callable[
    [str, str, str, PageObservation],
    CompletionCriteria,
]


@dataclass(frozen=True)
class AgentInspectionResult:
    snapshot: PageSnapshot
    agent_run: AgentRunResult
    completion_criteria: CompletionCriteria | None = None


def inspect_page(
    plan: ActionPlan,
    screenshot_path: Path,
    trace_path: Path,
) -> PageSnapshot:
    first_action = plan.actions[0]
    if not isinstance(first_action, NavigateAction):
        raise PageInspectionError("Action plan does not begin with navigation")
    requested_url = first_action.url

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                try:
                    context.tracing.start(
                        screenshots=True,
                        snapshots=True,
                        sources=True,
                    )
                    try:
                        page = context.new_page()

                        execution = execute_plan(page, plan)
                        response = execution.navigation_response
                        final_url = page.url
                        status = response.status if response is not None else None
                        title = page.title()
                        observation = observe_page(page)
                        assertion_results = evaluate_assertions(
                            page,
                            plan.assertions,
                        )
                        page.screenshot(path=screenshot_path, full_page=True)
                    finally:
                        context.tracing.stop(path=trace_path)
                finally:
                    context.close()
            finally:
                browser.close()
    except PlaywrightError as error:
        error_summary = str(error).splitlines()[0]
        raise PageInspectionError(
            f'Could not inspect "{requested_url}": {error_summary}'
        ) from error

    return PageSnapshot(
        url=final_url,
        status=status,
        title=title,
        observation=observation,
        action_results=execution.action_results,
        assertion_results=assertion_results,
    )


def inspect_page_with_agent(
    starting_url: str,
    goal: str,
    planner: DecisionPlanner,
    assertions: tuple[PlanAssertion, ...],
    screenshot_path: Path,
    trace_path: Path,
    criteria_generator: CriteriaGenerator | None = None,
    agent_step_reporter: AgentStepReporter | None = None,
) -> AgentInspectionResult:
    completion_criteria = CompletionCriteria(
        assertions=assertions,
        source=(
            CriteriaSource.USER_PROVIDED
            if assertions
            else CriteriaSource.NONE
        ),
        reason=(
            "Completion criteria were provided by the user"
            if assertions
            else "No completion criteria were available"
        ),
    )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                try:
                    context.tracing.start(
                        screenshots=True,
                        snapshots=True,
                        sources=True,
                    )
                    try:
                        page = context.new_page()
                        navigation = execute_action(
                            page,
                            NavigateAction(url=starting_url),
                            step_number=1,
                        )
                        if navigation.action_result.status == "failed":
                            agent_run = AgentRunResult(
                                status=AgentStatus.FAILED,
                                reason=navigation.action_result.message,
                                steps=(),
                                action_results=(),
                            )
                        else:
                            initial_observation = observe_page(page)
                            if not assertions and criteria_generator is not None:
                                completion_criteria = criteria_generator(
                                    goal,
                                    page.url,
                                    page.title(),
                                    initial_observation,
                                )
                                if completion_criteria.assertions:
                                    initial_results = evaluate_assertions(
                                        page,
                                        completion_criteria.assertions,
                                    )
                                    if all(
                                        result.passed
                                        for result in initial_results
                                    ):
                                        completion_criteria = CompletionCriteria(
                                            assertions=(),
                                            source=CriteriaSource.NONE,
                                            reason=(
                                                "AI-generated criteria were "
                                                "already satisfied on the "
                                                "initial page"
                                            ),
                                        )

                            if not completion_criteria.assertions:
                                agent_run = AgentRunResult(
                                    status=AgentStatus.UNVERIFIED,
                                    reason=completion_criteria.reason,
                                    steps=(),
                                    action_results=(),
                                )
                            else:
                                agent_run = run_agent_loop(
                                    page,
                                    goal,
                                    planner,
                                    starting_step_number=2,
                                    completion_criteria=(
                                        completion_criteria.assertions
                                    ),
                                    completion_verifier=(
                                        lambda current_page: (
                                            evaluate_assertions(
                                                current_page,
                                                completion_criteria.assertions,
                                            )
                                        )
                                    ),
                                    step_reporter=agent_step_reporter,
                                )

                        final_url = page.url
                        response = navigation.navigation_response
                        status = (
                            response.status
                            if response is not None
                            else None
                        )
                        title = page.title()
                        observation = observe_page(page)
                        assertion_results = evaluate_assertions(
                            page,
                            completion_criteria.assertions,
                        )
                        page.screenshot(path=screenshot_path, full_page=True)
                    finally:
                        context.tracing.stop(path=trace_path)
                finally:
                    context.close()
            finally:
                browser.close()
    except (PlaywrightError, AgentLoopError) as error:
        error_summary = str(error).splitlines()[0]
        raise PageInspectionError(
            f'Could not run agent on "{starting_url}": {error_summary}'
        ) from error

    snapshot = PageSnapshot(
        url=final_url,
        status=status,
        title=title,
        observation=observation,
        action_results=(navigation.action_result,)
        + agent_run.action_results,
        assertion_results=assertion_results,
    )
    return AgentInspectionResult(
        snapshot=snapshot,
        agent_run=agent_run,
        completion_criteria=completion_criteria,
    )
