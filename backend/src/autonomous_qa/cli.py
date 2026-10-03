import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import (
    AgentStatus,
    AgentStepResult,
)
from .suite.budgets import (
    DEFAULT_MAX_AI_REQUESTS,
    DEFAULT_MAX_BROWSER_GOALS,
    DEFAULT_MAX_BROWSER_RUNS,
    DEFAULT_MAX_SUITE_SECONDS,
    DEFAULT_MAX_SUITE_TESTS,
    SuiteBudgetValidationError,
    SuiteExecutionPolicy,
)
from .browser.checks import run_checks
from .plan_loader import PlanLoadError, load_action_plan
from .planner import PlannerError
from .plans import (
    ActionPlan,
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
    NavigateAction,
    PlanValidationError,
    TitleContainsAssertion,
    UrlContainsAssertion,
)
from .reporting import (
    ReportWriteError,
    write_json_report,
)
from .browser.runner import (
    PageInspectionError,
    inspect_page,
    inspect_page_with_agent,
)
from .service import (
    DEFAULT_MODELS,
    QaRunError,
    QaRunRequest,
    create_ai_callbacks,
    run_qa,
)
from .suite.suites import SuiteRunResult


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _print_agent_step(step: AgentStepResult) -> None:
    print(
        f"[AGENT] Step {step.step_number} "
        f"decision={step.decision_status} url={step.url}",
        flush=True,
    )
    print(f"  reason: {step.reason}", flush=True)

    if step.action_kind is not None:
        selector = (
            f' selector="{step.selector}"'
            if step.selector is not None
            else ""
        )
        status = (step.execution_status or "unknown").upper()
        print(
            f"  [ACTION {status}] {step.action_kind}{selector}: "
            f"{step.execution_message}",
            flush=True,
        )

    for result in step.verification_results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"  [VERIFY {status}] {result.name}: {result.message}",
            flush=True,
        )


def _print_message(message: str) -> None:
    print(message, flush=True)


def _print_suite_results(suite_run: SuiteRunResult) -> None:
    for result in suite_run.results:
        print(
            f"[{result.status.upper()}] {result.test_id}: "
            f"{result.message} ({result.duration_ms:.3f} ms)"
        )


def _run_suite(request: QaRunRequest) -> int:
    try:
        result = run_qa(
            request,
            on_message=_print_message,
            on_agent_step=_print_agent_step,
        )
    except QaRunError as error:
        if error.suite_run is not None:
            _print_suite_results(error.suite_run)
        print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"Run {error.run_id} output location: {error.run_directory}",
            file=sys.stderr,
        )
        return 2

    _print_suite_results(result.suite_run)
    print(f"Suite report written to: {result.report_path}")
    print(f"Suite artifacts written to: {result.artifact_directory}")
    return 0 if result.passed else 1


