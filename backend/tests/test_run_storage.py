import pytest

from autonomous_qa.run_storage import RunPaths


def test_existing_run_directory_is_never_reused(tmp_path):
    paths = RunPaths(tmp_path / "runs")
    paths.create()
    paths.report_path.write_text("existing report")

    with pytest.raises(FileExistsError):
        paths.create()

    assert paths.report_path.read_text() == "existing report"
