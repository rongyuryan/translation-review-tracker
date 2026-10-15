"""SQLite access: one connection per request, schema setup, and CSV import."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import click
from flask import Flask, current_app, g
from flask.cli import with_appcontext

SCHEMA = Path(__file__).with_name("schema.sql")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    get_db().executescript(SCHEMA.read_text(encoding="utf-8"))


def split_record_id(record_id: str) -> tuple[str, str]:
    """'EP01-002' -> ('EP01', '002'); IDs without a dash go under episode 'misc'."""
    episode, sep, line_ref = record_id.rpartition("-")
    return (episode, line_ref) if sep and episode else ("misc", record_id)


def import_qa_report(path: Path) -> tuple[int, int]:
    """Load an issues.csv written by bilingual-ai-localization-qa.

    Returns (segments created, issues created). Re-importing the same report
    adds no duplicate segments; open issues of the same type are not repeated.
    """
    db = get_db()
    segments = issues = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            episode, line_ref = split_record_id(row["record_id"].strip())
            cursor = db.execute(
                "INSERT OR IGNORE INTO segments (episode, line_ref, source_zh, translation) VALUES (?, ?, ?, ?)",
                (episode, line_ref, row["source_text"], row["translation_text"]),
            )
            segments += cursor.rowcount
            segment_id = db.execute(
                "SELECT id FROM segments WHERE episode = ? AND line_ref = ?", (episode, line_ref)
            ).fetchone()["id"]
            exists = db.execute(
                "SELECT 1 FROM issues WHERE segment_id = ? AND issue_type = ? AND status = 'open'",
                (segment_id, row["issue_type"]),
            ).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO issues (segment_id, issue_type, severity, note) VALUES (?, ?, ?, ?)",
                    (segment_id, row["issue_type"], row["severity"], row["message"]),
                )
                issues += 1
    db.commit()
    return segments, issues


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    """Create the tables if they do not exist."""
    init_db()
    click.echo("Initialized the database.")


@click.command("import-report")
@with_appcontext
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def import_report_command(path: Path) -> None:
    """Import an issues.csv produced by the localization QA checker."""
    init_db()
    segments, issues = import_qa_report(path)
    click.echo(f"Imported {issues} issues across {segments} new segments.")


def register(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(import_report_command)
