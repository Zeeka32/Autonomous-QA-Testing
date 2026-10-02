"""Output paths for one suite run, allocated without reusing a directory."""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class RunPaths:
    runs_directory: Path
    run_id: str = field(init=False, default_factory=lambda: uuid4().hex)

    @property
    def run_directory(self) -> Path:
        return self.runs_directory / self.run_id

    @property
    def report_path(self) -> Path:
        return self.run_directory / "report.json"

    @property
    def artifact_directory(self) -> Path:
        return self.run_directory / "artifacts"

    def create(self) -> None:
        self.runs_directory.mkdir(parents=True, exist_ok=True)
        # mkdir is atomic: even an ID collision must never reuse old outputs.
        self.run_directory.mkdir(exist_ok=False)
        self.artifact_directory.mkdir()
