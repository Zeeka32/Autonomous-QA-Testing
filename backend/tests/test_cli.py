import json
import sys

import pytest

from autonomous_qa import service

from autonomous_qa import cli
from autonomous_qa.agent import (
    AgentRunResult,
    AgentStatus,
    AgentStepResult,
)
from autonomous_qa.models import (
    ActionResult,
    CheckResult,
    PageObservation,
    PageSnapshot,
)
from autonomous_qa.plans import (
    ActionPlan,
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
    TitleContainsAssertion,
    UrlContainsAssertion,
)
from autonomous_qa.planner import (
    DecisionStatus,
    PlannerDecision,
    PlannerError,
)
from autonomous_qa.reporting import ReportWriteError
from autonomous_qa.runner import AgentInspectionResult, PageInspectionError
from autonomous_qa.suites import (
    TestCase as SuiteCase,
    TestKind as SuiteTestKind,
    TestSuite as SuiteDefinition,
)


def set_cli_arguments(monkeypatch, tmp_path, url: str) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            url,
            "--report",
            str(tmp_path / "report.json"),
            "--screenshot",
            str(tmp_path / "page.png"),
            "--trace",
            str(tmp_path / "trace.zip"),
        ],
    )


def test_cli_prints_live_agent_step_diagnostics(capsys) -> None:
    cli._print_agent_step(
        AgentStepResult(
            step_number=2,
            url="https://example.com",
            decision_status=DecisionStatus.ACTION,
            action_kind="click",
            selector="a.more",
            reason="Open the Learn more link",
            execution_status="passed",
            execution_message="Clicked the link",
            verification_results=(
                CheckResult(
                    name="Expected URL",
                    passed=True,
                    message="Final URL contains iana.org",
                ),
            ),
        )
    )

    output = capsys.readouterr().out
    assert "[AGENT] Step 2 decision=action" in output
    assert '[ACTION PASSED] click selector="a.more"' in output
    assert "[VERIFY PASS] Expected URL" in output


def test_cli_returns_zero_when_all_checks_pass(monkeypatch, tmp_path) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    monkeypatch.setattr(
        cli,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
        ),
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert (tmp_path / "report.json").exists()


def test_cli_returns_one_when_a_check_fails(monkeypatch, tmp_path) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com/missing")
    monkeypatch.setattr(
        cli,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url=plan.actions[0].url,
            status=404,
            title="Not Found",
        ),
    )

    exit_code = cli.main()

    assert exit_code == 1
    assert (tmp_path / "report.json").exists()


def test_cli_returns_one_and_writes_report_when_an_action_fails(
    monkeypatch,
    tmp_path,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    monkeypatch.setattr(
        cli,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            action_results=(
                ActionResult(
                    step_number=1,
                    kind="navigate",
                    status="failed",
                    duration_ms=10_000.0,
                    url_before="about:blank",
                    url_after="https://example.com/",
                    message="Timeout 10000ms exceeded",
                ),
            ),
        ),
    )

    exit_code = cli.main()

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["passed"] is False
    assert report["actions"][0]["message"] == "Timeout 10000ms exceeded"


def test_cli_checks_the_expected_final_url(monkeypatch, tmp_path) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    sys.argv.extend(["--expect-url-contains", "iana.org"])
    inspected_plans = []

    def inspect_plan(plan, screenshot, trace):
        inspected_plans.append(plan)
        return PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            assertion_results=(
                CheckResult(
                    name="Expected URL",
                    passed=False,
                    message=(
                        'Final URL "https://example.com/" '
                        'does not contain "iana.org"'
                    ),
                ),
            ),
        )

    monkeypatch.setattr(cli, "inspect_page", inspect_plan)

    exit_code = cli.main()

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["passed"] is False
    assert report["checks"][-1]["name"] == "Expected URL"
    assert report["checks"][-1]["passed"] is False
    assert inspected_plans[0].assertions == (
        UrlContainsAssertion(value="iana.org"),
    )


