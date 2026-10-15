"""REST endpoints for segments, issues, and summary statistics."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, abort, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .db import get_db

bp = Blueprint("api", __name__, static_folder="static")

SEVERITIES = ("low", "medium", "high")
STATUSES = ("open", "resolved")


# ------------------------------------------------------------------ helpers


def body(*required: str) -> dict[str, Any]:
    """Parse the JSON body and reject requests that miss required fields."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="request body must be a JSON object")
    missing = [name for name in required if not str(data.get(name, "")).strip()]
    if missing:
        abort(400, description=f"missing required field(s): {', '.join(missing)}")
    return data


def choice(value: Any, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        abort(400, description=f"{field} must be one of: {', '.join(allowed)}")
    return value


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def fetch_issue(issue_id: int) -> dict[str, Any]:
    row = get_db().execute(
        """SELECT i.*, s.episode, s.line_ref, s.source_zh, s.translation
           FROM issues i JOIN segments s ON s.id = i.segment_id
           WHERE i.id = ?""",
        (issue_id,),
    ).fetchone()
    if row is None:
        abort(404, description=f"issue {issue_id} not found")
    return dict(row)


@bp.errorhandler(HTTPException)
def json_error(exc: HTTPException):
    return jsonify(error=exc.name, message=exc.description), exc.code


# ------------------------------------------------------------------- web UI


@bp.get("/")
def index():
    return send_from_directory(bp.static_folder, "index.html")


@bp.get("/api/health")
def health():
    return {"status": "ok"}


# ----------------------------------------------------------------- segments


@bp.get("/api/segments")
def list_segments():
    sql = """SELECT s.*, COALESCE(SUM(i.status = 'open'), 0) AS open_issues
             FROM segments s LEFT JOIN issues i ON i.segment_id = s.id"""
    params: list[Any] = []
    if episode := request.args.get("episode"):
        sql += " WHERE s.episode = ?"
        params.append(episode)
    sql += " GROUP BY s.id ORDER BY s.episode, s.line_ref"
    return jsonify(rows(get_db().execute(sql, params)))


@bp.post("/api/segments")
def create_segment():
    data = body("episode", "line_ref", "source_zh")
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO segments (episode, line_ref, source_zh, translation) VALUES (?, ?, ?, ?)",
            (data["episode"].strip(), str(data["line_ref"]).strip(), data["source_zh"].strip(),
             str(data.get("translation", "")).strip()),
        )
    except sqlite3.IntegrityError:
        abort(409, description=f"segment {data['episode']}-{data['line_ref']} already exists")
    db.commit()
    return get_segment(cursor.lastrowid), 201


@bp.get("/api/segments/<int:segment_id>")
def get_segment(segment_id: int):
    db = get_db()
    segment = db.execute("SELECT * FROM segments WHERE id = ?", (segment_id,)).fetchone()
    if segment is None:
        abort(404, description=f"segment {segment_id} not found")
    issues = rows(db.execute("SELECT * FROM issues WHERE segment_id = ? ORDER BY id", (segment_id,)))
    return jsonify({**dict(segment), "issues": issues})


@bp.patch("/api/segments/<int:segment_id>")
def update_segment(segment_id: int):
    data = body("translation")
    db = get_db()
    cursor = db.execute("UPDATE segments SET translation = ? WHERE id = ?", (data["translation"].strip(), segment_id))
    if cursor.rowcount == 0:
        abort(404, description=f"segment {segment_id} not found")
    db.commit()
    return get_segment(segment_id)


# ------------------------------------------------------------------- issues


@bp.post("/api/segments/<int:segment_id>/issues")
def create_issue(segment_id: int):
    data = body("issue_type", "severity")
    severity = choice(data["severity"], SEVERITIES, "severity")
    db = get_db()
    if db.execute("SELECT 1 FROM segments WHERE id = ?", (segment_id,)).fetchone() is None:
        abort(404, description=f"segment {segment_id} not found")
    cursor = db.execute(
        "INSERT INTO issues (segment_id, issue_type, severity, note) VALUES (?, ?, ?, ?)",
        (segment_id, data["issue_type"].strip(), severity, str(data.get("note", "")).strip()),
    )
    db.commit()
    return jsonify(fetch_issue(cursor.lastrowid)), 201


