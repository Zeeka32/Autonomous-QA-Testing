import json
from dataclasses import asdict
from pathlib import Path

from .agent import AgentRunResult, AgentStatus
from .models import CheckResult, PageSnapshot
from .plans import CompletionCriteria


class ReportWriteError(RuntimeError):
    """Raised when a QA report cannot be written."""


def write_json_report(
    path: Path,
    requested_url: str,
    snapshot: PageSnapshot,
    results: list[CheckResult],
    screenshot_path: Path,
    trace_path: Path,
    agent_run: AgentRunResult | None = None,
    completion_criteria: CompletionCriteria | None = None,
) -> None:
    actions_passed = (
        all(action.status == "passed" for action in snapshot.action_results)
        if agent_run is None
        else agent_run.status is AgentStatus.COMPLETE
    )
    report = {
        "requested_url": requested_url,
        "final_url": snapshot.url,
        "status": snapshot.status,
        "title": snapshot.title,
        "observation": (
            asdict(snapshot.observation)
            if snapshot.observation is not None
            else None
        ),
        "passed": (
            actions_passed
            and all(result.passed for result in results)
        ),
        "actions": [asdict(action) for action in snapshot.action_results],
        "completion": (
            {
                "source": str(completion_criteria.source),
                "reason": completion_criteria.reason,
                "criteria": [
                    asdict(assertion)
                    for assertion in completion_criteria.assertions
                ],
            }
            if completion_criteria is not None
            else None
        ),
        "agent": (
            {
                "status": str(agent_run.status),
                "reason": agent_run.reason,
                "recoveries_used": agent_run.recoveries_used,
                "verification_retries_used": (
                    agent_run.verification_retries_used
                ),
                "steps": [asdict(step) for step in agent_run.steps],
            }
            if agent_run is not None
            else None
        ),
        "checks": [asdict(result) for result in results],
        "artifacts": {
            "screenshot": str(screenshot_path),
            "trace": str(trace_path),
        },
    }

    try:
        path.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ReportWriteError(
            f'Could not write report to "{path}": {error}'
        ) from error