def test_cli_adds_element_state_and_text_expectations(
    monkeypatch,
    tmp_path,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    sys.argv.extend(
        [
            "--expect-title-contains",
            "Complete",
            "--expect-element-visible",
            "#result",
            "--expect-element-hidden",
            "#spinner",
            "--expect-element-enabled",
            "#submit",
            "--expect-element-disabled",
            "#cancel",
            "--expect-element-checked",
            "#terms",
            "--expect-element-unchecked",
            "#newsletter",
            "--expect-element-value",
            "#name",
            "Ada",
            "--expect-element-count",
            ".result",
            "2",
            "--expect-element-attribute",
            "#status",
            "class",
            "complete",
            "--expect-element-text",
            "#result",
            "Submission complete",
        ]
    )
    inspected_plans = []

    def inspect_plan(plan, screenshot, trace):
        inspected_plans.append(plan)
        return PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Complete",
        )

    monkeypatch.setattr(cli, "inspect_page", inspect_plan)

    exit_code = cli.main()

    assert exit_code == 0
    assert inspected_plans[0].assertions == (
        TitleContainsAssertion(value="Complete"),
        ElementVisibleAssertion(selector="#result"),
        ElementHiddenAssertion(selector="#spinner"),
        ElementEnabledAssertion(selector="#submit"),
        ElementDisabledAssertion(selector="#cancel"),
        ElementCheckedAssertion(selector="#terms"),
        ElementUncheckedAssertion(selector="#newsletter"),
        ElementValueEqualsAssertion(selector="#name", value="Ada"),
        ElementCountEqualsAssertion(selector=".result", count=2),
        ElementAttributeContainsAssertion(
            selector="#status",
            attribute="class",
            value="complete",
        ),
        ElementTextContainsAssertion(
            selector="#result",
            value="Submission complete",
        ),
    )


