import json
from threading import Event
from time import sleep

import pytest
from fastapi.testclient import TestClient

from autonomous_qa import api, service
from autonomous_qa.models import PageObservation, PageSnapshot
from autonomous_qa.planner import PlannerError
from autonomous_qa.reporting import ReportWriteError
from autonomous_qa.suites import (
    TestCase as SuiteCase,
    TestKind as CaseKind,
    TestSuite as SuiteDefinition,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "load_dotenv", lambda **kwargs: None)
    with TestClient(api.create_app(tmp_path / "runs")) as client:
        yield client


@pytest.fixture
def inspect(monkeypatch):
    calls = []

    def fake_inspector(*args):
        calls.append(args)
        return PageSnapshot(
            url="https://example.com/", status=200, title="Example",
            observation=PageObservation(elements=(), truncated=False),
        )

    monkeypatch.setattr(service, "inspect_page", fake_inspector)
    return calls


def wait_for_run(client, accepted):
    path = accepted["status_path"]
    for _ in range(200):
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()
        if data["status"] in {"completed", "failed"}:
            return data
        sleep(0.01)
    pytest.fail("Run did not finish within two seconds")


def test_baseline_api_returns_id_then_serializes_report(client, inspect, tmp_path):
    response = client.post("/runs", json={"url": "https://example.com"})

    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "queued"
    assert accepted["status_path"] == f"/runs/{accepted['run_id']}"
    data = wait_for_run(client, accepted)
    assert data["status"] == "completed"
    assert data["passed"] is True
    assert len(inspect) == 1
    assert len(data["suite_run"]["results"]) == 2
    assert data["budget"]["ai_requests_used"] == 0
    path = tmp_path / "runs" / data["run_id"] / "report.json"
    assert data["report_path"] == str(path)
    assert json.loads(path.read_text())["run_id"] == data["run_id"]


def test_generated_request_passes_provider_model_and_budget(
    client, inspect, monkeypatch,
):
    def generate(request, url, title, observation, model, **kwargs):
        assert request == "Test title"
        assert model == "test-model"
        assert kwargs["provider"] == "openai"
        return SuiteDefinition(url=url, request=request, tests=(
            SuiteCase("title", "Title", CaseKind.TITLE_PRESENT),
        ))

    monkeypatch.setattr(service, "generate_test_suite", generate)
    response = client.post("/runs", json={
        "url": "https://example.com",
        "request": "Test title",
        "provider": "openai",
        "model": "test-model",
        "budget_policy": {"max_ai_requests": 1},
    })

    assert response.status_code == 202
    data = wait_for_run(client, response.json())
    assert data["passed"] is True
    assert data["budget"]["ai_requests_used"] == 1
    assert data["budget"]["policy"]["max_ai_requests"] == 1
    assert len(inspect) == 1


@pytest.mark.parametrize("body", [
    {},
    {"url": "file:///tmp/page"},
    {"url": "example.com"},
    {"url": "https://example.com", "request": "  "},
    {"url": "https://example.com", "request": "x" * 2001},
    {"url": "https://example.com", "provider": "unknown"},
    {"url": "https://example.com", "model": "  "},
    {"url": "https://example.com", "runs_directory": "/tmp/override"},
    {"url": "https://example.com", "budget_policy": {"max_tests": 0}},
    {"url": "https://example.com", "budget_policy": {"max_ai_requests": -1}},
    {"url": "https://example.com", "budget_policy": {"max_tests": True}},
    {"url": "https://example.com", "budget_policy": {"max_tests": "2"}},
    {"url": "https://example.com", "budget_policy": {"max_duration_seconds": 0}},
    {"url": "https://example.com", "budget_policy": {"unknown": 1}},
])
def test_invalid_input_never_starts_service(client, monkeypatch, body):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid input reached service")

    monkeypatch.setattr(api, "run_qa", unexpected)
    assert client.post("/runs", json=body).status_code == 422


