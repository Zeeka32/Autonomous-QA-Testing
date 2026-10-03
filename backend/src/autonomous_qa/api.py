"""HTTP interface for queued QA runs."""

import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

from .suite.budgets import (
    SuiteBudgetExceeded,
    SuiteBudgetSnapshot,
    SuiteExecutionPolicy,
)
from .planner import PlannerError
from .run_jobs import RunJob, RunJobManager, RunQueueFull
from .run_storage import RunPaths
from .service import QaRunError, QaRunRequest, run_qa
from .suite.suites import (
    MAX_SUITE_REQUEST_LENGTH,
    TEST_ID_PATTERN,
    SuiteRunResult,
)


logger = logging.getLogger(__name__)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_POLICY = SuiteExecutionPolicy()
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RUN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
ARTIFACT_MEDIA_TYPES = {
    ".png": "image/png",
    ".zip": "application/zip",
}


class BudgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    max_tests: int = Field(default=DEFAULT_POLICY.max_tests, ge=1)
    max_browser_goals: int = Field(default=DEFAULT_POLICY.max_browser_goals, ge=0)
    max_ai_requests: int = Field(default=DEFAULT_POLICY.max_ai_requests, ge=0)
    max_browser_runs: int = Field(default=DEFAULT_POLICY.max_browser_runs, ge=0)
    max_duration_seconds: float = Field(
        default=DEFAULT_POLICY.max_duration_seconds, gt=0
    )
    stop_on_provider_quota: bool = DEFAULT_POLICY.stop_on_provider_quota


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    request: NonBlankText | None = Field(
        default=None, max_length=MAX_SUITE_REQUEST_LENGTH
    )
    provider: Literal["gemini", "openai"] = "gemini"
    model: NonBlankText | None = None
    budget_policy: BudgetInput = Field(default_factory=BudgetInput)


class RunAcceptedResponse(BaseModel):
    run_id: str
    status: Literal["queued"] = "queued"
    status_path: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    passed: bool | None = None
    suite_run: SuiteRunResult | None = None
    budget: SuiteBudgetSnapshot | None = None
    report_path: str | None = None
    artifact_directory: str | None = None
    code: str | None = None
    message: str | None = None


class ArtifactLink(BaseModel):
    name: str
    path: str


class ArtifactListResponse(BaseModel):
    run_id: str
    artifacts: list[ArtifactLink]


def _run_directory(runs_directory: Path, run_id: str) -> Path:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    directory = runs_directory / run_id
    if not directory.is_dir() or directory.is_symlink():
        raise HTTPException(status_code=404, detail="Run not found")
    return directory


def _run_file(directory: Path, relative_path: Path) -> Path:
    path = directory / relative_path
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail="File not found")
    if not path.resolve().is_relative_to(directory.resolve()):
        raise HTTPException(status_code=404, detail="File not found")
    return path


def _allowed_artifact_names(directory: Path) -> set[str]:
    names = {"baseline-screenshot.png", "baseline-trace.zip"}
    report = directory / "report.json"
    if not report.is_file() or report.is_symlink():
        return names
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return names
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        return names
    for test in data.get("tests", []):
        test_id = test.get("test_id") if isinstance(test, dict) else None
        if isinstance(test_id, str) and TEST_ID_PATTERN.fullmatch(test_id):
            names.add(f"{test_id}-screenshot.png")
            names.add(f"{test_id}-trace.zip")
    return names


def _status_response(job: RunJob) -> RunStatusResponse:
    if job.result is not None:
        return RunStatusResponse(
            run_id=job.run_id,
            status="completed",
            passed=job.result.passed,
            suite_run=job.result.suite_run,
            budget=job.result.budget,
            report_path=str(job.result.report_path),
            artifact_directory=str(job.result.artifact_directory),
        )
    if isinstance(job.error, QaRunError):
        error = job.error
        if isinstance(error.__cause__, SuiteBudgetExceeded):
            code = "budget_exhausted"
            message = "The run exhausted its budget before execution."
        elif isinstance(error.__cause__, PlannerError):
            code = "planner_error"
            message = "AI planning failed. Check the provider logs."
        else:
            code = "execution_error"
            message = "The run could not finish. Check the server logs."
        return RunStatusResponse(
            run_id=job.run_id,
            status="failed",
            suite_run=error.suite_run,
            budget=error.budget,
            code=code,
            message=message,
        )
    if job.error is not None:
        return RunStatusResponse(
            run_id=job.run_id,
            status="failed",
            code="internal_error",
            message="The run failed unexpectedly. Check the server logs.",
        )
    return RunStatusResponse(run_id=job.run_id, status=job.status)


def create_app(
    runs_directory: Path = Path("qa-runs"),
    *,
    max_workers: int = 2,
    max_pending: int = 8,
) -> FastAPI:
    def execute(request: QaRunRequest, paths: RunPaths):
        try:
            return run_qa(request, run_paths=paths)
        except Exception:
            logger.exception("QA run %s failed", paths.run_id)
            raise

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv(dotenv_path=ENV_FILE, override=False)
        app.state.jobs = RunJobManager(
            runs_directory,
            execute,
            max_workers=max_workers,
            max_pending=max_pending,
        )
        try:
            yield
        finally:
            app.state.jobs.shutdown()

    app = FastAPI(
        title="Autonomous QA API",
        version="0.3.0",
        lifespan=lifespan,
    )

    @app.post(
        "/runs",
        status_code=202,
        response_model=RunAcceptedResponse,
        responses={429: {"description": "Run queue is full"}},
    )
    def create_run(body: RunInput):
        request = QaRunRequest(
            url=str(body.url),
            request=body.request,
            provider=body.provider,
            model=body.model,
            budget_policy=SuiteExecutionPolicy(**body.budget_policy.model_dump()),
            runs_directory=runs_directory,
        )
        try:
            job = app.state.jobs.submit(request)
        except RunQueueFull as error:
            raise HTTPException(status_code=429, detail=str(error)) from error
        return RunAcceptedResponse(
            run_id=job.run_id, status_path=f"/runs/{job.run_id}"
        )

    @app.get("/runs/{run_id}", response_model=RunStatusResponse)
    def get_run(run_id: str):
        job = app.state.jobs.get(run_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return _status_response(job)

    @app.get("/runs/{run_id}/report")
    def get_report(run_id: str):
        directory = _run_directory(runs_directory, run_id)
        report = _run_file(directory, Path("report.json"))
        return FileResponse(report, media_type="application/json")

    @app.get(
        "/runs/{run_id}/artifacts",
        response_model=ArtifactListResponse,
    )
    def list_artifacts(run_id: str):
        directory = _run_directory(runs_directory, run_id)
        names = _allowed_artifact_names(directory)
        artifacts = []
        for name in sorted(names):
            try:
                _run_file(directory, Path("artifacts") / name)
            except HTTPException:
                continue
            artifacts.append(ArtifactLink(
                name=name,
                path=f"/runs/{run_id}/artifacts/{name}",
            ))
        return ArtifactListResponse(run_id=run_id, artifacts=artifacts)

    @app.get("/runs/{run_id}/artifacts/{filename}")
    def get_artifact(run_id: str, filename: str):
        directory = _run_directory(runs_directory, run_id)
        if filename not in _allowed_artifact_names(directory):
            raise HTTPException(status_code=404, detail="File not found")
        artifact = _run_file(directory, Path("artifacts") / filename)
        return FileResponse(
            artifact,
            media_type=ARTIFACT_MEDIA_TYPES[artifact.suffix],
        )

    return app


app = create_app()
