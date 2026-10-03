"""Application workflow shared by the CLI and future API callers."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .agent import AgentStepReporter, DecisionPlanner
from .suite.budgets import (
    SuiteBudgetExceeded,
    SuiteBudgetSnapshot,
    SuiteBudgetTracker,
    SuiteExecutionPolicy,
)
from .planner import (
    PlannerError,
    generate_completion_criteria,
    generate_next_decision,
    generate_test_suite,
)
from .plans import ActionPlan, NavigateAction
from .reporting import ReportWriteError, write_suite_json_report
from .run_storage import RunPaths
from .browser.runner import (
    CriteriaGenerator,
    PageInspectionError,
    inspect_accessibility,
    inspect_page,
    inspect_page_with_agent,
)
from .suite.suite_executors import create_suite_executors
from .suite.suite_runner import SuiteRunnerError, run_test_suite
from .suite.suites import (
    MAX_SUITE_REQUEST_LENGTH,
    SuiteRunResult,
    TestCase,
    TestKind,
    TestSuite,
)


DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openai": "gpt-5.6-luna",
}
MessageReporter = Callable[[str], None]


@dataclass(frozen=True)
class QaRunRequest:
    """No request text means the fixed baseline suite; text means AI planning."""

    url: str
    request: str | None = None
    provider: str = "gemini"
    model: str | None = None
    budget_policy: SuiteExecutionPolicy = field(
        default_factory=SuiteExecutionPolicy
    )
    runs_directory: Path = Path("qa-runs")

    def __post_init__(self) -> None:
        # Reuse the browser action's URL validation before any side effects.
        NavigateAction(url=self.url)
        if self.request is not None:
            if not isinstance(self.request, str) or not self.request.strip():
                raise ValueError("QA request must be a non-blank string")
            if len(self.request) > MAX_SUITE_REQUEST_LENGTH:
                raise ValueError(
                    "QA request cannot exceed "
                    f"{MAX_SUITE_REQUEST_LENGTH} characters"
                )
        if self.provider not in DEFAULT_MODELS:
            raise ValueError(f'Unsupported AI provider: "{self.provider}"')
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model.strip()
        ):
            raise ValueError("QA model must be a non-blank string")
        if not isinstance(self.budget_policy, SuiteExecutionPolicy):
            raise ValueError("QA budget_policy must be a SuiteExecutionPolicy")
        if not isinstance(self.runs_directory, Path):
            raise ValueError("QA runs_directory must be a Path")

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.provider]


@dataclass(frozen=True)
class QaRunResult:
    run_id: str
    run_directory: Path
    suite_run: SuiteRunResult
    budget: SuiteBudgetSnapshot
    report_path: Path
    artifact_directory: Path

    @property
    def passed(self) -> bool:
        return self.suite_run.passed


class QaRunError(RuntimeError):
    """A workflow failure, distinct from completed tests that failed."""

    def __init__(
        self,
        message: str,
        budget: SuiteBudgetSnapshot,
        suite_run: SuiteRunResult | None = None,
        *,
        run_paths: RunPaths,
    ) -> None:
        super().__init__(message)
        self.budget = budget
        self.suite_run = suite_run
        self.run_id = run_paths.run_id
        self.run_directory = run_paths.run_directory
        self.report_path = run_paths.report_path
        self.artifact_directory = run_paths.artifact_directory


def _ignore_message(message: str) -> None:
    pass


def create_ai_callbacks(
    provider: str,
    model: str,
    initial_request_count: int = 0,
    budget: SuiteBudgetTracker | None = None,
    on_message: MessageReporter | None = None,
) -> tuple[DecisionPlanner, CriteriaGenerator]:
    emit = on_message or _ignore_message
    ai_request_count = initial_request_count
    planning_request_count = 0

    def planner(
        goal,
        current_url,
        observation,
        previous_action_result,
        previous_verification_results,
        frozen_criteria,
    ):
        nonlocal ai_request_count, planning_request_count
        if budget is not None:
            budget.consume_ai_request()
        ai_request_count += 1
        planning_request_count += 1
        request_number = ai_request_count
        emit(
            f"[AI REQUEST {request_number}] "
            f"plan agent decision {planning_request_count}",
        )
        decision = generate_next_decision(
            goal,
            current_url,
            observation,
            model,
            provider=provider,
            previous_action_result=previous_action_result,
            previous_verification_results=previous_verification_results,
            completion_criteria=frozen_criteria,
        )
        emit(
            f"[AI RESPONSE {request_number}] "
            f"decision={decision.status}: {decision.reason}",
        )
        return decision

    def criteria_generator(
        goal,
        current_url,
        page_title,
        observation,
    ):
        nonlocal ai_request_count
        if budget is not None:
            budget.consume_ai_request()
        ai_request_count += 1
        request_number = ai_request_count
        emit(
            f"[AI REQUEST {request_number}] generate completion criteria",
        )
        criteria = generate_completion_criteria(
            goal,
            current_url,
            page_title,
            observation,
            model,
            provider=provider,
        )
        emit(
            f"[AI RESPONSE {request_number}] "
            f"criteria={len(criteria.assertions)} "
            f"source={criteria.source}: {criteria.reason}",
        )
        for criterion in criteria.assertions:
            emit(f"  criterion: {criterion}")
        return criteria

    return planner, criteria_generator


def run_qa(
    request: QaRunRequest,
    *,
    on_message: MessageReporter | None = None,
    on_agent_step: AgentStepReporter | None = None,
    run_paths: RunPaths | None = None,
) -> QaRunResult:
    """Run a suite and save its report without reading CLI input or printing.

    Expected setup/planning/report errors raise QaRunError. Failed or skipped
    test cases are returned normally in QaRunResult.
    """

    budget = SuiteBudgetTracker(request.budget_policy)
    paths = run_paths or RunPaths(request.runs_directory)
    if paths.runs_directory != request.runs_directory:
        raise ValueError("Run paths must use the request runs directory")
    emit = on_message or _ignore_message
    suite_run = None
    try:
        paths.create()
        emit(f"Run ID: {paths.run_id}")
        initial_snapshots = {}
        planner = None
        criteria_generator = None
        if request.request is None:
            suite = TestSuite(
                url=request.url,
                request="Run baseline page-load and title checks",
                tests=(
                    TestCase(
                        test_id="page-load",
                        name="Page loads successfully",
                        kind=TestKind.PAGE_LOAD,
                    ),
                    TestCase(
                        test_id="page-title",
                        name="Page has a title",
                        kind=TestKind.TITLE_PRESENT,
                    ),
                ),
            )
        else:
            budget.consume_browser_run()
            snapshot = inspect_page(
                ActionPlan(actions=(NavigateAction(url=request.url),)),
                paths.artifact_directory / "baseline-screenshot.png",
                paths.artifact_directory / "baseline-trace.zip",
            )
            if snapshot.observation is None:
                raise PageInspectionError(
                    "Initial page observation is unavailable"
                )
            initial_snapshots[request.url] = snapshot
            emit(
                f"planning test suite with {request.provider} model: "
                f"{request.resolved_model}"
            )
            budget.consume_ai_request()
            emit("[AI REQUEST 1] generate test suite")
            suite = generate_test_suite(
                request.request,
                request.url,
                snapshot.title,
                snapshot.observation,
                request.resolved_model,
                provider=request.provider,
            )
            emit(f"[AI RESPONSE 1] generated {len(suite.tests)} tests")
            for test in suite.tests:
                goal = f' goal="{test.goal}"' if test.goal is not None else ""
                emit(f"  test: {test.test_id} kind={test.kind}{goal}")
            planner, criteria_generator = create_ai_callbacks(
                request.provider,
                request.resolved_model,
                initial_request_count=1,
                budget=budget,
                on_message=on_message,
            )

        executors = create_suite_executors(
            paths.artifact_directory,
            planner=planner,
            criteria_generator=criteria_generator,
            agent_step_reporter=on_agent_step,
            page_inspector=inspect_page,
            accessibility_inspector=inspect_accessibility,
            agent_inspector=inspect_page_with_agent,
            initial_snapshots=initial_snapshots,
            budget=budget,
        )
        suite_run = run_test_suite(suite, executors, budget=budget)
        budget_snapshot = budget.snapshot()
        write_suite_json_report(
            paths.report_path,
            suite_run,
            paths.artifact_directory,
            budget_snapshot=budget_snapshot,
            run_id=paths.run_id,
        )
    except (
        PageInspectionError,
        PlannerError,
        SuiteBudgetExceeded,
        SuiteRunnerError,
        ReportWriteError,
        OSError,
    ) as error:
        raise QaRunError(
            str(error), budget.snapshot(), suite_run=suite_run,
            run_paths=paths,
        ) from error

    return QaRunResult(
        run_id=paths.run_id,
        run_directory=paths.run_directory,
        suite_run=suite_run,
        budget=budget_snapshot,
        report_path=paths.report_path,
        artifact_directory=paths.artifact_directory,
    )
