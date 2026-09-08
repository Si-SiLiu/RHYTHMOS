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
from uuid import uuid4

import requests
from flask import Flask, Response, jsonify, redirect, request, session
from requests.auth import HTTPBasicAuth

from .mobile_snapshot import build_mobile_daily_snapshot
from .mobile_recovery_history import (
    MAX_DAYS as RECOVERY_HISTORY_MAX_DAYS,
    MobileRecoveryHistoryError,
    build_mobile_recovery_history,
)
from .mobile_training_history import (
    MobileTrainingHistoryError,
    build_mobile_training_history,
)
from .mobile_kubios_import import (
    MobileKubiosImportError,
    import_mobile_morning_hrv_measurement,
    import_mobile_screenshot_measurement,
)
from .mobile_nutrition_input import MobileNutritionInputError, save_mobile_manual_nutrition_entry
from .mobile_nutrition_library import (
    MobileNutritionLibraryError,
    mobile_food_nutrition_library,
    parse_mobile_food_label,
    save_mobile_food_label,
)
from .mobile_nutrition_plan_input import (
    MobileNutritionPlanInputError,
    save_mobile_nutrition_plan_entry,
)
from .mobile_personal_input import (
    MobilePersonalInputError,
    save_mobile_body_measurement,
    save_mobile_personal_profile,
)
from .cloud_sync_store import CloudSyncError, DOCUMENT_TYPES, cloud_store_from_settings
from .polar_client import TOKEN_FILE
from .secure_token_store import TokenStoreError, token_store_for
from .sync_pipeline import PipelineError, PipelineRunner