def test_skipped_cases_are_completed_results(client, inspect):
    response = client.post("/runs", json={
        "url": "https://example.com",
        "budget_policy": {"max_browser_runs": 0},
    })
    assert response.status_code == 202
    data = wait_for_run(client, response.json())
    assert data["status"] == "completed"
    assert data["passed"] is False
    assert data["suite_run"]["results"][0]["status"] == "skipped"
    assert inspect == []


def test_budget_exhaustion_before_planning_marks_run_failed(client, inspect):
    response = client.post("/runs", json={
        "url": "https://example.com", "request": "Test title",
        "budget_policy": {"max_ai_requests": 0},
    })
    assert response.status_code == 202
    data = wait_for_run(client, response.json())
    assert data["status"] == "failed"
    assert data["code"] == "budget_exhausted"
    assert data["run_id"] == response.json()["run_id"]


def test_planner_failure_is_structured_without_raw_provider_message(
    client, inspect, monkeypatch,
):
    def fail(*args, **kwargs):
        raise PlannerError("private provider details")

    monkeypatch.setattr(service, "generate_test_suite", fail)
    response = client.post("/runs", json={
        "url": "https://example.com", "request": "Test title",
    })
    assert response.status_code == 202
    data = wait_for_run(client, response.json())
    assert data["status"] == "failed"
    assert data["code"] == "planner_error"
    assert "private provider details" not in str(data)
    assert data["budget"]["ai_requests_used"] == 1


def test_report_failure_preserves_completed_results(client, inspect, monkeypatch):
    def fail(*args, **kwargs):
        raise ReportWriteError("Disk failed")

    monkeypatch.setattr(service, "write_suite_json_report", fail)
    response = client.post("/runs", json={"url": "https://example.com"})
    data = wait_for_run(client, response.json())
    assert data["status"] == "failed"
    assert data["code"] == "execution_error"
    assert len(data["suite_run"]["results"]) == 2


def test_unknown_run_returns_404(client):
    response = client.get("/runs/" + "0" * 32)
    assert response.status_code == 404


def test_queued_running_and_full_queue_are_visible(tmp_path, monkeypatch):
    started = Event()
    release = Event()
    monkeypatch.setattr(api, "load_dotenv", lambda **kwargs: None)

    def hold_run(request, *, run_paths):
        started.set()
        assert release.wait(5)
        raise RuntimeError("test failure")

    monkeypatch.setattr(api, "run_qa", hold_run)
    with TestClient(
        api.create_app(tmp_path / "runs", max_workers=1, max_pending=2)
    ) as client:
        try:
            first = client.post("/runs", json={"url": "https://example.com"})
            assert first.status_code == 202
            assert started.wait(2)
            first_status = client.get(first.json()["status_path"]).json()
            assert first_status["status"] == "running"
            second = client.post("/runs", json={"url": "https://example.com"})
            assert second.status_code == 202
            second_status = client.get(second.json()["status_path"]).json()
            assert second_status["status"] == "queued"
            full = client.post("/runs", json={"url": "https://example.com"})
            assert full.status_code == 429
        finally:
            release.set()
        first_final = wait_for_run(client, first.json())
        second_final = wait_for_run(client, second.json())
        assert first_final["status"] == second_final["status"] == "failed"
        assert first_final["code"] == "internal_error"
        assert first_final["run_id"] != second_final["run_id"]
        third = client.post("/runs", json={"url": "https://example.com"})
        assert third.status_code == 202
        wait_for_run(client, third.json())