def test_cli_returns_two_when_inspection_fails(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://unavailable.example")

    def fail_inspection(plan, screenshot, trace):
        raise PageInspectionError("Could not inspect the page")

    monkeypatch.setattr(cli, "inspect_page", fail_inspection)

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR: Could not inspect the page" in captured.err
    assert not (tmp_path / "report.json").exists()


def test_cli_returns_two_when_report_writing_fails(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    monkeypatch.setattr(
        cli,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url=plan.actions[0].url,
            status=200,
            title="Example Domain",
        ),
    )

    def fail_report(*args, **kwargs):
        raise ReportWriteError("Disk is unavailable")

    monkeypatch.setattr(cli, "write_json_report", fail_report)

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR: Disk is unavailable" in captured.err


def test_cli_accepts_a_json_action_plan(monkeypatch, tmp_path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        """
        {
          "actions": [
            {"kind": "navigate", "url": "https://example.com"},
            {"kind": "click", "selector": "#submit"}
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "--plan",
            str(plan_path),
            "--report",
            str(tmp_path / "report.json"),
            "--screenshot",
            str(tmp_path / "page.png"),
            "--trace",
            str(tmp_path / "trace.zip"),
        ],
    )
    received_plans = []

    def inspect_plan(plan, screenshot, trace):
        received_plans.append(plan)
        return PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
        )

    monkeypatch.setattr(cli, "inspect_page", inspect_plan)

    exit_code = cli.main()

    assert exit_code == 0
    assert [action.kind for action in received_plans[0].actions] == [
        "navigate",
        "click",
    ]


def test_cli_evaluates_assertions_from_a_json_plan(
    monkeypatch,
    tmp_path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        """
        {
          "actions": [
            {"kind": "navigate", "url": "https://example.com"}
          ],
          "assertions": [
            {"kind": "url_contains", "value": "iana.org"}
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "--plan",
            str(plan_path),
            "--report",
            str(tmp_path / "report.json"),
            "--screenshot",
            str(tmp_path / "page.png"),
            "--trace",
            str(tmp_path / "trace.zip"),
        ],
    )
    monkeypatch.setattr(
        cli,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            assertion_results=(
                CheckResult(
                    name="Expected URL",
                    passed=False,
                    message=(
                        'Final URL "https://example.com/" '
                        'does not contain "iana.org"'
                    ),
                ),
            ),
        ),
    )

    exit_code = cli.main()

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["checks"][-1]["name"] == "Expected URL"
    assert report["checks"][-1]["passed"] is False


def test_cli_runs_a_goal_through_the_agent_loop(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    sys.argv.extend(
        [
            "--goal",
            "Open the details button",
            "--model",
            "test-model",
            "--expect-url-contains",
            "details",
        ]
    )
    observation = PageObservation(elements=(), truncated=False)
    planner_calls = []

    def generate_decision(
        goal,
        current_url,
        supplied_observation,
        model,
        client=None,
        provider="openai",
        previous_action_result=None,
        previous_verification_results=(),
        completion_criteria=(),
    ):
        planner_calls.append(
            (
                goal,
                current_url,
                supplied_observation,
                model,
                provider,
                previous_action_result,
                previous_verification_results,
                completion_criteria,
            )
        )
        return PlannerDecision(
            status=DecisionStatus.COMPLETE,
            action=None,
            reason="Goal reached",
        )

    inspection_calls = []

    def inspect_with_agent(
        starting_url,
        goal,
        planner,
        assertions,
        screenshot,
        trace,
        criteria_generator,
        agent_step_reporter,
    ):
        inspection_calls.append(
            (
                starting_url,
                goal,
                assertions,
                screenshot,
                trace,
            )
        )
        assert agent_step_reporter is cli._print_agent_step
        decision = planner(
            goal,
            starting_url,
            observation,
            None,
            (),
            assertions,
        )
        assert decision.status is DecisionStatus.COMPLETE
        return AgentInspectionResult(
            snapshot=PageSnapshot(
                url="https://example.com/",
                status=200,
                title="Example Domain",
                observation=observation,
            ),
            agent_run=AgentRunResult(
                status=AgentStatus.COMPLETE,
                reason="Goal reached",
                steps=(),
                action_results=(),
            ),
            completion_criteria=CompletionCriteria(
                assertions=assertions,
                source=CriteriaSource.USER_PROVIDED,
                reason="Completion criteria were provided by the user",
            ),
        )

    monkeypatch.setattr(service, "generate_next_decision", generate_decision)
    monkeypatch.setattr(cli, "inspect_page_with_agent", inspect_with_agent)

    exit_code = cli.main()

    output = capsys.readouterr().out
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "[AI REQUEST 1] plan agent decision 1" in output
    assert "[AI RESPONSE 1] decision=complete: Goal reached" in output
    assert inspection_calls == [
        (
            "https://example.com",
            "Open the details button",
            (UrlContainsAssertion(value="details"),),
            tmp_path / "page.png",
            tmp_path / "trace.zip",
        )
    ]
    assert planner_calls == [
        (
            "Open the details button",
            "https://example.com",
            observation,
            "test-model",
            "gemini",
            None,
            (),
            (UrlContainsAssertion(value="details"),),
        )
    ]
    assert report["agent"]["status"] == "complete"
    assert report["agent"]["reason"] == "Goal reached"
    assert report["completion"]["source"] == "user_provided"


def test_cli_passes_when_an_agent_recovers_from_a_failed_action(
    monkeypatch,
    tmp_path,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    sys.argv.extend(["--goal", "Open the details button"])
    failed_action = ActionResult(
        step_number=2,
        kind="click",
        status="failed",
        duration_ms=10_000.0,
        url_before="https://example.com/",
        url_after="https://example.com/",
        message="First selector timed out",
    )

    monkeypatch.setattr(
        cli,
        "inspect_page_with_agent",
        lambda *args: AgentInspectionResult(
            snapshot=PageSnapshot(
                url="https://example.com/complete",
                status=200,
                title="Complete",
                action_results=(failed_action,),
            ),
            agent_run=AgentRunResult(
                status=AgentStatus.COMPLETE,
                reason="Goal reached after choosing another control",
                steps=(),
                action_results=(failed_action,),
                recoveries_used=1,
            ),
        ),
    )

    exit_code = cli.main()

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["passed"] is True
    assert report["actions"][0]["status"] == "failed"
    assert report["agent"]["recoveries_used"] == 1


def test_cli_fails_when_agent_completion_is_unverified(
    monkeypatch,
    tmp_path,
) -> None:
    set_cli_arguments(monkeypatch, tmp_path, "https://example.com")
    sys.argv.extend(["--goal", "Open the details button"])

    monkeypatch.setattr(
        cli,
        "inspect_page_with_agent",
        lambda *args: AgentInspectionResult(
            snapshot=PageSnapshot(
                url="https://example.com/",
                status=200,
                title="Example Domain",
            ),
            agent_run=AgentRunResult(
                status=AgentStatus.UNVERIFIED,
                reason="No deterministic completion criteria",
                steps=(),
                action_results=(),
            ),
        ),
    )

    exit_code = cli.main()

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["passed"] is False
    assert report["agent"]["status"] == "unverified"


def test_cli_runs_the_fixed_baseline_suite(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--suite",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    inspection_calls = []

    def inspect(plan, screenshot_path, trace_path):
        inspection_calls.append((plan, screenshot_path, trace_path))
        return PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
        )

    monkeypatch.setattr(service, "inspect_page", inspect)

    exit_code = cli.main()

    output = capsys.readouterr().out
    report_path = next((tmp_path / "runs").glob("*/report.json"))
    artifact_directory = report_path.parent / "artifacts"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(inspection_calls) == 1
    plan, screenshot_path, trace_path = inspection_calls[0]
    assert plan.actions[0].url == "https://example.com"
    assert screenshot_path == artifact_directory / "baseline-screenshot.png"
    assert trace_path == artifact_directory / "baseline-trace.zip"
    assert "[PASSED] page-load: Page returned HTTP 200" in output
    assert '[PASSED] page-title: Page title is "Example Domain"' in output
    assert f"Run ID: {report['run_id']}" in output
    assert report_path.parent.name == report["run_id"]
    assert report["passed"] is True
    assert [test["test_id"] for test in report["tests"]] == [
        "page-load",
        "page-title",
    ]
    assert report["artifacts"]["directory"] == str(artifact_directory)
    assert report["budget"]["usage"]["ai_requests"] == 0
    assert report["budget"]["usage"]["browser_runs"] == 1
    assert report["budget"]["exhausted"] is False


def test_cli_suite_returns_one_when_a_case_fails(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--suite",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    monkeypatch.setattr(
        service,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url="https://example.com/",
            status=503,
            title="",
        ),
    )

    exit_code = cli.main()

    report_path = next((tmp_path / "runs").glob("*/report.json"))
    artifact_directory = report_path.parent / "artifacts"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["passed"] is False
    assert [test["status"] for test in report["tests"]] == [
        "failed",
        "failed",
    ]


def test_cli_suite_rejects_goal_mode(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--suite",
            "--goal",
            "Open the menu",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert "--goal cannot be used with --suite yet" in capsys.readouterr().err


def test_cli_suite_returns_two_when_report_writing_fails(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--suite",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    monkeypatch.setattr(
        service,
        "inspect_page",
        lambda plan, screenshot, trace: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
        ),
    )

    def fail_report(*args, **kwargs):
        raise ReportWriteError("Disk is unavailable")

    monkeypatch.setattr(service, "write_suite_json_report", fail_report)

    exit_code = cli.main()

    assert exit_code == 2
    assert "ERROR: Disk is unavailable" in capsys.readouterr().err


def test_cli_generates_and_runs_a_suite_from_a_broad_request(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--request",
            "Run basic smoke tests",
            "--model",
            "test-model",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    observation = PageObservation(elements=(), truncated=False)
    inspection_calls = []

    def inspect(plan, screenshot_path, trace_path):
        inspection_calls.append((plan, screenshot_path, trace_path))
        return PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            observation=observation,
        )

    generation_calls = []

    def generate_suite(
        request,
        starting_url,
        page_title,
        supplied_observation,
        model,
        client=None,
        provider="openai",
    ):
        generation_calls.append(
            (
                request,
                starting_url,
                page_title,
                supplied_observation,
                model,
                provider,
            )
        )
        return SuiteDefinition(
            url=starting_url,
            request=request,
            tests=(
                SuiteCase(
                    test_id="page-load",
                    name="Page loads",
                    kind=SuiteTestKind.PAGE_LOAD,
                ),
                SuiteCase(
                    test_id="page-title",
                    name="Page has a title",
                    kind=SuiteTestKind.TITLE_PRESENT,
                ),
            ),
        )

    monkeypatch.setattr(service, "inspect_page", inspect)
    monkeypatch.setattr(service, "generate_test_suite", generate_suite)

    exit_code = cli.main()

    output = capsys.readouterr().out
    report_path = next((tmp_path / "runs").glob("*/report.json"))
    artifact_directory = report_path.parent / "artifacts"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(inspection_calls) == 1
    assert inspection_calls[0][1:] == (
        artifact_directory / "baseline-screenshot.png",
        artifact_directory / "baseline-trace.zip",
    )
    assert generation_calls == [
        (
            "Run basic smoke tests",
            "https://example.com",
            "Example Domain",
            observation,
            "test-model",
            "gemini",
        )
    ]
    assert "[AI REQUEST 1] generate test suite" in output
    assert "[AI RESPONSE 1] generated 2 tests" in output
    assert report["request"] == "Run basic smoke tests"
    assert [test["kind"] for test in report["tests"]] == [
        "page_load",
        "title_present",
    ]
    assert report["budget"]["usage"]["ai_requests"] == 1
    assert report["budget"]["usage"]["browser_runs"] == 1
    assert report["budget"]["exhausted"] is False


def test_cli_generated_browser_goal_uses_existing_agent_callbacks(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--request",
            "Test the main interaction",
            "--model",
            "test-model",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    observation = PageObservation(elements=(), truncated=False)
    monkeypatch.setattr(
        service,
        "inspect_page",
        lambda *args: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            observation=observation,
        ),
    )
    monkeypatch.setattr(
        service,
        "generate_test_suite",
        lambda request, starting_url, *args, **kwargs: SuiteDefinition(
            url=starting_url,
            request=request,
            tests=(
                SuiteCase(
                    test_id="complete-workflow",
                    name="Complete the workflow",
                    kind=SuiteTestKind.BROWSER_GOAL,
                    goal="Complete the main workflow",
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        service,
        "generate_completion_criteria",
        lambda *args, **kwargs: CompletionCriteria(
            assertions=(TitleContainsAssertion(value="Complete"),),
            source=CriteriaSource.AI_GENERATED,
            reason="The final title proves completion",
        ),
    )
    monkeypatch.setattr(
        service,
        "generate_next_decision",
        lambda *args, **kwargs: PlannerDecision(
            status=DecisionStatus.COMPLETE,
            action=None,
            reason="The workflow is complete",
        ),
    )

    def inspect_with_agent(
        starting_url,
        goal,
        planner,
        assertions,
        screenshot,
        trace,
        criteria_generator,
        agent_step_reporter,
    ):
        criteria = criteria_generator(
            goal,
            starting_url,
            "Example Domain",
            observation,
        )
        decision = planner(
            goal,
            starting_url,
            observation,
            None,
            (),
            criteria.assertions,
        )
        assert decision.status is DecisionStatus.COMPLETE
        return AgentInspectionResult(
            snapshot=PageSnapshot(
                url=starting_url,
                status=200,
                title="Complete",
                observation=observation,
                assertion_results=(
                    CheckResult(
                        name="Expected title",
                        passed=True,
                        message='Page title contains "Complete"',
                    ),
                ),
            ),
            agent_run=AgentRunResult(
                status=AgentStatus.COMPLETE,
                reason=decision.reason,
                steps=(),
                action_results=(),
            ),
            completion_criteria=criteria,
        )

    monkeypatch.setattr(service, "inspect_page_with_agent", inspect_with_agent)

    exit_code = cli.main()

    output = capsys.readouterr().out
    report_path = next((tmp_path / "runs").glob("*/report.json"))
    artifact_directory = report_path.parent / "artifacts"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "[AI REQUEST 1] generate test suite" in output
    assert "[AI REQUEST 2] generate completion criteria" in output
    assert "[AI REQUEST 3] plan agent decision 1" in output
    assert report["tests"][0]["kind"] == "browser_goal"
    assert report["tests"][0]["status"] == "passed"
    assert report["budget"]["usage"]["ai_requests"] == 3
    assert report["budget"]["usage"]["browser_runs"] == 2


def test_cli_returns_two_when_suite_generation_fails(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--request",
            "Test unsupported behavior",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    monkeypatch.setattr(
        service,
        "inspect_page",
        lambda *args: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            observation=PageObservation(elements=(), truncated=False),
        ),
    )

    def fail_generation(*args, **kwargs):
        raise PlannerError("Generated suite is unsupported")

    monkeypatch.setattr(service, "generate_test_suite", fail_generation)

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR: Generated suite is unsupported" in captured.err
    assert not list((tmp_path / "runs").glob("*/report.json"))
    run_directory = next((tmp_path / "runs").iterdir())
    assert run_directory.name in captured.err


def test_cli_rejects_request_with_fixed_suite(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--request",
            "Run smoke tests",
            "--suite",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert "--request and --suite cannot be used together" in (
        capsys.readouterr().err
    )


def test_cli_suite_skips_cases_when_browser_run_budget_is_zero(
    monkeypatch,
    tmp_path,
) -> None:
    inspection_calls = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--suite",
            "--max-browser-runs",
            "0",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    def inspect(*args):
        inspection_calls.append(args)
        raise AssertionError("browser should not launch")

    monkeypatch.setattr(service, "inspect_page", inspect)

    exit_code = cli.main()

    report_path = next((tmp_path / "runs").glob("*/report.json"))
    artifact_directory = report_path.parent / "artifacts"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert inspection_calls == []
    assert [test["status"] for test in report["tests"]] == [
        "skipped",
        "skipped",
    ]
    assert report["budget"]["exhausted"] is True
    assert "browser-run budget exhausted" in report["budget"]["reason"]


def test_cli_generated_suite_stops_before_ai_when_budget_is_zero(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    generation_calls = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--request",
            "Run smoke tests",
            "--max-ai-requests",
            "0",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    monkeypatch.setattr(
        service,
        "inspect_page",
        lambda *args: PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example Domain",
            observation=PageObservation(elements=(), truncated=False),
        ),
    )

    def generate_suite(*args, **kwargs):
        generation_calls.append((args, kwargs))
        raise AssertionError("AI should not be called")

    monkeypatch.setattr(service, "generate_test_suite", generate_suite)

    exit_code = cli.main()

    assert exit_code == 2
    assert generation_calls == []
    assert "Suite AI-request budget exhausted" in capsys.readouterr().err


def test_cli_rejects_invalid_suite_budget(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous-qa",
            "https://example.com",
            "--suite",
            "--max-suite-tests",
            "0",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert "max_tests must be an integer of at least 1" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("directory_args, root", [
    ([], "qa-runs"),
    (["--runs-dir", "custom"], "custom"),
    (["--artifacts-dir", "custom"], "custom"),
])
def test_cli_repeated_suites_keep_both_reports(
    monkeypatch, tmp_path, capsys, directory_args, root,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "autonomous-qa", "https://example.com", "--suite", *directory_args,
    ])
    monkeypatch.setattr(service, "inspect_page", lambda *args: PageSnapshot(
        url="https://example.com/", status=200, title="Example",
    ))

    assert cli.main() == 0
    first_report = next((tmp_path / root).glob("*/report.json"))
    original = first_report.read_bytes()
    assert cli.main() == 0

    assert first_report.read_bytes() == original
    reports = list((tmp_path / root).glob("*/report.json"))
    assert len(reports) == 2
    output = capsys.readouterr().out
    for path in reports:
        report = json.loads(path.read_text())
        assert report["run_id"] == path.parent.name
        assert f"Run ID: {path.parent.name}" in output


def test_cli_suite_rejects_shared_report_path(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", [
        "autonomous-qa", "https://example.com", "--suite",
        "--report", "shared.json",
    ])

    with pytest.raises(SystemExit) as caught:
        cli.main()

    assert caught.value.code == 2
    assert "use --runs-dir instead of --report" in capsys.readouterr().err


def test_cli_rejects_runs_directory_outside_suite_mode(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "autonomous-qa", "https://example.com", "--runs-dir", "custom",
    ])

    with pytest.raises(SystemExit) as caught:
        cli.main()

    assert caught.value.code == 2
    assert "only be used with --suite or --request" in capsys.readouterr().err
