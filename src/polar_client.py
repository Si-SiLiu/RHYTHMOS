import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

try:
    from .secure_token_store import TokenStoreError, token_store_for
except ImportError:
    from secure_token_store import TokenStoreError, token_store_for


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
TOKEN_FILE = Path(os.getenv("POLAR_TOKEN_FILE", DATA_DIR / "polar_tokens.json"))
USER_FILE = DATA_DIR / "polar_user.json"
API_BASE_URL = "https://www.polaraccesslink.com/v3"
API_V4_BASE_URL = "https://www.polaraccesslink.com/v4/data"
TOKEN_URL = "https://auth.polar.com/oauth/token"
TOKEN_REFRESH_TIMEOUT_SECONDS = 120
CLIENT_ID = os.getenv("POLAR_CLIENT_ID")
CLIENT_SECRET = os.getenv("POLAR_CLIENT_SECRET")
MEMBER_ID = os.getenv("POLAR_MEMBER_ID", "daily-recovery-coach-local")
GET_RETRY_ATTEMPTS = 3
GET_RETRY_BACKOFF_SECONDS = 0.5
RETRYABLE_GET_STATUS_CODES = {429, 500, 502, 503, 504}


class PolarClientError(RuntimeError):
    pass


class PolarTokenExpired(PolarClientError):
    pass


class PolarTokenRefreshError(PolarClientError):
    pass


class PolarAPIError(PolarClientError):
    def __init__(self, path, status_code, body):
        self.path = path
        self.status_code = status_code
        self.body = body
        super().__init__(f"Polar API request failed: {path} HTTP {status_code}")