def test_openapi_documents_post_and_polling(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    routes = response.json()["paths"]
    assert set(routes["/runs"]["post"]["responses"]) == {"202", "422", "429"}
    assert "200" in routes["/runs/{run_id}"]["get"]["responses"]
    assert "200" in routes["/runs/{run_id}/report"]["get"]["responses"]
    assert "200" in routes["/runs/{run_id}/artifacts"]["get"]["responses"]
    assert client.get("/docs").status_code == 200


def test_report_and_artifacts_can_be_fetched_after_restart(
    tmp_path, monkeypatch, inspect,
):
    monkeypatch.setattr(api, "load_dotenv", lambda **kwargs: None)
    runs_directory = tmp_path / "runs"
    with TestClient(api.create_app(runs_directory)) as client:
        accepted = client.post("/runs", json={"url": "https://example.com"})
        result = wait_for_run(client, accepted.json())

    run_id = result["run_id"]
    directory = runs_directory / run_id
    (directory / "artifacts" / "baseline-screenshot.png").write_bytes(b"png")
    (directory / "artifacts" / "baseline-trace.zip").write_bytes(b"zip")
    (directory / "artifacts" / "page-load-screenshot.png").write_bytes(b"case")
    (directory / "artifacts" / "unknown-screenshot.png").write_bytes(b"secret")

    with TestClient(api.create_app(runs_directory)) as client:
        assert client.get(f"/runs/{run_id}").status_code == 404
        report = client.get(f"/runs/{run_id}/report")
        assert report.status_code == 200
        assert report.headers["content-type"] == "application/json"
        assert report.json()["run_id"] == run_id

        listing = client.get(f"/runs/{run_id}/artifacts")
        assert listing.status_code == 200
        assert [item["name"] for item in listing.json()["artifacts"]] == [
            "baseline-screenshot.png",
            "baseline-trace.zip",
            "page-load-screenshot.png",
        ]
        for item in listing.json()["artifacts"]:
            response = client.get(item["path"])
            assert response.status_code == 200
            assert response.content in {b"png", b"zip", b"case"}
        assert client.get(
            f"/runs/{run_id}/artifacts/unknown-screenshot.png"
        ).status_code == 404


def test_artifact_endpoints_reject_unknown_runs_and_unlisted_files(
    client, inspect, tmp_path,
):
    run_id = "0" * 32
    assert client.get(f"/runs/{run_id}/report").status_code == 404
    assert client.get(f"/runs/{run_id}/artifacts").status_code == 404
    assert client.get(
        f"/runs/{run_id}/artifacts/baseline-trace.zip"
    ).status_code == 404

    accepted = client.post("/runs", json={"url": "https://example.com"})
    result = wait_for_run(client, accepted.json())
    run_id = result["run_id"]
    artifacts = tmp_path / "runs" / run_id / "artifacts"
    (artifacts / "private.txt").write_text("private")
    assert client.get(f"/runs/{run_id}/artifacts/private.txt").status_code == 404
    assert client.get(
        f"/runs/{run_id}/artifacts/page-title-trace.zip"
    ).status_code == 404
    assert client.get("/runs/not-a-run-id/report").status_code == 404


def test_artifact_endpoint_rejects_symlinks(client, inspect, tmp_path):
    accepted = client.post("/runs", json={"url": "https://example.com"})
    result = wait_for_run(client, accepted.json())
    run_id = result["run_id"]
    private = tmp_path / "private.png"
    private.write_bytes(b"private")
    artifact = tmp_path / "runs" / run_id / "artifacts" / "baseline-screenshot.png"
    artifact.symlink_to(private)

    assert client.get(
        f"/runs/{run_id}/artifacts/baseline-screenshot.png"
    ).status_code == 404
    assert client.get(f"/runs/{run_id}/artifacts").json()["artifacts"] == []


def test_failed_planning_run_can_serve_existing_baseline_artifact(
    client, inspect, monkeypatch, tmp_path,
):
    def fail(*args, **kwargs):
        raise PlannerError("Unavailable")

    monkeypatch.setattr(service, "generate_test_suite", fail)
    accepted = client.post("/runs", json={
        "url": "https://example.com", "request": "Test navigation",
    })
    result = wait_for_run(client, accepted.json())
    assert result["status"] == "failed"
    run_id = result["run_id"]
    artifact = tmp_path / "runs" / run_id / "artifacts" / "baseline-trace.zip"
    artifact.write_bytes(b"partial-trace")

    assert client.get(f"/runs/{run_id}/report").status_code == 404
    listing = client.get(f"/runs/{run_id}/artifacts").json()
    assert [item["name"] for item in listing["artifacts"]] == [
        "baseline-trace.zip",
    ]
    response = client.get(listing["artifacts"][0]["path"])
    assert response.status_code == 200
    assert response.content == b"partial-trace"