AUTH_URL = "https://auth.polar.com/oauth/authorize"
TOKEN_URL = "https://auth.polar.com/oauth/token"
USER_REGISTRATION_URL = "https://www.polaraccesslink.com/v3/users"
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
        "POLAR_MEMBER_ID": os.getenv("POLAR_MEMBER_ID", "daily-recovery-coach-local"),
        "MOBILE_SYNC_API_TOKEN": os.getenv("MOBILE_SYNC_API_TOKEN"),
        "POLAR_CONNECT_USERNAME": os.getenv("POLAR_CONNECT_USERNAME", "owner"),
        "POLAR_CONNECT_PASSWORD": os.getenv("POLAR_CONNECT_PASSWORD"),
        "FLASK_SECRET_KEY": os.getenv("FLASK_SECRET_KEY"),
        "POLAR_TOKEN_FILE": str(TOKEN_FILE),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "CLOUD_SYNC_SOURCE_DEVICE": os.getenv("CLOUD_SYNC_SOURCE_DEVICE", "render-polar-service"),
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
    history_builder: Callable[..., dict[str, Any]] = build_mobile_recovery_history,
    training_history_builder: Callable[..., dict[str, Any]] = build_mobile_training_history,
    screenshot_importer: Callable[[dict[str, Any]], dict[str, Any]] = import_mobile_screenshot_measurement,
    morning_hrv_importer: Callable[[dict[str, Any]], dict[str, Any]] = import_mobile_morning_hrv_measurement,
    nutrition_entry_saver: Callable[[dict[str, Any]], dict[str, str]] = save_mobile_manual_nutrition_entry,
    nutrition_label_parser: Callable[[dict[str, Any]], dict[str, Any]] = parse_mobile_food_label,
    nutrition_label_saver: Callable[[dict[str, Any]], dict[str, Any]] = save_mobile_food_label,
    nutrition_library_loader: Callable[[], dict[str, list[dict[str, Any]]]] = mobile_food_nutrition_library,
    nutrition_plan_entry_saver: Callable[[dict[str, Any]], dict[str, str]] = save_mobile_nutrition_plan_entry,
    personal_profile_saver: Callable[[dict[str, Any]], dict[str, str]] = save_mobile_personal_profile,
    body_measurement_saver: Callable[[dict[str, Any]], dict[str, str]] = save_mobile_body_measurement,
    cloud_store_factory: Callable[[dict[str, Any]], Any] = cloud_store_from_settings,
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

    def cloud_store() -> Any | None:
        """Build an optional cloud store without making cloud configuration required."""
        try:
            return cloud_store_factory(service_settings())
        except (CloudSyncError, ValueError):
            return None

    def cloud_account_id() -> str:
        # Polar's member id is controlled server-side and scopes the initial
        # small-test account. A multi-account identity layer will replace it.
        return str(service_settings()["POLAR_MEMBER_ID"])

    def load_cloud_document(document_type: str, document_key: str) -> dict[str, Any] | None:
        store = cloud_store()
        if store is None:
            return None
        try:
            document = store.load(cloud_account_id(), document_type, document_key)
        except (CloudSyncError, ValueError):
            return None
        return document.payload if document else None

    def save_cloud_document(document_type: str, document_key: str, payload: dict[str, Any]) -> bool:
        store = cloud_store()
        if store is None:
            return False
        try:
            store.save(
                cloud_account_id(), document_type, document_key, payload,
                str(service_settings()["CLOUD_SYNC_SOURCE_DEVICE"]),
            )
        except (CloudSyncError, ValueError):
            return False
        return True

    def cloud_snapshot(snapshot: dict[str, Any]) -> None:
        snapshot_date = snapshot.get("date")
        if isinstance(snapshot_date, str):
            save_cloud_document("daily_snapshot", snapshot_date, snapshot)

    def cloud_mobile_change(kind: str, payload: dict[str, Any]) -> None:
        """Queue an iOS-confirmed write for the local Mac database.

        The Render service remains the sole cloud credential holder.  The
        queue contains only the validated form fields already accepted by the
        iOS endpoint; it never contains an image, a Polar token, or a SQLite
        database.  Individual immutable documents make delivery idempotent.
        """
        if kind not in {
            "kubios_screenshot", "morning_hrv", "nutrition_entry",
            "nutrition_plan_entry", "personal_profile", "body_measurement",
            "food_nutrition_label",
        }:
            return
        save_cloud_document(
            "mobile_change", f"ios:{uuid4()}",
            {"kind": kind, "payload": payload, "version": 1},
        )

    def cloud_recovery_history(days: int = 28) -> None:
        """Refresh the mobile history projection after recovery data changes."""
        try:
            history = history_builder(days=days)
        except Exception:
            # Projection availability must not turn an otherwise successful
            # Polar or reviewed-screenshot import into a failed operation.
            return
        if isinstance(history, dict):
            save_cloud_document("recovery_history", f"days:{days}", history)

    def cloud_error_response(error: CloudSyncError | ValueError) -> Response:
        """Return a stable, non-sensitive cloud storage failure code."""
        failure_code = error.failure_code if isinstance(error, CloudSyncError) else "configuration"
        return jsonify(error=f"CLOUD_SYNC_{failure_code.upper()}"), 502

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz")
    def healthz() -> Response:
        # This deliberately exposes only readiness booleans, never credentials,
        # account identifiers, health records, or Polar connection state.
        current = service_settings()
        return jsonify(
            status="ok",
            supabase_url_configured=bool(current.get("SUPABASE_URL")),
            supabase_service_role_configured=bool(current.get("SUPABASE_SERVICE_ROLE_KEY")),
            cloud_sync_configured=bool(
                current.get("SUPABASE_URL") and current.get("SUPABASE_SERVICE_ROLE_KEY")
            ),
            mobile_sync_configured=bool(current.get("MOBILE_SYNC_API_TOKEN")),
        )

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
            registration = http_post(
                USER_REGISTRATION_URL,
                json={"member-id": current["POLAR_MEMBER_ID"]},
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            # A user may already exist when authorization is repeated after an
            # instance rebuild. Polar reports that state as a conflict, which
            # still means the account is registered and may be synchronized.
            if registration.status_code not in {200, 201, 409}:
                raise ValueError("Polar user registration failed")
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
        # A failed cloud projection must not hide a successful provider sync.
        # The next authenticated read retries the projection.
        snapshot = snapshot_builder()
        if isinstance(snapshot, dict):
            cloud_snapshot(snapshot)
        cloud_recovery_history()
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
        document_key = requested_date or date.today().isoformat()
        snapshot = load_cloud_document("daily_snapshot", document_key)
        if snapshot is None:
            snapshot = snapshot_builder(snapshot_date=requested_date) if requested_date else snapshot_builder()
            if isinstance(snapshot, dict):
                cloud_snapshot(snapshot)
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 404
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/v1/mobile/recovery-history")
    def recovery_history() -> Response:
        guard = api_guard()
        if guard:
            return guard
        requested_days = request.args.get("days", "28")
        try:
            days = int(requested_days)
            if not 1 <= days <= RECOVERY_HISTORY_MAX_DAYS:
                raise MobileRecoveryHistoryError(
                    f"days must be between 1 and {RECOVERY_HISTORY_MAX_DAYS}"
                )
            history = load_cloud_document("recovery_history", f"days:{days}")
            if history is None:
                history = history_builder(days=days)
                if isinstance(history, dict):
                    save_cloud_document("recovery_history", f"days:{days}", history)
        except (TypeError, ValueError, MobileRecoveryHistoryError):
            return jsonify(error="INVALID_HISTORY_RANGE"), 400
        response = jsonify(history)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/v1/mobile/training-history")
    def training_history() -> Response:
        guard = api_guard()
        if guard:
            return guard
        requested_days = request.args.get("days", "30")
        try:
            days = int(requested_days)
            history = load_cloud_document("training_history", f"days:{days}")
            if history is None:
                history = training_history_builder(days=days)
                if isinstance(history, dict):
                    save_cloud_document("training_history", f"days:{days}", history)
        except (TypeError, ValueError, MobileTrainingHistoryError):
            return jsonify(error="INVALID_HISTORY_RANGE"), 400
        response = jsonify(history)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/kubios-screenshot-import")
    def import_kubios_screenshot() -> Response:
        """Accept reviewed local OCR values, never an iPhone screenshot image."""
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_SCREENSHOT_PAYLOAD"), 400
        try:
            result = screenshot_importer(payload)
        except MobileKubiosImportError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="SCREENSHOT_IMPORT_FAILED"), 502
        cloud_mobile_change("kubios_screenshot", payload)
        snapshot = snapshot_builder(snapshot_date=result["date"])
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 502
        cloud_snapshot(snapshot)
        cloud_recovery_history()
        response = jsonify(snapshot)
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/morning-hrv-import")
    def import_morning_hrv() -> Response:
        """Accept reviewed derived metrics from an iPhone device measurement."""
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_DEVICE_MEASUREMENT_PAYLOAD"), 400
        try:
            result = morning_hrv_importer(payload)
        except MobileKubiosImportError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="DEVICE_MEASUREMENT_IMPORT_FAILED"), 502
        cloud_mobile_change("morning_hrv", payload)
        snapshot = snapshot_builder(snapshot_date=result["date"])
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 502
        cloud_snapshot(snapshot)
        cloud_recovery_history()
        response = jsonify(snapshot)
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/nutrition-entry")
    def save_nutrition_entry() -> Response:
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_NUTRITION_PAYLOAD"), 400
        try:
            result = nutrition_entry_saver(payload)
        except MobileNutritionInputError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="NUTRITION_SAVE_FAILED"), 502
        cloud_mobile_change("nutrition_entry", payload)
        snapshot = snapshot_builder(snapshot_date=result["date"])
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 502
        cloud_snapshot(snapshot)
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/nutrition-plan-entry")
    def save_nutrition_plan_entry() -> Response:
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_NUTRITION_PLAN_PAYLOAD"), 400
        try:
            result = nutrition_plan_entry_saver(payload)
        except MobileNutritionPlanInputError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="NUTRITION_PLAN_SAVE_FAILED"), 502
        cloud_mobile_change("nutrition_plan_entry", payload)
        snapshot = snapshot_builder(snapshot_date=result["date"])
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 502
        cloud_snapshot(snapshot)
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/personal-profile")
    def save_personal_profile() -> Response:
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_PROFILE_PAYLOAD"), 400
        try:
            result = personal_profile_saver(payload)
        except MobilePersonalInputError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="PROFILE_SAVE_FAILED"), 502
        cloud_mobile_change("personal_profile", payload)
        snapshot = snapshot_builder(snapshot_date=result["date"])
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 502
        cloud_snapshot(snapshot)
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/body-measurement")
    def save_body_measurement() -> Response:
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_BODY_PAYLOAD"), 400
        try:
            result = body_measurement_saver(payload)
        except MobilePersonalInputError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="BODY_SAVE_FAILED"), 502
        cloud_mobile_change("body_measurement", payload)
        snapshot = snapshot_builder(snapshot_date=result["date"])
        if snapshot is None:
            return jsonify(error="SNAPSHOT_UNAVAILABLE"), 502
        cloud_snapshot(snapshot)
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/nutrition-label/parse")
    def parse_nutrition_label() -> Response:
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_NUTRITION_LABEL_PAYLOAD"), 400
        try:
            result = nutrition_label_parser(payload)
        except MobileNutritionLibraryError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="NUTRITION_LABEL_PARSE_FAILED"), 502
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/v1/mobile/nutrition-library/food")
    def food_nutrition_library() -> Response:
        guard = api_guard()
        if guard:
            return guard
        try:
            result = nutrition_library_loader()
        except Exception:
            return jsonify(error="NUTRITION_LIBRARY_UNAVAILABLE"), 502
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/mobile/nutrition-library/food")
    def save_food_nutrition_label() -> Response:
        guard = api_guard()
        if guard:
            return guard
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="INVALID_NUTRITION_LABEL_PAYLOAD"), 400
        try:
            result = nutrition_label_saver(payload)
        except MobileNutritionLibraryError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            return jsonify(error="NUTRITION_LABEL_SAVE_FAILED"), 502
        cloud_mobile_change("food_nutrition_label", payload)
        response = jsonify(result)
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/v1/cloud/documents/<document_type>/<document_key>")
    def get_cloud_document(document_type: str, document_key: str) -> Response:
        """Authenticated pull endpoint for the local macOS application."""
        guard = api_guard()
        if guard:
            return guard
        if document_type not in DOCUMENT_TYPES:
            return jsonify(error="INVALID_CLOUD_DOCUMENT_TYPE"), 400
        store = cloud_store()
        if store is None:
            return jsonify(error="CLOUD_SYNC_NOT_CONFIGURED"), 503
        try:
            document = store.load(cloud_account_id(), document_type, document_key)
        except (CloudSyncError, ValueError) as error:
            return cloud_error_response(error)
        if document is None:
            return jsonify(error="CLOUD_DOCUMENT_NOT_FOUND"), 404
        response = jsonify(
            revision=document.revision,
            payload=document.payload,
            payload_sha256=document.payload_sha256,
            source_device=document.source_device,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/v1/cloud/changes")
    def list_cloud_changes() -> Response:
        """Return the private iOS write inbox for the connected Mac only."""
        guard = api_guard()
        if guard:
            return guard
        try:
            limit = int(request.args.get("limit", "200"))
            store = cloud_store()
            if store is None:
                return jsonify(error="CLOUD_SYNC_NOT_CONFIGURED"), 503
            documents = store.list_documents(cloud_account_id(), "mobile_change", limit=limit)
        except (TypeError, ValueError):
            return jsonify(error="INVALID_CLOUD_CHANGE_LIMIT"), 400
        except CloudSyncError as error:
            return cloud_error_response(error)
        response = jsonify(changes=[
            {
                "id": document.document_key,
                "payload": document.payload,
                "source_device": document.source_device,
                "updated_at": document.updated_at,
            }
            for document in documents
        ])
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/cloud/documents/<document_type>/<document_key>")
    def put_cloud_document(document_type: str, document_key: str) -> Response:
        """Authenticated push endpoint for the local macOS application."""
        guard = api_guard()
        if guard:
            return guard
        if document_type not in DOCUMENT_TYPES:
            return jsonify(error="INVALID_CLOUD_DOCUMENT_TYPE"), 400
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("payload"), dict):
            return jsonify(error="INVALID_CLOUD_DOCUMENT_PAYLOAD"), 400
        store = cloud_store()
        if store is None:
            return jsonify(error="CLOUD_SYNC_NOT_CONFIGURED"), 503
        source_device = payload.get("source_device")
        if not isinstance(source_device, str) or not source_device or len(source_device) > 160:
            return jsonify(error="INVALID_CLOUD_SOURCE_DEVICE"), 400
        try:
            document = store.save(
                cloud_account_id(), document_type, document_key, payload["payload"], source_device,
            )
        except (CloudSyncError, ValueError) as error:
            return cloud_error_response(error)
        response = jsonify(
            revision=document.revision,
            payload_sha256=document.payload_sha256,
            source_device=document.source_device,
        )
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()