@bp.get("/api/issues")
def list_issues():
    """Filter by ?status=open|resolved, ?severity=low|medium|high, ?episode=EP01."""
    sql = """SELECT i.*, s.episode, s.line_ref, s.source_zh, s.translation
             FROM issues i JOIN segments s ON s.id = i.segment_id WHERE 1 = 1"""
    params: list[Any] = []
    if status := request.args.get("status"):
        sql += " AND i.status = ?"
        params.append(choice(status, STATUSES, "status"))
    if severity := request.args.get("severity"):
        sql += " AND i.severity = ?"
        params.append(choice(severity, SEVERITIES, "severity"))
    if episode := request.args.get("episode"):
        sql += " AND s.episode = ?"
        params.append(episode)
    sql += """ ORDER BY CASE i.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
               s.episode, s.line_ref, i.id"""
    return jsonify(rows(get_db().execute(sql, params)))


@bp.patch("/api/issues/<int:issue_id>")
def update_issue(issue_id: int):
    data = body()
    fetch_issue(issue_id)  # 404 if missing
    db = get_db()
    if "status" in data:
        status = choice(data["status"], STATUSES, "status")
        db.execute(
            """UPDATE issues SET status = ?,
               resolved_at = CASE WHEN ? = 'resolved' THEN datetime('now') ELSE NULL END
               WHERE id = ?""",
            (status, status, issue_id),
        )
    if "severity" in data:
        db.execute("UPDATE issues SET severity = ? WHERE id = ?", (choice(data["severity"], SEVERITIES, "severity"), issue_id))
    if "note" in data:
        db.execute("UPDATE issues SET note = ? WHERE id = ?", (str(data["note"]).strip(), issue_id))
    db.commit()
    return jsonify(fetch_issue(issue_id))


@bp.delete("/api/issues/<int:issue_id>")
def delete_issue(issue_id: int):
    db = get_db()
    if db.execute("DELETE FROM issues WHERE id = ?", (issue_id,)).rowcount == 0:
        abort(404, description=f"issue {issue_id} not found")
    db.commit()
    return "", 204


# -------------------------------------------------------------------- stats


@bp.get("/api/stats")
def stats():
    db = get_db()
    totals = db.execute(
        """SELECT COUNT(*) AS total,
                  SUM(status = 'open') AS open,
                  SUM(status = 'resolved') AS resolved
           FROM issues"""
    ).fetchone()
    open_by_severity = {r["severity"]: r["n"] for r in db.execute(
        "SELECT severity, COUNT(*) AS n FROM issues WHERE status = 'open' GROUP BY severity")}
    by_type = rows(db.execute(
        """SELECT issue_type, COUNT(*) AS total, SUM(status = 'open') AS open
           FROM issues GROUP BY issue_type ORDER BY total DESC, issue_type"""))
    by_episode = rows(db.execute(
        """SELECT s.episode, COUNT(i.id) AS open_issues
           FROM segments s JOIN issues i ON i.segment_id = s.id AND i.status = 'open'
           GROUP BY s.episode ORDER BY open_issues DESC, s.episode"""))
    hours = db.execute(
        """SELECT ROUND(AVG((julianday(resolved_at) - julianday(created_at)) * 24), 2) AS h
           FROM issues WHERE status = 'resolved'"""
    ).fetchone()["h"]
    return jsonify({
        "total": totals["total"],
        "open": totals["open"] or 0,
        "resolved": totals["resolved"] or 0,
        "open_by_severity": {s: open_by_severity.get(s, 0) for s in SEVERITIES},
        "by_type": by_type,
        "open_by_episode": by_episode,
        "avg_hours_to_resolve": hours,
    })
