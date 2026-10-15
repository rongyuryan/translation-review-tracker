"""Translation review tracker: a Flask + SQLite REST API with a small web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from flask import Flask

from . import api, db


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get("TRACKER_DATABASE", str(Path(app.instance_path) / "tracker.sqlite")),
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    db.register(app)
    app.register_blueprint(api.bp)
    with app.app_context():
        db.init_db()
    return app
