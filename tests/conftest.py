import threading

import pytest
from werkzeug.serving import make_server

from tracker import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite")})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def segment(client):
    """A segment that tests can attach issues to."""
    response = client.post("/api/segments", json={
        "episode": "EP01", "line_ref": "002",
        "source_zh": "我等了你三个小时", "translation": "I waited for you for hours",
    })
    assert response.status_code == 201
    return response.get_json()


@pytest.fixture
def live_server(app):
    """Run the app on a free local port for browser tests."""
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
