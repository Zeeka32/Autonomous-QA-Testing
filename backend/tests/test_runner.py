import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import sleep

import pytest
from fastapi.testclient import TestClient

from autonomous_qa.agent import AgentStatus
from autonomous_qa.api import create_app
from autonomous_qa.checks import run_checks
from autonomous_qa.models import ActionResult, CheckResult, PageObservation
from autonomous_qa.planner import DecisionStatus, PlannerDecision
from autonomous_qa.plans import (
    ClickAction,
    CompletionCriteria,
    CriteriaSource,
    ElementDisabledAssertion,
    ElementValueEqualsAssertion,
    FillAction,
    PlanAssertion,
    TitleContainsAssertion,
)
from autonomous_qa.reporting import write_json_report
from autonomous_qa.runner import (
    inspect_accessibility,
    inspect_page_with_agent,
)
from autonomous_qa.service import QaRunRequest, run_qa


@pytest.fixture
def local_test_page(tmp_path):
    page_path = tmp_path / "agent-test.html"
    page_path.write_text(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <title>Agent fixture</title>
          </head>
          <body>
            <label for="name">Name</label>
            <input id="name" type="text">
            <button
              id="submit"
              onclick="
                document.title = 'Submitted';
                this.disabled = true;
                document.querySelector('#result-link').hidden = false;
              "
            >Submit</button>
            <a id="result-link" href="/done" hidden>Submission complete</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}/{page_path.name}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_service_runs_baseline_suite_in_real_browser(
    local_test_page, tmp_path,
) -> None:
    request = QaRunRequest(
        url=local_test_page,
        runs_directory=tmp_path / "runs",
    )

    result = run_qa(request)

    assert result.passed
    assert result.budget.browser_runs_used == 1
    assert result.budget.ai_requests_used == 0
    report = json.loads(result.report_path.read_text())
    assert report["passed"] is True
    assert report["run_id"] == result.run_id
    assert len(report["tests"]) == 2
    assert (result.artifact_directory / "baseline-screenshot.png").is_file()
    assert (result.artifact_directory / "baseline-trace.zip").is_file()


def test_api_runs_real_browser_and_returns_report(local_test_page, tmp_path):
    with TestClient(create_app(tmp_path / "api-runs")) as client:
        response = client.post("/runs", json={"url": local_test_page})
        assert response.status_code == 202
        for _ in range(500):
            status = client.get(response.json()["status_path"]).json()
            if status["status"] in {"completed", "failed"}:
                break
            sleep(0.01)
        else:
            pytest.fail("Browser run did not finish within five seconds")
        report = client.get(f"/runs/{status['run_id']}/report")
        listing = client.get(f"/runs/{status['run_id']}/artifacts")

    data = status
    assert data["status"] == "completed"
    assert data["passed"] is True
    directory = tmp_path / "api-runs" / data["run_id"]
    assert (directory / "report.json").is_file()
    assert (directory / "artifacts" / "baseline-screenshot.png").is_file()
    assert (directory / "artifacts" / "baseline-trace.zip").is_file()
    assert report.status_code == 200
    assert report.json()["run_id"] == data["run_id"]
    assert listing.status_code == 200
    assert [item["name"] for item in listing.json()["artifacts"]] == [
        "baseline-screenshot.png",
        "baseline-trace.zip",
    ]


class ScriptedPlanner:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                str,
                str,
                PageObservation,
                ActionResult | None,
                tuple[CheckResult, ...],
                tuple[PlanAssertion, ...],
            ]
        ] = []

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
        selectors = {element.selector: element for element in observation.elements}
        assert completion_criteria == (
            TitleContainsAssertion(value="Submitted"),
            ElementDisabledAssertion(selector="#submit"),
            ElementValueEqualsAssertion(selector="#name", value="Ada"),
        )

        if len(self.calls) == 1:
            assert previous_action_result is None
            assert "#name" in selectors
            assert "#submit" in selectors
            return PlannerDecision(
                status=DecisionStatus.ACTION,
                action=FillAction(selector="#name", value="Ada"),
                reason="Enter a name before submitting",
            )

        if len(self.calls) == 2:
            assert previous_action_result is not None
            assert previous_action_result.status == "passed"
            assert selectors["#submit"].disabled is False
            return PlannerDecision(
                status=DecisionStatus.ACTION,
                action=ClickAction(selector="#submit"),
                reason="Submit the completed form",
            )

        assert previous_action_result is not None
        assert previous_action_result.status == "passed"
        assert selectors["#submit"].disabled is True
        assert "#result-link" in selectors
        return PlannerDecision(
            status=DecisionStatus.COMPLETE,
            action=None,
            reason="The submission result is visible",
        )


