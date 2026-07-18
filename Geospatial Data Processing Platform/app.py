"""HTTP API for MapWork.ai.

The API can run in two modes:

* demo mode works without external credentials and exposes deterministic sample scans;
* connected mode adds PostGIS and imagery providers when their environment variables exist.

Run locally with ``python app.py`` or ``flask --app app:create_app run``.
"""

import logging
import time
from contextlib import closing
from typing import Any, Dict, Tuple
from uuid import uuid4

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import HTTPException

from config import Config
from demo_service import ScanValidationError, list_areas, run_demo_scan

try:
    import psycopg2
except ImportError:  # The demo API remains runnable without the Postgres adapter.
    psycopg2 = None


LOGGER = logging.getLogger("mapwork.api")


def create_app(config: Config = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAPWORK_CONFIG"] = config or Config.from_environment()
    configure_logging(app.config["MAPWORK_CONFIG"].log_level)
    register_request_hooks(app)
    register_error_handlers(app)
    register_routes(app)
    return app


def configure_logging(level: str) -> None:
    resolved_level = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    LOGGER.setLevel(resolved_level)


def register_request_hooks(app: Flask) -> None:
    @app.before_request
    def start_request() -> None:
        g.request_started_at = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID", str(uuid4()))

    @app.after_request
    def add_response_metadata(response: Response) -> Response:
        elapsed_ms = (time.perf_counter() - g.request_started_at) * 1000
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Response-Time"] = "{:.2f}ms".format(elapsed_ms)
        response.headers["Cache-Control"] = "no-store"
        LOGGER.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
            g.request_id,
        )
        return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ScanValidationError)
    def handle_validation_error(error: ScanValidationError) -> Tuple[Response, int]:
        return api_error("invalid_scan_request", str(error), 400)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> Tuple[Response, int]:
        return api_error(error.name.lower().replace(" ", "_"), error.description, error.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> Tuple[Response, int]:
        LOGGER.exception("unhandled_error request_id=%s", getattr(g, "request_id", "unknown"))
        return api_error("internal_error", "The request could not be completed.", 500)


def api_error(code: str, message: str, status: int) -> Tuple[Response, int]:
    return jsonify({
        "error": {"code": code, "message": message},
        "request_id": getattr(g, "request_id", None),
    }), status


def register_routes(app: Flask) -> None:
    @app.get("/")
    def index() -> Response:
        return jsonify({
            "name": "MapWork.ai API",
            "version": "1.0.0",
            "mode": "demo-ready",
            "endpoints": {
                "health": "/api/v1/health",
                "areas": "/api/v1/areas",
                "scan": "POST /api/v1/scans",
            },
        })

    @app.get("/api/v1/health")
    def health() -> Response:
        config = get_config(app)
        integrations = config.integration_status()
        connected_count = sum(item["configured"] for item in integrations.values())
        return jsonify({
            "status": "healthy",
            "mode": "connected" if connected_count else "demo",
            "integrations": integrations,
            "request_id": g.request_id,
        })

    @app.get("/api/v1/areas")
    def areas() -> Response:
        return jsonify({"data": list_areas(), "count": len(list_areas())})

    @app.post("/api/v1/scans")
    def create_scan() -> Tuple[Response, int]:
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        scan = run_demo_scan(payload)
        scan["request_id"] = g.request_id
        return jsonify(scan), 201

    @app.get("/api/v1/database/status")
    def database_status() -> Tuple[Response, int]:
        config = get_config(app)
        if not config.database_configured:
            return jsonify({"status": "not_configured", "detail": "Demo API is still available."}), 200
        if psycopg2 is None:
            return api_error("adapter_missing", "PostgreSQL adapter is not installed.", 503)

        started_at = time.perf_counter()
        try:
            with closing(psycopg2.connect(**config.database_parameters, connect_timeout=3)) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_database(), PostGIS_Version();")
                    database, postgis_version = cursor.fetchone()
            return jsonify({
                "status": "connected",
                "database": database,
                "postgis_version": postgis_version,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            }), 200
        except Exception:
            LOGGER.exception("database_probe_failed request_id=%s", g.request_id)
            return api_error("database_unavailable", "PostGIS could not be reached.", 503)


def get_config(app: Flask) -> Config:
    return app.config["MAPWORK_CONFIG"]


app = create_app()


if __name__ == "__main__":
    runtime_config = get_config(app)
    app.run(host=runtime_config.host, port=runtime_config.port, debug=runtime_config.debug)
