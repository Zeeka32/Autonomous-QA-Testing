from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from playwright.sync_api import Page

from .executor import execute_action
from .models import ActionResult, CheckResult, PageObservation
from .observation import observe_page
from .planner import DecisionStatus, PlannerDecision
from .plans import PlanAssertion


MAX_AGENT_STEPS = 10
MAX_AGENT_RECOVERIES = 2
MAX_VERIFICATION_RETRIES = 2

DecisionPlanner = Callable[
    [
        str,
        str,
        PageObservation,
        ActionResult | None,
        tuple[CheckResult, ...],
        tuple[PlanAssertion, ...],
    ],
    PlannerDecision,
]
CompletionVerifier = Callable[[Page], tuple[CheckResult, ...]]


class AgentStatus(StrEnum):
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"
    STEP_LIMIT_REACHED = "step_limit_reached"
    UNVERIFIED = "unverified"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True)
class AgentStepResult:
    step_number: int
    url: str
    decision_status: DecisionStatus
    action_kind: str | None
    selector: str | None
    reason: str
    execution_status: str | None
    execution_message: str | None = None
    verification_results: tuple[CheckResult, ...] = ()


AgentStepReporter = Callable[[AgentStepResult], None]


@dataclass(frozen=True)
class AgentRunResult:
    status: AgentStatus
    reason: str
    steps: tuple[AgentStepResult, ...]
    action_results: tuple[ActionResult, ...]
    recoveries_used: int = 0
    verification_retries_used: int = 0


class AgentLoopError(RuntimeError):
    """Raised when a planner violates the one-step decision contract."""


def run_agent_loop(
    page: Page,
    goal: str,
    planner: DecisionPlanner,
    max_steps: int = MAX_AGENT_STEPS,
    max_recoveries: int = MAX_AGENT_RECOVERIES,
    max_verification_retries: int = MAX_VERIFICATION_RETRIES,
    starting_step_number: int = 1,
    completion_criteria: tuple[PlanAssertion, ...] = (),
    completion_verifier: CompletionVerifier | None = None,
    step_reporter: AgentStepReporter | None = None,
) -> AgentRunResult:
    if not goal.strip():
        raise AgentLoopError("agent goal must not be blank")
    if max_steps < 1:
        raise AgentLoopError("max_steps must be at least 1")
    if max_recoveries < 0:
        raise AgentLoopError("max_recoveries must be at least 0")
    if max_verification_retries < 0:
        raise AgentLoopError(
            "max_verification_retries must be at least 0"
        )
    if starting_step_number < 1:
        raise AgentLoopError("starting_step_number must be at least 1")

    steps: list[AgentStepResult] = []
    action_results: list[ActionResult] = []
    previous_action_result = None
    previous_verification_results: tuple[CheckResult, ...] = ()
    recoveries_used = 0
    verification_retries_used = 0

    for offset in range(max_steps):
        step_number = starting_step_number + offset
        observation = observe_page(page)
        decision_url = page.url
        decision = planner(
            goal,
            decision_url,
            observation,
            previous_action_result,
            previous_verification_results,
            completion_criteria,
        )
        previous_verification_results = ()
        if not decision.reason.strip():
            raise AgentLoopError("planner decision reason must not be blank")

        if decision.status is DecisionStatus.COMPLETE:
            if decision.action is not None:
                raise AgentLoopError("complete decision included an action")
            verification_results = (
                completion_verifier(page)
                if completion_verifier is not None
                else ()
            )
            step = AgentStepResult(
                step_number=step_number,
                url=decision_url,
                decision_status=decision.status,
                action_kind=None,
                selector=None,
                reason=decision.reason,
                execution_status=None,
                execution_message=None,
                verification_results=verification_results,
            )
            steps.append(step)
            if step_reporter is not None:
                step_reporter(step)
            if completion_verifier is not None and not verification_results:
                return AgentRunResult(
                    status=AgentStatus.UNVERIFIED,
                    reason=(
                        "Agent declared completion without any deterministic "
                        "completion criteria"
                    ),
                    steps=tuple(steps),
                    action_results=tuple(action_results),
                    recoveries_used=recoveries_used,
                    verification_retries_used=verification_retries_used,
                )
            failed_verifications = tuple(
                result for result in verification_results if not result.passed
            )
            if failed_verifications:
                final_step = offset == max_steps - 1
                if (
                    verification_retries_used
                    >= max_verification_retries
                    or final_step
                ):
                    failure_summary = "; ".join(
                        result.message for result in failed_verifications
                    )
                    return AgentRunResult(
                        status=AgentStatus.VERIFICATION_FAILED,
                        reason=failure_summary,
                        steps=tuple(steps),
                        action_results=tuple(action_results),
                        recoveries_used=recoveries_used,
                        verification_retries_used=(
                            verification_retries_used
                        ),
                    )
                verification_retries_used += 1
                previous_action_result = None
                previous_verification_results = failed_verifications
                continue
            return AgentRunResult(
                status=AgentStatus.COMPLETE,
                reason=decision.reason,
                steps=tuple(steps),
                action_results=tuple(action_results),
                recoveries_used=recoveries_used,
                verification_retries_used=verification_retries_used,
            )

        if decision.status is DecisionStatus.BLOCKED:
            if decision.action is not None:
                raise AgentLoopError("blocked decision included an action")
            step = AgentStepResult(
                step_number=step_number,
                url=decision_url,
                decision_status=decision.status,
                action_kind=None,
                selector=None,
                reason=decision.reason,
                execution_status=None,
                execution_message=None,
                verification_results=(),
            )
            steps.append(step)
            if step_reporter is not None:
                step_reporter(step)
            return AgentRunResult(
                status=AgentStatus.BLOCKED,
                reason=decision.reason,
                steps=tuple(steps),
                action_results=tuple(action_results),
                recoveries_used=recoveries_used,
                verification_retries_used=verification_retries_used,
            )

        if decision.action is None:
            raise AgentLoopError("action decision did not include an action")

        execution = execute_action(page, decision.action, step_number)
        action_result = execution.action_result
        action_results.append(action_result)
        step = AgentStepResult(
            step_number=step_number,
            url=decision_url,
            decision_status=decision.status,
            action_kind=str(decision.action.kind),
            selector=decision.action.selector,
            reason=decision.reason,
            execution_status=action_result.status,
            execution_message=action_result.message,
            verification_results=(),
        )
        steps.append(step)
        if step_reporter is not None:
            step_reporter(step)
        previous_action_result = action_result

        if action_result.status == "failed":
            final_step = offset == max_steps - 1
            if recoveries_used >= max_recoveries or final_step:
                return AgentRunResult(
                    status=AgentStatus.FAILED,
                    reason=action_result.message,
                    steps=tuple(steps),
                    action_results=tuple(action_results),
                    recoveries_used=recoveries_used,
                    verification_retries_used=verification_retries_used,
                )
            recoveries_used += 1

    return AgentRunResult(
        status=AgentStatus.STEP_LIMIT_REACHED,
        reason=f"Agent reached the limit of {max_steps} action steps",
        steps=tuple(steps),
        action_results=tuple(action_results),
        recoveries_used=recoveries_used,
        verification_retries_used=verification_retries_used,
    )
