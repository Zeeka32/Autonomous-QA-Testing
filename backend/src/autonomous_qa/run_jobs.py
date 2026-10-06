"""Small in-process worker pool and status registry for API runs."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Literal

from .run_storage import RunPaths
from .service import QaRunRequest, QaRunResult
from .suite.suites import TestCaseResult, TestSuite


RunStatus = Literal["queued", "running", "completed", "failed"]
RunWorker = Callable[[QaRunRequest, RunPaths], QaRunResult]


class RunQueueFull(RuntimeError):
    """The process already has its configured number of active jobs."""


@dataclass(frozen=True)
class RunJob:
    run_id: str
    status: RunStatus
    result: QaRunResult | None = None
    error: Exception | None = None
    suite: TestSuite | None = None
    results: tuple[TestCaseResult, ...] = ()


class RunJobManager:
    def __init__(
        self,
        runs_directory: Path,
        worker: RunWorker,
        *,
        max_workers: int = 2,
        max_pending: int = 8,
    ) -> None:
        if max_workers < 1 or max_pending < max_workers:
            raise ValueError("Run queue limits must allow at least one worker")
        self.runs_directory = runs_directory
        self._worker = worker
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="qa-run"
        )
        self._max_pending = max_pending
        self._pending = 0
        self._jobs: dict[str, RunJob] = {}
        self._lock = Lock()
        self._closed = False

    def submit(self, request: QaRunRequest) -> RunJob:
        with self._lock:
            if self._closed:
                raise RuntimeError("Run manager is shut down")
            if self._pending >= self._max_pending:
                raise RunQueueFull("Run queue is full; try again later")
            paths = RunPaths(self.runs_directory)
            while paths.run_id in self._jobs:
                paths = RunPaths(self.runs_directory)
            job = RunJob(run_id=paths.run_id, status="queued")
            self._jobs[job.run_id] = job
            self._pending += 1
            try:
                self._executor.submit(self._execute, request, paths)
            except RuntimeError:
                del self._jobs[job.run_id]
                self._pending -= 1
                raise
            return job

    def get(self, run_id: str) -> RunJob | None:
        with self._lock:
            return self._jobs.get(run_id)

    def set_suite(self, run_id: str, suite: TestSuite) -> None:
        with self._lock:
            job = self._jobs[run_id]
            self._jobs[run_id] = replace(job, suite=suite, results=())

    def add_result(self, run_id: str, result: TestCaseResult) -> None:
        with self._lock:
            job = self._jobs[run_id]
            self._jobs[run_id] = replace(
                job, results=(*job.results, result),
            )

    def _execute(self, request: QaRunRequest, paths: RunPaths) -> None:
        with self._lock:
            self._jobs[paths.run_id] = RunJob(paths.run_id, "running")
        try:
            result = self._worker(request, paths)
        except Exception as error:
            with self._lock:
                self._jobs[paths.run_id] = replace(
                    self._jobs[paths.run_id], status="failed", error=error,
                )
        else:
            with self._lock:
                self._jobs[paths.run_id] = replace(
                    self._jobs[paths.run_id], status="completed", result=result,
                )
        finally:
            with self._lock:
                self._pending -= 1

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True)
