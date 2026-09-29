import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import AgentStatus, AgentStepResult
from .checks import run_checks
from .plan_loader import PlanLoadError, load_action_plan
from .planner import (
    PlannerError,
    generate_completion_criteria,
    generate_next_decision,
)
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
from .reporting import ReportWriteError, write_json_report
from .runner import (
    PageInspectionError,
    inspect_page,
    inspect_page_with_agent,
)


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openai": "gpt-5.6-luna",
}


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
        default=Path("qa-report.json"),
        help="path for the JSON report (default: qa-report.json)",
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

    if (args.url is None) == (args.plan is None):
        parser.error("provide either a URL or --plan, but not both")
    if args.goal is not None and args.plan is not None:
        parser.error("--goal can only be used with a URL, not --plan")
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

            ai_request_count = 0
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
                ai_request_count += 1
                planning_request_count += 1
                request_number = ai_request_count
                print(
                    f"[AI REQUEST {request_number}] "
                    f"plan agent decision {planning_request_count}",
                    flush=True,
                )
                decision = generate_next_decision(
                    goal,
                    current_url,
                    observation,
                    model,
                    provider=args.provider,
                    previous_action_result=previous_action_result,
                    previous_verification_results=(
                        previous_verification_results
                    ),
                    completion_criteria=frozen_criteria,
                )
                print(
                    f"[AI RESPONSE {request_number}] "
                    f"decision={decision.status}: {decision.reason}",
                    flush=True,
                )
                return decision

            def criteria_generator(
                goal,
                current_url,
                page_title,
                observation,
            ):
                nonlocal ai_request_count
                ai_request_count += 1
                request_number = ai_request_count
                print(
                    f"[AI REQUEST {request_number}] "
                    "generate completion criteria",
                    flush=True,
                )
                criteria = generate_completion_criteria(
                    goal,
                    current_url,
                    page_title,
                    observation,
                    model,
                    provider=args.provider,
                )
                print(
                    f"[AI RESPONSE {request_number}] "
                    f"criteria={len(criteria.assertions)} "
                    f"source={criteria.source}: {criteria.reason}",
                    flush=True,
                )
                for criterion in criteria.assertions:
                    print(f"  criterion: {criterion}", flush=True)
                return criteria

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
