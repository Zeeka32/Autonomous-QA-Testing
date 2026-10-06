import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import UUID

import pytest

from autonomous_qa import service
from autonomous_qa.suite.budgets import SuiteExecutionPolicy
from autonomous_qa.models import ActionResult, PageObservation, PageSnapshot
from autonomous_qa.planner import PlannerError
from autonomous_qa.reporting import ReportWriteError
from autonomous_qa.service import QaRunError, QaRunRequest, run_qa
from autonomous_qa.suite.suites import (
    TestCase as SuiteCase,
    TestKind as CaseKind,
    TestSuite as SuiteDefinition,
)


@pytest.fixture
def request_data(tmp_path):
    return QaRunRequest(
        url="https://example.com",
        runs_directory=tmp_path / "runs",
    )


@pytest.fixture
def inspections(monkeypatch):
    calls = []

    def inspect(*args):
        calls.append(args)
        args[1].write_bytes(b"screenshot")
        args[2].write_bytes(b"trace")
        return PageSnapshot(
            url="https://example.com/",
            status=200,
            title="Example",
            observation=PageObservation(elements=(), truncated=False),
        )

    monkeypatch.setattr(service, "inspect_page", inspect)
    return calls


def test_direct_runs_are_silent_and_have_independent_budgets(
    request_data, inspections, capsys,
) -> None:
    first = run_qa(request_data)
    saved_report = first.report_path.read_bytes()
    second = run_qa(request_data)

    assert first.passed and second.passed
    assert len(inspections) == 2
    assert first.budget.browser_runs_used == 1
    assert second.budget.browser_runs_used == 1
    assert first.budget.ai_requests_used == 0
    assert len(first.suite_run.results) == 2
    report = json.loads(first.report_path.read_text())
    assert report["budget"]["usage"]["browser_runs"] == 1
    assert first.run_id != second.run_id
    assert UUID(first.run_id).version == 4
    assert first.report_path.read_bytes() == saved_report
    assert first.report_path != second.report_path
    assert first.artifact_directory != second.artifact_directory
    assert report["run_id"] == first.run_id
    assert first.run_directory == request_data.runs_directory / first.run_id
    assert first.report_path == first.run_directory / "report.json"
    assert first.artifact_directory == first.run_directory / "artifacts"
    for result in (first, second):
        assert (result.artifact_directory / "baseline-screenshot.png").exists()
        assert (result.artifact_directory / "baseline-trace.zip").exists()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_generated_suite_reuses_observation_and_emits_optional_progress(
    request_data, inspections, monkeypatch, capsys,
) -> None:
    request_data = replace(request_data, request="Test the page title")
    messages = []

    def generate(request, url, title, observation, model, **kwargs):
        assert request == request_data.request
        assert title == "Example"
        assert isinstance(observation, PageObservation)
        assert model == request_data.resolved_model
        assert kwargs["provider"] == request_data.provider
        return SuiteDefinition(
            url=url,
            request=request,
            tests=(SuiteCase("title", "Has a title", CaseKind.TITLE_PRESENT),),
        )

    monkeypatch.setattr(service, "generate_test_suite", generate)
    result = run_qa(request_data, on_message=messages.append)

    assert result.passed
    assert len(inspections) == 1
    assert result.budget.ai_requests_used == 1
    assert result.budget.browser_runs_used == 1
    assert "[AI REQUEST 1] generate test suite" in messages
    assert messages[0] == f"Run ID: {result.run_id}"
    assert inspections[0][1].parent == result.artifact_directory
    assert capsys.readouterr().out == ""