def test_agent_runner_completes_a_real_browser_workflow(
    local_test_page,
    tmp_path,
) -> None:
    screenshot_path = tmp_path / "agent-page.png"
    trace_path = tmp_path / "agent-trace.zip"
    report_path = tmp_path / "agent-report.json"
    planner = ScriptedPlanner()
    reported_steps = []

    criteria_calls = []

    def generate_criteria(goal, current_url, page_title, observation):
        criteria_calls.append((goal, current_url, page_title, observation))
        return CompletionCriteria(
            assertions=(
                TitleContainsAssertion(value="Submitted"),
                ElementDisabledAssertion(selector="#submit"),
                ElementValueEqualsAssertion(selector="#name", value="Ada"),
            ),
            source=CriteriaSource.AI_GENERATED,
            reason="The completed workflow changes the page title",
        )

    inspection = inspect_page_with_agent(
        starting_url=local_test_page,
        goal="Enter a name and submit the form",
        planner=planner,
        assertions=(),
        screenshot_path=screenshot_path,
        trace_path=trace_path,
        criteria_generator=generate_criteria,
        agent_step_reporter=reported_steps.append,
    )

    results = run_checks(inspection.snapshot)
    write_json_report(
        report_path,
        local_test_page,
        inspection.snapshot,
        results,
        screenshot_path,
        trace_path,
        inspection.agent_run,
        inspection.completion_criteria,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert inspection.agent_run.status is AgentStatus.COMPLETE
    assert inspection.snapshot.status == 200
    assert inspection.snapshot.title == "Submitted"
    assert len(planner.calls) == 3
    assert tuple(reported_steps) == inspection.agent_run.steps
    assert len(criteria_calls) == 1
    assert inspection.completion_criteria is not None
    assert inspection.completion_criteria.source is CriteriaSource.AI_GENERATED
    assert [action.kind for action in inspection.snapshot.action_results] == [
        "navigate",
        "fill",
        "click",
    ]
    assert [step.step_number for step in inspection.agent_run.steps] == [2, 3, 4]
    assert all(result.passed for result in results)
    assert screenshot_path.stat().st_size > 0
    assert trace_path.stat().st_size > 0
    assert report["passed"] is True
    assert report["completion"]["source"] == "ai_generated"
    assert report["completion"]["criteria"] == [
        {"value": "Submitted", "kind": "title_contains"},
        {"selector": "#submit", "kind": "element_disabled"},
        {
            "selector": "#name",
            "value": "Ada",
            "kind": "element_value_equals",
        },
    ]
    assert [step["decision_status"] for step in report["agent"]["steps"]] == [
        "action",
        "action",
        "complete",
    ]


def test_agent_runner_rejects_generated_criteria_already_true_initially(
    local_test_page,
    tmp_path,
) -> None:
    def planner(*args):
        raise AssertionError("planner must not run with trivial criteria")

    inspection = inspect_page_with_agent(
        starting_url=local_test_page,
        goal="Complete the workflow",
        planner=planner,
        assertions=(),
        screenshot_path=tmp_path / "initial-page.png",
        trace_path=tmp_path / "initial-trace.zip",
        criteria_generator=lambda *args: CompletionCriteria(
            assertions=(
                TitleContainsAssertion(value="Agent fixture"),
            ),
            source=CriteriaSource.AI_GENERATED,
            reason="The starting title describes the page",
        ),
    )

    assert inspection.agent_run.status is AgentStatus.UNVERIFIED
    assert inspection.completion_criteria is not None
    assert inspection.completion_criteria.source is CriteriaSource.NONE
    assert "already satisfied" in inspection.completion_criteria.reason


def test_accessibility_runner_audits_a_real_page(
    local_test_page,
    tmp_path,
) -> None:
    screenshot_path = tmp_path / "accessibility.png"
    trace_path = tmp_path / "accessibility-trace.zip"

    inspection = inspect_accessibility(
        local_test_page,
        screenshot_path,
        trace_path,
    )

    assert inspection.snapshot.status == 200
    assert [check.name for check in inspection.checks] == [
        "Document language",
        "Document title",
        "Image alternative text",
        "Form control names",
        "Interactive element names",
        "Frame titles",
    ]
    assert all(check.passed for check in inspection.checks)
    assert screenshot_path.stat().st_size > 0
    assert trace_path.stat().st_size > 0
