"""HTTPS boundary for the iPhone's read-only RHYTHMOS snapshot.

Polar OAuth exchanges and refresh tokens stay on this service.  The mobile
client can only request a validated daily projection or ask the service to
run its normal ingestion pipeline; it never receives a Polar credential.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time
import urllib.parse
from datetime import date
from typing import Any, Callable

import requests
from flask import Flask, Response, jsonify, redirect, request, session
from requests.auth import HTTPBasicAuth

from .mobile_snapshot import build_mobile_daily_snapshot
from .polar_client import TOKEN_FILE
from .secure_token_store import TokenStoreError, token_store_for
from .sync_pipeline import PipelineError, PipelineRunner


AUTH_URL = "https://auth.polar.com/oauth/authorize"
TOKEN_URL = "https://auth.polar.com/oauth/token"
SCOPES = (
    "training_sessions:read",
    "activity:read",
    "sleep:read",
    "nightly_recharge:read",
    "continuous_samples:read",
    "profile:read",
    "sports:read",
)


def _settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    values = {
        "POLAR_CLIENT_ID": os.getenv("POLAR_CLIENT_ID"),
        "POLAR_CLIENT_SECRET": os.getenv("POLAR_CLIENT_SECRET"),
        "POLAR_REDIRECT_URI": os.getenv("POLAR_REDIRECT_URI"),
        "POLAR_TOKEN_ENCRYPTION_KEY": os.getenv("POLAR_TOKEN_ENCRYPTION_KEY"),
        "MOBILE_SYNC_API_TOKEN": os.getenv("MOBILE_SYNC_API_TOKEN"),
        "POLAR_CONNECT_USERNAME": os.getenv("POLAR_CONNECT_USERNAME", "owner"),
        "POLAR_CONNECT_PASSWORD": os.getenv("POLAR_CONNECT_PASSWORD"),
        "FLASK_SECRET_KEY": os.getenv("FLASK_SECRET_KEY"),
        "POLAR_TOKEN_FILE": str(TOKEN_FILE),
    }
    if overrides:
        values.update(overrides)
    return values


def _required_settings(settings: dict[str, Any], *keys: str) -> list[str]:
    return [key for key in keys if not settings.get(key)]


def _api_authorized(settings: dict[str, Any]) -> bool:
    expected = settings.get("MOBILE_SYNC_API_TOKEN")
    header = request.headers.get("Authorization", "")
    if not expected or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header.removeprefix("Bearer "), expected)


def _connect_authorized(settings: dict[str, Any]) -> bool:
    credentials = request.authorization
    expected_user = settings.get("POLAR_CONNECT_USERNAME")
    expected_password = settings.get("POLAR_CONNECT_PASSWORD")
    return bool(
        credentials
        and expected_user
        and expected_password
        and hmac.compare_digest(credentials.username or "", expected_user)
        and hmac.compare_digest(credentials.password or "", expected_password)
    )


def _safe_summary(summary: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "success", "run_id", "duration", "records_imported", "metrics_updated",
        "baseline_updated", "recovery_updated", "confidence_updated", "warning_count",
    }
    return {key: summary[key] for key in allowed if key in summary}


def create_app(
    config: dict[str, Any] | None = None,
    *,
    runner_factory: Callable[[], PipelineRunner] = PipelineRunner,
    snapshot_builder: Callable[..., dict[str, Any] | None] = build_mobile_daily_snapshot,
    http_post: Callable[..., requests.Response] = requests.post,
) -> Flask:
    """Create the service without requiring deploy-time secrets at import time."""
    settings = _settings(config)
    app = Flask(__name__)
    app.config.update(settings)
    app.secret_key = settings["FLASK_SECRET_KEY"] or secrets.token_urlsafe(32)

    def service_settings() -> dict[str, Any]:
        return {key: app.config.get(key) for key in settings}

    def api_guard() -> Response | None:
        current = service_settings()
        missing = _required_settings(current, "MOBILE_SYNC_API_TOKEN")
        if missing:
            return jsonify(error="SYNC_NOT_CONFIGURED"), 503
        if not _api_authorized(current):
            return jsonify(error="UNAUTHORIZED"), 401
        return None

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz")
    def healthz() -> Response:
        return jsonify(status="ok")

    @app.get("/connect/polar")
    def connect_polar() -> Response:
        current = service_settings()
        missing = _required_settings(
            current,
            "POLAR_CLIENT_ID", "POLAR_CLIENT_SECRET", "POLAR_REDIRECT_URI",
            "POLAR_TOKEN_ENCRYPTION_KEY", "FLASK_SECRET_KEY", "POLAR_CONNECT_PASSWORD",
        )
        if missing:
            return jsonify(error="SYNC_NOT_CONFIGURED", missing=missing), 503
        if not _connect_authorized(current):
            response = jsonify(error="CONNECT_AUTH_REQUIRED")
            response.status_code = 401
            response.headers["WWW-Authenticate"] = 'Basic realm="RHYTHMOS Polar setup"'
            return response

        state = secrets.token_urlsafe(32)
        session["polar_oauth_state"] = state
        query = urllib.parse.urlencode({
            "client_id": current["POLAR_CLIENT_ID"],
            "response_type": "code",
            "redirect_uri": current["POLAR_REDIRECT_URI"],
            "scope": " ".join(SCOPES),
            "state": state,
        })
        return redirect(f"{AUTH_URL}?{query}")

    @app.get("/oauth2_callback")
    def oauth2_callback() -> Response:
        current = service_settings()
        if request.args.get("error"):
            return Response("Polar authorization was cancelled or rejected.", status=400, mimetype="text/plain")
        code = request.args.get("code")
        state = request.args.get("state")
        if not code or not state or not hmac.compare_digest(state, session.get("polar_oauth_state", "")):
            return Response("Polar authorization state validation failed. Start again from /connect/polar.", status=400, mimetype="text/plain")
        missing = _required_settings(
            current,
            "POLAR_CLIENT_ID", "POLAR_CLIENT_SECRET", "POLAR_REDIRECT_URI", "POLAR_TOKEN_ENCRYPTION_KEY",
        )
        if missing:
            return jsonify(error="SYNC_NOT_CONFIGURED", missing=missing), 503

        response = http_post(
            TOKEN_URL,
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": current["POLAR_REDIRECT_URI"]},
            auth=HTTPBasicAuth(current["POLAR_CLIENT_ID"], current["POLAR_CLIENT_SECRET"]),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=30,
        )
        if response.status_code >= 400:
            return Response("Polar token exchange failed. Please retry authorization.", status=502, mimetype="text/plain")
        try:
            tokens = response.json()
            if not isinstance(tokens, dict) or not tokens.get("access_token"):
                raise ValueError("invalid token response")
            tokens["expires_at"] = int(time.time()) + int(tokens.get("expires_in", 0)) - 60
            token_store_for(current["POLAR_TOKEN_FILE"], current["POLAR_TOKEN_ENCRYPTION_KEY"]).save(tokens)
        except (TokenStoreError, ValueError, TypeError):
            return Response("Could not safely save Polar authorization. Please check server configuration.", status=503, mimetype="text/plain")
        session.pop("polar_oauth_state", None)
        return Response("Polar connected. You can return to RHYTHMOS.", mimetype="text/plain")

    @app.get("/v1/mobile/status")
    def mobile_status() -> Response:
        guard = api_guard()
        if guard:
            return guard
        current = service_settings()
        try:
            connected = token_store_for(
                current["POLAR_TOKEN_FILE"], current["POLAR_TOKEN_ENCRYPTION_KEY"],
            ).load().get("access_token") is not None
        except TokenStoreError:
            connected = False
        return jsonify(connected=connected, source="polar", snapshot_contract_version=1)

    @app.post("/v1/mobile/sync")
    def sync_mobile_data() -> Response:
        guard = api_guard()
        if guard:
            return guard
        try:
            summary = runner_factory().run(if_new_data=True, trigger_type="scheduled")
        except PipelineError as error:
            return jsonify(error="SYNC_FAILED", summary=_safe_summary(error.summary)), 502
        except Exception:
            return jsonify(error="SYNC_FAILED"), 502
        return jsonify(_safe_summary(summary))

    @app.get("/v1/mobile/daily-snapshot")
    def daily_snapshot() -> Response:
        guard = api_guard()
        if guard:
            return guard
        requested_date = request.args.get("date")
        if requested_date:
            try:
                date.fromisoformat(requested_date)
            except ValueError:
                return jsonify(error="INVALID_DATE"), 400
        snapshot = snapshot_builder(snapshot_date=requested_date) if requested_date else snapshot_builder()
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 404
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()
