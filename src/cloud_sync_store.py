"""Private, versioned RHYTHMOS document storage in Supabase.

Only the Render service constructs this client.  The Supabase service-role key
must never be bundled with the macOS or iOS applications.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping
from urllib.parse import urlparse

import requests


DOCUMENT_TYPES = frozenset({
    "daily_snapshot", "recovery_history", "training_history", "nutrition_history", "personal_history",
    "mobile_change", "mobile_request", "mobile_session", "mobile_account", "mobile_credential",
})
TABLE_NAME = "rhythmos_sync_documents"


class CloudSyncError(RuntimeError):
    """Raised when the private cloud projection cannot be safely used."""

    def __init__(self, message: str, *, failure_code: str = "unavailable"):
        super().__init__(message)
        self.failure_code = failure_code


def _response_failure_code(status_code: int) -> str:
    """Classify an upstream response without retaining its body or headers."""
    if status_code in {401, 403}:
        return "credentials"
    if status_code in {404, 406}:
        return "schema"
    if status_code == 429:
        return "throttled"
    return "unavailable"


@dataclass(frozen=True)
class CloudDocument:
    account_id: str
    document_type: str
    document_key: str
    revision: int
    payload: dict[str, Any]
    payload_sha256: str
    source_device: str
    updated_at: str | None = None


def payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


class SupabaseCloudDocumentStore:
    """Small REST client for the RLS-protected Supabase sync table."""

    def __init__(self, base_url: str, service_role_key: str, *, http: Any = requests, timeout: int = 15):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("SUPABASE_URL must be a valid HTTPS URL")
        if not service_role_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required")
        self._endpoint = f"{base_url.rstrip('/')}/rest/v1/{TABLE_NAME}"
        self._http = http
        self._timeout = timeout
        self._headers = {
            "apikey": service_role_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Supabase's newer sb_secret_* keys are API keys, not JWTs.  Sending
        # one in Authorization makes the REST gateway try to parse it as a JWT
        # and reject it.  Keep the Authorization header for the legacy JWT
        # service_role key while migrating existing test deployments safely.
        if not service_role_key.startswith("sb_secret_"):
            self._headers["Authorization"] = f"Bearer {service_role_key}"

    def load(self, account_id: str, document_type: str, document_key: str) -> CloudDocument | None:
        self._validate_identity(account_id, document_type, document_key)
        response = self._http.get(
            self._endpoint,
            headers=self._headers,
            params={
                "select": "account_id,document_type,document_key,revision,payload,payload_sha256,source_device",
                "account_id": f"eq.{account_id}",
                "document_type": f"eq.{document_type}",
                "document_key": f"eq.{document_key}",
                "limit": "1",
            },
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise CloudSyncError(
                "cloud document lookup failed",
                failure_code=_response_failure_code(response.status_code),
            )
        try:
            rows = response.json()
        except ValueError as error:
            raise CloudSyncError("cloud document lookup returned invalid JSON") from error
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
            raise CloudSyncError("cloud document shape is invalid")
        return CloudDocument(
            account_id=str(row["account_id"]),
            document_type=str(row["document_type"]),
            document_key=str(row["document_key"]),
            revision=int(row["revision"]),
            payload=row["payload"],
            payload_sha256=str(row["payload_sha256"]),
            source_device=str(row["source_device"]),
            updated_at=str(row["updated_at"]) if row.get("updated_at") is not None else None,
        )

    def list_documents(
        self, account_id: str, document_type: str, *, limit: int = 200,
    ) -> list[CloudDocument]:
        """Return an account-scoped ordered document collection for sync inboxes."""
        if not account_id or len(account_id) > 160 or document_type not in DOCUMENT_TYPES:
            raise ValueError("invalid cloud document collection")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("invalid cloud document limit")
        response = self._http.get(
            self._endpoint,
            headers=self._headers,
            params={
                "select": "account_id,document_type,document_key,revision,payload,payload_sha256,source_device,updated_at",
                "account_id": f"eq.{account_id}",
                "document_type": f"eq.{document_type}",
                "order": "updated_at.asc,document_key.asc",
                "limit": str(limit),
            },
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise CloudSyncError(
                "cloud document collection lookup failed",
                failure_code=_response_failure_code(response.status_code),
            )
        try:
            rows = response.json()
        except ValueError as error:
            raise CloudSyncError("cloud document collection returned invalid JSON") from error
        if not isinstance(rows, list):
            raise CloudSyncError("cloud document collection shape is invalid")
        documents: list[CloudDocument] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
                raise CloudSyncError("cloud document collection item is invalid")
            documents.append(CloudDocument(
                account_id=str(row["account_id"]),
                document_type=str(row["document_type"]),
                document_key=str(row["document_key"]),
                revision=int(row["revision"]),
                payload=row["payload"],
                payload_sha256=str(row["payload_sha256"]),
                source_device=str(row["source_device"]),
                updated_at=str(row["updated_at"]) if row.get("updated_at") is not None else None,
            ))
        return documents

    def save(
        self,
        account_id: str,
        document_type: str,
        document_key: str,
        payload: Mapping[str, Any],
        source_device: str,
    ) -> CloudDocument:
        self._validate_identity(account_id, document_type, document_key)
        if not isinstance(payload, Mapping) or not source_device or len(source_device) > 160:
            raise ValueError("invalid cloud document payload or source device")
        existing = self.load(account_id, document_type, document_key)
        document = {
            "account_id": account_id,
            "document_type": document_type,
            "document_key": document_key,
            "revision": (existing.revision + 1) if existing else 1,
            "payload": dict(payload),
            "payload_sha256": payload_sha256(payload),
            "source_device": source_device,
        }
        response = self._http.post(
            self._endpoint,
            headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=representation"},
            json=document,
            timeout=self._timeout,
        )
        if response.status_code not in {200, 201}:
            raise CloudSyncError(
                "cloud document save failed",
                failure_code=_response_failure_code(response.status_code),
            )
        try:
            rows = response.json()
        except ValueError as error:
            raise CloudSyncError("cloud document save returned invalid JSON") from error
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise CloudSyncError("cloud document save response is invalid")
        saved = rows[0]
        return CloudDocument(
            account_id=str(saved["account_id"]),
            document_type=str(saved["document_type"]),
            document_key=str(saved["document_key"]),
            revision=int(saved["revision"]),
            payload=dict(saved["payload"]),
            payload_sha256=str(saved["payload_sha256"]),
            source_device=str(saved["source_device"]),
            updated_at=str(saved["updated_at"]) if saved.get("updated_at") is not None else None,
        )

    @staticmethod
    def _validate_identity(account_id: str, document_type: str, document_key: str) -> None:
        if not account_id or len(account_id) > 160:
            raise ValueError("invalid cloud account id")
        if document_type not in DOCUMENT_TYPES:
            raise ValueError("invalid cloud document type")
        if not document_key or len(document_key) > 160:
            raise ValueError("invalid cloud document key")


def cloud_store_from_settings(settings: Mapping[str, Any]) -> SupabaseCloudDocumentStore | None:
    """Return no store until both Render cloud settings are explicitly configured."""
    url = settings.get("SUPABASE_URL")
    key = settings.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url and not key:
        return None
    if not url or not key:
        raise CloudSyncError("incomplete Supabase configuration")
    return SupabaseCloudDocumentStore(str(url), str(key))
