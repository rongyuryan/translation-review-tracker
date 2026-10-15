-- Translation review tracker schema (SQLite)

CREATE TABLE IF NOT EXISTS segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    episode      TEXT    NOT NULL,
    line_ref     TEXT    NOT NULL,
    source_zh    TEXT    NOT NULL,
    translation  TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (episode, line_ref)
);

CREATE TABLE IF NOT EXISTS issues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id   INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    issue_type   TEXT    NOT NULL,
    severity     TEXT    NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    status       TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    note         TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_issues_segment ON issues(segment_id);
CREATE INDEX IF NOT EXISTS idx_issues_status_severity ON issues(status, severity);
