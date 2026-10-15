"""Importing an issues.csv produced by the bilingual-ai-localization-qa checker."""

from pathlib import Path

from tracker.db import import_qa_report, split_record_id

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "qa_issues.csv"


def test_split_record_id():
    assert split_record_id("EP01-002") == ("EP01", "002")
    assert split_record_id("S1-EP03-010") == ("S1-EP03", "010")
    assert split_record_id("17") == ("misc", "17")


def test_import_creates_segments_and_issues(app, client):
    with app.app_context():
        segments, issues = import_qa_report(SAMPLE)
    assert (segments, issues) == (7, 7)
    stats = client.get("/api/stats").get_json()
    assert stats["open_by_severity"] == {"low": 1, "medium": 4, "high": 2}


def test_reimport_does_not_duplicate(app):
    with app.app_context():
        import_qa_report(SAMPLE)
        assert import_qa_report(SAMPLE) == (0, 0)


def test_cli_import_command(app):
    result = app.test_cli_runner().invoke(args=["import-report", str(SAMPLE)])
    assert result.exit_code == 0
    assert "Imported 7 issues across 7 new segments" in result.output