def main() -> int:
    load_dotenv(dotenv_path=ENV_FILE, override=False)

    parser = argparse.ArgumentParser(
        description="Run deterministic QA checks against a webpage"
    )
    parser.add_argument("url", nargs="?", help="URL of the webpage to test")
    parser.add_argument("--plan", type=Path, help="path to a JSON action plan")
    parser.add_argument(
        "--goal",
        help="natural-language goal for the AI planner",
    )
    parser.add_argument(
        "--request",
        help="broad request used by AI to generate a test suite",
    )
    parser.add_argument(
        "--suite",
        action="store_true",
        help="run the fixed baseline multi-test suite",
    )
    parser.add_argument(
        "--max-suite-tests",
        type=int,
        default=DEFAULT_MAX_SUITE_TESTS,
        help=(
            "maximum tests in a suite "
            f"(default: {DEFAULT_MAX_SUITE_TESTS})"
        ),
    )
    parser.add_argument(
        "--max-browser-goals",
        type=int,
        default=DEFAULT_MAX_BROWSER_GOALS,
        help=(
            "maximum AI browser-goal tests in a suite "
            f"(default: {DEFAULT_MAX_BROWSER_GOALS})"
        ),
    )
    parser.add_argument(
        "--max-ai-requests",
        type=int,
        default=DEFAULT_MAX_AI_REQUESTS,
        help=(
            "maximum AI requests in a suite "
            f"(default: {DEFAULT_MAX_AI_REQUESTS})"
        ),
    )
    parser.add_argument(
        "--max-browser-runs",
        type=int,
        default=DEFAULT_MAX_BROWSER_RUNS,
        help=(
            "maximum browser launches in a suite "
            f"(default: {DEFAULT_MAX_BROWSER_RUNS})"
        ),
    )
    parser.add_argument(
        "--max-suite-seconds",
        type=float,
        default=DEFAULT_MAX_SUITE_SECONDS,
        help=(
            "maximum suite duration in seconds "
            f"(default: {DEFAULT_MAX_SUITE_SECONDS:g})"
        ),
    )
    parser.add_argument(
        "--provider",
        choices=tuple(DEFAULT_MODELS),
        default="gemini",
        help="AI provider used for planning (default: gemini)",
    )
    parser.add_argument(
        "--model",
        help="provider model used for planning (defaults according to provider)",
    )
    parser.add_argument(
        "--expect-url-contains",
        help="fail unless the final URL contains this text",
    )
    parser.add_argument(
        "--expect-title-contains",
        help="fail unless the final page title contains this text",
    )
    parser.add_argument(
        "--expect-element-visible",
        help="fail unless this selector is visible on the final page",
    )
    parser.add_argument(
        "--expect-element-hidden",
        help="fail unless this selector is hidden",
    )
    parser.add_argument(
        "--expect-element-enabled",
        help="fail unless this selector is enabled",
    )
    parser.add_argument(
        "--expect-element-disabled",
        help="fail unless this selector is disabled",
    )
    parser.add_argument(
        "--expect-element-checked",
        help="fail unless this selector is checked",
    )
    parser.add_argument(
        "--expect-element-unchecked",
        help="fail unless this selector is unchecked",
    )
    parser.add_argument(
        "--expect-element-value",
        nargs=2,
        metavar=("SELECTOR", "VALUE"),
        help="fail unless the selected form control has the exact value",
    )
    parser.add_argument(
        "--expect-element-count",
        nargs=2,
        metavar=("SELECTOR", "COUNT"),
        help="fail unless this selector matches exactly COUNT elements",
    )
    parser.add_argument(
        "--expect-element-attribute",
        nargs=3,
        metavar=("SELECTOR", "ATTRIBUTE", "TEXT"),
        help="fail unless an element attribute contains the expected text",
    )
    parser.add_argument(
        "--expect-element-text",
        nargs=2,
        metavar=("SELECTOR", "TEXT"),
        help="fail unless the selected element contains the expected text",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="single-run JSON report path (default: qa-report.json)",
    )
    parser.add_argument(
        "--runs-dir",
        "--artifacts-dir",
        dest="runs_dir",
        type=Path,
        help=(
            "parent directory for isolated suite runs (default: qa-runs); "
            "--artifacts-dir is an alias"
        ),
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=Path("screenshot.png"),
        help="path for the full-page screenshot (default: screenshot.png)",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("trace.zip"),
        help="path for the Playwright trace (default: trace.zip)",
    )

    args = parser.parse_args()

    suite_mode = args.suite or args.request is not None
    if suite_mode and args.report is not None:
        parser.error(
            "suite reports are saved per run; use --runs-dir instead of --report"
        )
    if not suite_mode and args.runs_dir is not None:
        parser.error("--runs-dir can only be used with --suite or --request")
    if args.report is None:
        args.report = Path("qa-report.json")

    try:
        suite_policy = SuiteExecutionPolicy(
            max_tests=args.max_suite_tests,
            max_browser_goals=args.max_browser_goals,
            max_ai_requests=args.max_ai_requests,
            max_browser_runs=args.max_browser_runs,
            max_duration_seconds=args.max_suite_seconds,
        )
    except SuiteBudgetValidationError as error:
        parser.error(str(error))

    if (args.url is None) == (args.plan is None):
        parser.error("provide either a URL or --plan, but not both")
    if args.goal is not None and args.plan is not None:
        parser.error("--goal can only be used with a URL, not --plan")
    if args.request is not None and args.plan is not None:
        parser.error("--request can only be used with a URL, not --plan")
    if args.request is not None and args.goal is not None:
        parser.error("--request and --goal cannot be used together")
    if args.request is not None and args.suite:
        parser.error("--request and --suite cannot be used together")
    if args.request is not None and not args.request.strip():
        parser.error("--request must not be blank")
    if args.suite and args.plan is not None:
        parser.error("--suite can only be used with a URL, not --plan")
    if args.suite and args.goal is not None:
        parser.error("--goal cannot be used with --suite yet")
    if (
        args.expect_url_contains is not None
        and not args.expect_url_contains.strip()
    ):
        parser.error("--expect-url-contains must not be blank")
    if (
        args.expect_title_contains is not None
        and not args.expect_title_contains.strip()
    ):
        parser.error("--expect-title-contains must not be blank")
    if (
        args.expect_element_visible is not None
        and not args.expect_element_visible.strip()
    ):
        parser.error("--expect-element-visible must not be blank")
    element_state_options = {
        "--expect-element-hidden": args.expect_element_hidden,
        "--expect-element-enabled": args.expect_element_enabled,
        "--expect-element-disabled": args.expect_element_disabled,
        "--expect-element-checked": args.expect_element_checked,
        "--expect-element-unchecked": args.expect_element_unchecked,
    }
    for option, selector in element_state_options.items():
        if selector is not None and not selector.strip():
            parser.error(f"{option} must not be blank")
    if args.expect_element_value is not None:
        selector, _ = args.expect_element_value
        if not selector.strip():
            parser.error(
                "--expect-element-value selector must not be blank"
            )
    expected_element_count = None
    if args.expect_element_count is not None:
        selector, count_text = args.expect_element_count
        if not selector.strip():
            parser.error(
                "--expect-element-count selector must not be blank"
            )
        try:
            expected_element_count = int(count_text)
        except ValueError:
            parser.error(
                "--expect-element-count COUNT must be a non-negative integer"
            )
        if expected_element_count < 0:
            parser.error(
                "--expect-element-count COUNT must be a non-negative integer"
            )
    if args.expect_element_attribute is not None and not all(
        value.strip() for value in args.expect_element_attribute
    ):
        parser.error(
            "--expect-element-attribute values must not be blank"
        )
    if args.expect_element_text is not None and not all(
        value.strip() for value in args.expect_element_text
    ):
        parser.error(
            "--expect-element-text selector and text must not be blank"
        )
    expectation_values = (
        args.expect_url_contains,
        args.expect_title_contains,
        args.expect_element_visible,
        args.expect_element_hidden,
        args.expect_element_enabled,
        args.expect_element_disabled,
        args.expect_element_checked,
        args.expect_element_unchecked,
        args.expect_element_value,
        args.expect_element_count,
        args.expect_element_attribute,
        args.expect_element_text,
    )
    if (args.suite or args.request is not None) and any(
        value is not None for value in expectation_values
    ):
        parser.error(
            "expectation options cannot be used with suite modes yet"
        )

    try:
        if args.plan is not None:
            plan = load_action_plan(args.plan)
        else:
            plan = ActionPlan(actions=(NavigateAction(url=args.url),))
    except (PlanLoadError, PlanValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    requested_url = plan.actions[0].url
    print(f"processing url: {requested_url}", flush=True)

    if args.suite or args.request is not None:
        try:
            request = QaRunRequest(
                url=requested_url,
                request=args.request,
                provider=args.provider,
                model=args.model,
                budget_policy=suite_policy,
                runs_directory=args.runs_dir or Path("qa-runs"),
            )
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        return _run_suite(request)

    additional_assertions = []
    if args.expect_url_contains is not None:
        additional_assertions.append(
            UrlContainsAssertion(args.expect_url_contains)
        )
    if args.expect_title_contains is not None:
        additional_assertions.append(
            TitleContainsAssertion(args.expect_title_contains)
        )
    if args.expect_element_visible is not None:
        additional_assertions.append(
            ElementVisibleAssertion(args.expect_element_visible)
        )
    state_assertions = (
        (args.expect_element_hidden, ElementHiddenAssertion),
        (args.expect_element_enabled, ElementEnabledAssertion),
        (args.expect_element_disabled, ElementDisabledAssertion),
        (args.expect_element_checked, ElementCheckedAssertion),
        (args.expect_element_unchecked, ElementUncheckedAssertion),
    )
    for selector, assertion_type in state_assertions:
        if selector is not None:
            additional_assertions.append(assertion_type(selector))
    if args.expect_element_value is not None:
        selector, value = args.expect_element_value
        additional_assertions.append(
            ElementValueEqualsAssertion(selector, value)
        )
    if args.expect_element_count is not None:
        selector, _ = args.expect_element_count
        additional_assertions.append(
            ElementCountEqualsAssertion(
                selector,
                expected_element_count,
            )
        )
    if args.expect_element_attribute is not None:
        selector, attribute, value = args.expect_element_attribute
        additional_assertions.append(
            ElementAttributeContainsAssertion(
                selector,
                attribute,
                value,
            )
        )
    if args.expect_element_text is not None:
        selector, value = args.expect_element_text
        additional_assertions.append(
            ElementTextContainsAssertion(selector, value)
        )
    if additional_assertions:
        plan = ActionPlan(
            actions=plan.actions,
            assertions=plan.assertions + tuple(additional_assertions),
        )

    agent_run = None
    completion_criteria = None
    try:
        if args.goal is not None:
            model = args.model or DEFAULT_MODELS[args.provider]
            print(
                f"running agent with {args.provider} model: {model}",
                flush=True,
            )

            planner, criteria_generator = create_ai_callbacks(
                args.provider,
                model,
                on_message=_print_message,
            )

            inspection = inspect_page_with_agent(
                requested_url,
                args.goal,
                planner,
                plan.assertions,
                args.screenshot,
                args.trace,
                criteria_generator,
                _print_agent_step,
            )
            snapshot = inspection.snapshot
            agent_run = inspection.agent_run
            completion_criteria = inspection.completion_criteria
        else:
            snapshot = inspect_page(plan, args.screenshot, args.trace)
    except (PageInspectionError, PlannerError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    results = run_checks(snapshot)

    for action in snapshot.action_results:
        label = action.status.upper()
        print(
            f"[{label}] Step {action.step_number} {action.kind}: "
            f"{action.message} ({action.duration_ms:.3f} ms)"
        )

    for result in results:
        label = "PASS" if result.passed else "FAIL"
        print(f"[{label}] {result.name}: {result.message}")

    if completion_criteria is not None:
        print(
            "Completion criteria "
            f"({completion_criteria.source}): "
            f"{completion_criteria.reason}"
        )

    if agent_run is not None:
        print(
            f"[{agent_run.status.upper()}] Agent: {agent_run.reason}"
        )

    try:
        write_json_report(
            args.report,
            requested_url,
            snapshot,
            results,
            args.screenshot,
            args.trace,
            agent_run,
            completion_criteria,
        )
    except ReportWriteError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print(f"Report written to: {args.report}")
    print(f"Screenshot written to: {args.screenshot}")
    print(f"Trace written to: {args.trace}")

    actions_passed = (
        all(action.status == "passed" for action in snapshot.action_results)
        if agent_run is None
        else agent_run.status is AgentStatus.COMPLETE
    )
    passed = actions_passed and all(result.passed for result in results)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
