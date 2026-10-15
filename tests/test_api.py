"""API tests: happy paths, validation errors, filters, and SQL aggregates."""


def add_issue(client, segment_id, severity="medium", issue_type="number_mismatch", note=""):
    response = client.post(f"/api/segments/{segment_id}/issues",
                           json={"issue_type": issue_type, "severity": severity, "note": note})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Translation Review Tracker" in response.data


# --------------------------------------------------------------- segments


def test_create_and_fetch_segment(client, segment):
    fetched = client.get(f"/api/segments/{segment['id']}").get_json()
    assert fetched["episode"] == "EP01"
    assert fetched["source_zh"] == "我等了你三个小时"
    assert fetched["issues"] == []


def test_duplicate_segment_returns_409(client, segment):
    response = client.post("/api/segments", json={"episode": "EP01", "line_ref": "002", "source_zh": "重复"})
    assert response.status_code == 409


def test_missing_fields_return_400(client):
    response = client.post("/api/segments", json={"episode": "EP01"})
    assert response.status_code == 400
    assert "line_ref" in response.get_json()["message"]


def test_non_json_body_returns_400(client):
    response = client.post("/api/segments", data="not json", content_type="text/plain")
    assert response.status_code == 400


def test_unknown_segment_returns_404_json(client):
    response = client.get("/api/segments/999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Not Found"


def test_update_translation(client, segment):
    response = client.patch(f"/api/segments/{segment['id']}", json={"translation": "I waited three hours for you"})
    assert response.get_json()["translation"] == "I waited three hours for you"


def test_segment_list_counts_open_issues(client, segment):
    first = add_issue(client, segment["id"])
    add_issue(client, segment["id"], issue_type="tone")
    client.patch(f"/api/issues/{first['id']}", json={"status": "resolved"})
    listed = client.get("/api/segments?episode=EP01").get_json()
    assert listed[0]["open_issues"] == 1


# ----------------------------------------------------------------- issues


def test_create_issue_returns_segment_context(client, segment):
    issue = add_issue(client, segment["id"], severity="high", note="三个小时 lost the number")
    assert issue["status"] == "open"
    assert issue["episode"] == "EP01"
    assert issue["translation"] == "I waited for you for hours"


def test_invalid_severity_is_rejected(client, segment):
    response = client.post(f"/api/segments/{segment['id']}/issues", json={"issue_type": "tone", "severity": "urgent"})
    assert response.status_code == 400


def test_issue_on_missing_segment_returns_404(client):
    response = client.post("/api/segments/42/issues", json={"issue_type": "tone", "severity": "low"})
    assert response.status_code == 404


def test_resolve_sets_timestamp_and_reopen_clears_it(client, segment):
    issue = add_issue(client, segment["id"])
    resolved = client.patch(f"/api/issues/{issue['id']}", json={"status": "resolved"}).get_json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    reopened = client.patch(f"/api/issues/{issue['id']}", json={"status": "open"}).get_json()
    assert reopened["resolved_at"] is None


def test_filters_and_severity_ordering(client, segment):
    add_issue(client, segment["id"], severity="low", issue_type="punctuation")
    add_issue(client, segment["id"], severity="high", issue_type="number_mismatch")
    add_issue(client, segment["id"], severity="medium", issue_type="tone")

    all_open = client.get("/api/issues?status=open").get_json()
    assert [i["severity"] for i in all_open] == ["high", "medium", "low"]

    high_only = client.get("/api/issues?severity=high").get_json()
    assert [i["issue_type"] for i in high_only] == ["number_mismatch"]

    assert client.get("/api/issues?status=closed").status_code == 400


def test_delete_issue(client, segment):
    issue = add_issue(client, segment["id"])
    assert client.delete(f"/api/issues/{issue['id']}").status_code == 204
    assert client.delete(f"/api/issues/{issue['id']}").status_code == 404


def test_deleting_segment_rows_cascades(app, client, segment):
    add_issue(client, segment["id"])
    with app.app_context():
        from tracker.db import get_db
        db = get_db()
        db.execute("DELETE FROM segments WHERE id = ?", (segment["id"],))
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0


# ------------------------------------------------------------------ stats


def test_stats_aggregates(client, segment):
    other = client.post("/api/segments", json={"episode": "EP02", "line_ref": "001", "source_zh": "你好"}).get_json()
    add_issue(client, segment["id"], severity="high")
    add_issue(client, segment["id"], severity="high", issue_type="tone")
    done = add_issue(client, other["id"], severity="low", issue_type="tone")
    client.patch(f"/api/issues/{done['id']}", json={"status": "resolved"})

    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 3
    assert stats["open"] == 2
    assert stats["resolved"] == 1
    assert stats["open_by_severity"] == {"low": 0, "medium": 0, "high": 2}
    assert stats["by_type"][0] == {"issue_type": "tone", "total": 2, "open": 1}
    assert stats["open_by_episode"] == [{"episode": "EP01", "open_issues": 2}]
    assert stats["avg_hours_to_resolve"] is not None


def test_stats_on_empty_database(client):
    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 0
    assert stats["open"] == 0
    assert stats["avg_hours_to_resolve"] is None