def test_failed_initial_navigation_never_reaches_suite_planner(
    request_data, monkeypatch,
) -> None:
    def inspect(*args):
        return PageSnapshot(
            url=request_data.url,
            status=None,
            title="The Internet",
            observation=PageObservation(elements=(), truncated=False),
            action_results=(ActionResult(
                step_number=1,
                kind="navigate",
                status="failed",
                duration_ms=40_000,
                url_before="about:blank",
                url_after=request_data.url,
                message="Timeout 40000ms exceeded",
            ),),
        )

    def unexpected_planning(*args, **kwargs):
        pytest.fail("Suite planner must not receive a failed navigation")

    monkeypatch.setattr(service, "inspect_page", inspect)
    monkeypatch.setattr(service, "generate_test_suite", unexpected_planning)

    with pytest.raises(
        QaRunError, match="Could not navigate.*Timeout 40000ms exceeded",
    ) as caught:
        run_qa(replace(request_data, request="Test the checkboxes"))

    assert caught.value.budget.browser_runs_used == 1
    assert caught.value.budget.ai_requests_used == 0


def test_exhausted_execution_budget_returns_skipped_results(
    request_data, inspections,
) -> None:
    result = run_qa(replace(
        request_data,
        budget_policy=SuiteExecutionPolicy(max_browser_runs=0),
    ))

    assert not result.passed
    assert inspections == []
    assert [case.status for case in result.suite_run.results] == [
        "skipped", "skipped",
    ]
    assert result.budget.exhausted
    assert result.report_path.exists()


def test_planning_error_retains_usage_without_creating_a_report(
    request_data, inspections, monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise PlannerError("Unsupported request")

    monkeypatch.setattr(service, "generate_test_suite", fail)
    with pytest.raises(QaRunError, match="Unsupported request") as caught:
        run_qa(replace(request_data, request="Test the site"))

    assert caught.value.budget.ai_requests_used == 1
    assert caught.value.budget.browser_runs_used == 1
    assert caught.value.suite_run is None
    assert not caught.value.report_path.exists()
    assert caught.value.run_directory.is_dir()
    assert caught.value.artifact_directory.is_dir()
    assert UUID(caught.value.run_id).version == 4


def test_report_failure_preserves_completed_test_results(
    request_data, inspections, monkeypatch,
) -> None:
    def fail_report(*args, **kwargs):
        raise ReportWriteError("Could not write report")

    monkeypatch.setattr(service, "write_suite_json_report", fail_report)
    with pytest.raises(QaRunError, match="Could not write report") as caught:
        run_qa(request_data)

    assert caught.value.suite_run.passed
    assert caught.value.budget.browser_runs_used == 1
    assert caught.value.artifact_directory.is_dir()


def test_unexpected_programming_errors_propagate(
    request_data, monkeypatch,
) -> None:
    def broken_inspector(*args):
        raise TypeError("Programming bug")

    monkeypatch.setattr(service, "inspect_page", broken_inspector)
    with pytest.raises(TypeError, match="Programming bug"):
        run_qa(request_data)


@pytest.mark.parametrize("changes", [
    {"url": "file:///tmp/page.html"},
    {"request": "   "},
    {"request": "x" * 2_001},
    {"provider": "unsupported"},
    {"model": ""},
    {"budget_policy": None},
    {"runs_directory": "runs"},
])
def test_request_validates_inputs_before_execution(request_data, changes):
    with pytest.raises(ValueError):
        replace(request_data, **changes)


def test_cohere_request_uses_default_model(request_data):
    request = replace(request_data, provider="cohere")

    assert request.resolved_model == "command-a-03-2025"


def test_concurrent_runs_write_to_separate_directories(
    request_data, inspections,
) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(run_qa, [request_data, request_data]))

    assert first.run_id != second.run_id
    for result in (first, second):
        report = json.loads(result.report_path.read_text())
        assert report["run_id"] == result.run_id
        assert report["artifacts"]["directory"] == str(result.artifact_directory)
        assert (result.artifact_directory / "baseline-trace.zip").exists()


def test_directory_failure_has_run_identity_and_starts_no_browser(
    request_data, inspections,
) -> None:
    request_data.runs_directory.write_text("existing file")
    with pytest.raises(QaRunError) as caught:
        run_qa(request_data)

    assert inspections == []
    assert caught.value.budget.browser_runs_used == 0
    assert caught.value.run_directory == (
        request_data.runs_directory / caught.value.run_id
    )
    assert request_data.runs_directory.read_text() == "existing file"