def load_json_file(path):
    if not path.exists():
        raise PolarClientError(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_file(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_raw_json(name, data):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def safe_error_payload(exc):
    payload = {
        "ok": False,
        "path": exc.path,
        "status_code": exc.status_code,
    }
    if exc.body:
        payload["body"] = exc.body
    return payload


def as_v4_datetime(value, end_of_day=False):
    if not value:
        return None
    text = str(value)
    if "T" in text:
        return text
    suffix = "T23:59:59" if end_of_day else "T00:00:00"
    return text + suffix


def as_v4_date(value):
    if not value:
        return None
    return str(value)[:10]


class PolarClient:
    def __init__(
        self,
        token_file=TOKEN_FILE,
        api_base_url=API_BASE_URL,
        api_v4_base_url=API_V4_BASE_URL,
        session=None,
        token_store=None,
    ):
        self.token_file = Path(token_file)
        self.api_base_url = api_base_url.rstrip("/")
        self.api_v4_base_url = api_v4_base_url.rstrip("/")
        self.token_store = token_store or token_store_for(self.token_file)
        try:
            self.tokens = self.token_store.load()
        except TokenStoreError as error:
            raise PolarClientError(str(error)) from error
        self.session = session or requests.Session()

        if not self.tokens.get("access_token"):
            raise PolarClientError("polar_tokens.json does not contain access_token")

    @property
    def expires_at(self):
        value = self.tokens.get("expires_at")
        return int(value) if value is not None else 0

    def is_token_expired(self, leeway_seconds=60):
        return self.expires_at <= int(time.time()) + leeway_seconds

    def require_valid_token(self):
        if self.is_token_expired():
            self.refresh_access_token()

    def refresh_access_token(self):
        refresh_token = self.tokens.get("refresh_token")
        if not refresh_token:
            raise PolarTokenExpired(
                "Polar access token is expired and polar_tokens.json has no refresh_token. Please re-run OAuth."
            )
        if not CLIENT_ID or not CLIENT_SECRET:
            raise PolarTokenRefreshError(
                "Missing POLAR_CLIENT_ID or POLAR_CLIENT_SECRET in .env; cannot refresh Polar token."
            )

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=TOKEN_REFRESH_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise PolarTokenRefreshError(
                f"Polar token refresh failed: HTTP {response.status_code} {response.text[:300]}"
            )

        refreshed = response.json()
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        refreshed["expires_at"] = int(time.time()) + int(refreshed.get("expires_in", 0)) - 60
        self.tokens.update(refreshed)
        try:
            self.token_store.save(self.tokens)
        except TokenStoreError as error:
            raise PolarTokenRefreshError("Unable to persist refreshed Polar credentials.") from error
        return self.tokens

    def bearer_headers(self):
        return {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Accept": "application/json",
        }

    def build_url(self, path):
        parsed = urlparse(path)
        if parsed.scheme and parsed.netloc:
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.api_base_url + path

    def build_v4_url(self, path):
        parsed = urlparse(path)
        if parsed.scheme and parsed.netloc:
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.api_v4_base_url + path

    def _get_with_retry(self, url, *, headers, params=None):
        """Retry idempotent reads after transient TLS/network or server failures."""
        for attempt in range(GET_RETRY_ATTEMPTS):
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=30,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if attempt + 1 >= GET_RETRY_ATTEMPTS:
                    raise
            else:
                if (
                    response.status_code not in RETRYABLE_GET_STATUS_CODES
                    or attempt + 1 >= GET_RETRY_ATTEMPTS
                ):
                    return response
            time.sleep(GET_RETRY_BACKOFF_SECONDS * (2 ** attempt))
        raise PolarClientError("Polar GET retry loop ended unexpectedly")

    def get(self, path, params=None):
        self.require_valid_token()
        response = self._get_with_retry(
            self.build_url(path),
            headers=self.bearer_headers(),
            params=params,
        )

        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            raise PolarAPIError(path, response.status_code, response.text[:500])

        if not response.text.strip():
            return None

        return response.json()

    def get_v4(self, path, params=None):
        self.require_valid_token()
        response = self._get_with_retry(
            self.build_v4_url(path),
            headers=self.bearer_headers(),
            params=params,
        )

        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            raise PolarAPIError(path, response.status_code, response.text[:500])

        if not response.text.strip():
            return None

        return response.json()

    def post(self, path, json_body=None):
        self.require_valid_token()
        response = self.session.post(
            self.build_url(path),
            headers={
                **self.bearer_headers(),
                "Content-Type": "application/json",
            },
            json=json_body,
            timeout=30,
        )
        if response.status_code == 204:
            return None
        if response.status_code >= 400:
            raise PolarAPIError(path, response.status_code, response.text[:500])
        if not response.text.strip():
            return None
        return response.json()

    def get_saved_user_id(self):
        for key in ("x_user_id", "polar-user-id", "polar_user_id"):
            if self.tokens.get(key):
                return self.tokens[key]

        if USER_FILE.exists():
            user = load_json_file(USER_FILE)
            for key in ("polar-user-id", "polar_user_id", "x_user_id"):
                if user.get(key):
                    return user[key]

        return None

    def get_user_account_info(self):
        user_id = self.get_saved_user_id()
        if user_id:
            return self.get(f"/users/{user_id}")
        return self.get("/users/physical-info")

    def register_user(self, member_id=MEMBER_ID):
        return self.post("/users", json_body={"member-id": member_id})

    def get_training_sessions_v3(self, samples=False, zones=False, route=False):
        return self.get(
            "/exercises",
            params={
                "samples": str(samples).lower(),
                "zones": str(zones).lower(),
                "route": str(route).lower(),
            },
        )

    def get_training_sessions(self, from_date=None, to_date=None):
        params = {}
        if from_date:
            params["from"] = as_v4_datetime(from_date)
        if to_date:
            params["to"] = as_v4_datetime(to_date, end_of_day=True)
        return self.get_v4("/training-sessions/list", params=params or None)

    def get_sports(self):
        """Return the Dynamic API sport catalog used to resolve numeric sport IDs."""
        return self.get_v4("/sports/list")

    def get_daily_activity_v3(
        self,
        from_date=None,
        to_date=None,
        steps=False,
        activity_zones=False,
        inactivity_stamps=False,
    ):
        params = {
            "steps": str(steps).lower(),
            "activity_zones": str(activity_zones).lower(),
            "inactivity_stamps": str(inactivity_stamps).lower(),
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self.get("/users/activities", params=params)

    def get_daily_activity(self, from_date=None, to_date=None):
        params = {}
        if from_date:
            params["from"] = as_v4_date(from_date)
        if to_date:
            params["to"] = as_v4_date(to_date)
        return self.get_v4("/activity/list", params=params or None)

    def get_sleep(self, from_date=None, to_date=None):
        params = {}
        if from_date:
            params["from"] = as_v4_date(from_date)
        if to_date:
            params["to"] = as_v4_date(to_date)
        return self.get_v4("/sleeps", params=params or None)

    def get_sleep_for_date(self, date_value):
        start = date.fromisoformat(as_v4_date(date_value))
        return self.get_v4(
            "/sleeps",
            params={
                "from": start.isoformat(),
                "to": (start + timedelta(days=1)).isoformat(),
                "features": (
                    "sleep-result",
                    "original-sleep-result",
                    "sleep-evaluation",
                    "sleep-score",
                ),
            },
        )

    def get_available_sleep(self):
        return self.get_v4("/sleeps/available")

    def get_nightly_recharge(self, from_date=None, to_date=None, samples=False):
        if samples and from_date and to_date:
            start = date.fromisoformat(as_v4_date(from_date))
            end = date.fromisoformat(as_v4_date(to_date))
            if end - start != timedelta(days=1):
                raise PolarClientError(
                    "Polar Nightly Recharge samples require an exclusive one-day date range."
                )
        params = {}
        if from_date:
            params["from"] = as_v4_date(from_date)
        if to_date:
            params["to"] = as_v4_date(to_date)
        if samples:
            params["features"] = "samples"
        return self.get_v4("/nightly-recharge-results", params=params or None)

    def get_nightly_recharge_for_date(self, date_value):
        return self.get_v4(f"/nightly-recharge-results/{date_value}")

    def get_cardio_load(self):
        return self.get_v4("/cardio-load")

    def get_cardio_load_for_date(self, date_value):
        return self.get_v4(f"/cardio-load/{date_value}")

    def get_cardio_load_range(self, from_date=None, to_date=None):
        params = {}
        if from_date:
            params["from"] = as_v4_datetime(from_date)
        if to_date:
            params["to"] = as_v4_datetime(to_date, end_of_day=True)
        return self.get_v4("/cardio-load/date", params=params or None)

    def get_continuous_heart_rate(self, date_value=None, from_date=None, to_date=None):
        if date_value:
            start = date.fromisoformat(as_v4_date(date_value))
            return self.get_v4(
                "/continuous-samples",
                params={
                    "from": start.isoformat(),
                    "to": (start + timedelta(days=1)).isoformat(),
                    "features": ("heart-rate-samples",),
                },
            )
        params = {}
        if from_date:
            params["from"] = as_v4_date(from_date)
        if to_date:
            params["to"] = as_v4_date(to_date)
        params["features"] = ("heart-rate-samples",)
        return self.get_v4("/continuous-samples", params=params or None)
