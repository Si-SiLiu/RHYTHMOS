"""Account-scoped mobile sessions for the RHYTHMOS HTTPS boundary.

The service validates a Sign in with Apple identity token before issuing its
own short-lived access token.  A rotating opaque refresh secret is retained
only as a SHA-256 digest in the private cloud document store; the plaintext
refresh secret exists only in the device Keychain.
"""

from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
import re
import unicodedata
from dataclasses import dataclass
from hashlib import scrypt, sha256
from typing import Any, Callable, Mapping

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
ACCOUNT_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{2,31}")
PASSWORD_SCRYPT_N = 2**14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1


class MobileAccountAuthError(RuntimeError):
    """A stable authentication failure that never includes credential data."""


def normalize_account_name(value: object) -> str:
    """Normalize a public RHYTHMOS account name without accepting lookalikes."""
    if not isinstance(value, str):
        raise MobileAccountAuthError("invalid account name")
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    if not ACCOUNT_NAME_PATTERN.fullmatch(normalized):
        raise MobileAccountAuthError("invalid account name")
    return normalized


def account_name_digest(value: str) -> str:
    """Keep a public account name out of cloud document keys and logs."""
    return sha256(value.encode("utf-8")).hexdigest()


def password_hash(value: object, *, salt: bytes | None = None) -> str:
    """Create a parameterized scrypt password record for RHYTHMOS accounts."""
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise MobileAccountAuthError("invalid password")
    encoded = value.encode("utf-8")
    if len(encoded) > 512:
        raise MobileAccountAuthError("invalid password")
    salt = salt or secrets.token_bytes(16)
    derived = scrypt(
        encoded, salt=salt, n=PASSWORD_SCRYPT_N, r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P, dklen=32,
    )
    return "scrypt-v1${}${}".format(
        base64.urlsafe_b64encode(salt).rstrip(b"=").decode("ascii"),
        base64.urlsafe_b64encode(derived).rstrip(b"=").decode("ascii"),
    )


def password_matches(value: object, stored: object) -> bool:
    """Check a password record in constant time and reject malformed records."""
    if not isinstance(value, str) or not isinstance(stored, str):
        return False
    try:
        version, encoded_salt, expected = stored.split("$", 2)
        if version != "scrypt-v1":
            return False
        salt = _base64url_decode(encoded_salt)
        candidate = password_hash(value, salt=salt).split("$", 2)[2]
        return hmac.compare_digest(candidate, expected)
    except (MobileAccountAuthError, ValueError):
        return False


def _base64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as error:  # noqa: BLE001 - normalize untrusted JWT input
        raise MobileAccountAuthError("invalid token encoding") from error


def _json_part(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_base64url_decode(value))
    except (TypeError, ValueError) as error:
        raise MobileAccountAuthError("invalid token JSON") from error
    if not isinstance(decoded, dict):
        raise MobileAccountAuthError("invalid token JSON")
    return decoded


def _constant_time_text(left: object, right: object) -> bool:
    return isinstance(left, str) and isinstance(right, str) and hmac.compare_digest(left, right)


class AppleIdentityTokenVerifier:
    """Verify Apple's ES256 identity JWT using the current Apple JWKS."""

    def __init__(
        self,
        audience: str,
        *,
        http_get: Callable[..., requests.Response] = requests.get,
        now: Callable[[], float] = time.time,
    ):
        if not audience:
            raise ValueError("Apple audience is required")
        self._audience = audience
        self._http_get = http_get
        self._now = now

    def verify(self, identity_token: str, nonce: str) -> str:
        if not isinstance(identity_token, str) or len(identity_token) > 12_000:
            raise MobileAccountAuthError("invalid identity token")
        if not isinstance(nonce, str) or not 16 <= len(nonce) <= 256:
            raise MobileAccountAuthError("invalid nonce")
        parts = identity_token.split(".")
        if len(parts) != 3:
            raise MobileAccountAuthError("invalid identity token")
        header = _json_part(parts[0])
        claims = _json_part(parts[1])
        if header.get("alg") != "ES256" or not isinstance(header.get("kid"), str):
            raise MobileAccountAuthError("unsupported identity token")
        key = self._key_for(header["kid"])
        signature = _base64url_decode(parts[2])
        if len(signature) != 64:
            raise MobileAccountAuthError("invalid identity token signature")
        try:
            key.verify(
                encode_dss_signature(
                    int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"),
                ),
                f"{parts[0]}.{parts[1]}".encode("ascii"),
                ec.ECDSA(hashes.SHA256()),
            )
        except InvalidSignature as error:
            raise MobileAccountAuthError("invalid identity token signature") from error

        audience = claims.get("aud")
        valid_audience = self._audience in audience if isinstance(audience, list) else audience == self._audience
        expiry = claims.get("exp")
        if (
            not _constant_time_text(claims.get("iss"), APPLE_ISSUER)
            or not valid_audience
            or not isinstance(expiry, (int, float))
            or expiry <= self._now()
            or not _constant_time_text(claims.get("nonce"), nonce)
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"]
        ):
            raise MobileAccountAuthError("identity token claims are invalid")
        return claims["sub"]

    def _key_for(self, kid: str) -> ec.EllipticCurvePublicKey:
        try:
            response = self._http_get(APPLE_JWKS_URL, timeout=10)
            payload = response.json() if response.status_code == 200 else None
        except Exception as error:  # noqa: BLE001 - upstream failures are normalized
            raise MobileAccountAuthError("Apple identity service is unavailable") from error
        keys = payload.get("keys") if isinstance(payload, dict) else None
        candidate = next((key for key in keys or [] if isinstance(key, dict) and key.get("kid") == kid), None)
        if not candidate or candidate.get("kty") != "EC" or candidate.get("crv") != "P-256":
            raise MobileAccountAuthError("Apple signing key is unavailable")
        try:
            public_numbers = ec.EllipticCurvePublicNumbers(
                int.from_bytes(_base64url_decode(str(candidate["x"])), "big"),
                int.from_bytes(_base64url_decode(str(candidate["y"])), "big"),
                ec.SECP256R1(),
            )
            return public_numbers.public_key()
        except (KeyError, ValueError) as error:
            raise MobileAccountAuthError("Apple signing key is invalid") from error


@dataclass(frozen=True)
class MobileSession:
    access_token: str
    refresh_token: str
    expires_at: int
    account_id: str


class MobileSessionIssuer:
    """Issue and verify compact HS256 access JWTs without third-party JWT code."""

    def __init__(self, signing_key: str, *, now: Callable[[], float] = time.time, access_lifetime_seconds: int = 3600):
        if len(signing_key.encode("utf-8")) < 32:
            raise ValueError("session signing key must be at least 32 bytes")
        self._key = signing_key.encode("utf-8")
        self._now = now
        self._lifetime = access_lifetime_seconds

    def issue(self, account_id: str, device_id: str, session_id: str | None = None) -> MobileSession:
        if not account_id or not device_id:
            raise ValueError("account and device are required")
        issued_at = int(self._now())
        expires_at = issued_at + self._lifetime
        session_id = session_id or secrets.token_urlsafe(18)
        header = self._encode_json({"alg": "HS256", "typ": "JWT"})
        claims = self._encode_json({
            "iss": "rhythmos.mobile", "sub": account_id, "sid": session_id,
            "did": device_id, "iat": issued_at, "exp": expires_at,
        })
        signature = self._sign(f"{header}.{claims}".encode("ascii"))
        refresh_secret = secrets.token_urlsafe(40)
        return MobileSession(
            access_token=f"{header}.{claims}.{signature}",
            refresh_token=f"{session_id}.{refresh_secret}",
            expires_at=expires_at,
            account_id=account_id,
        )

    def verify_access_token(self, token: str) -> tuple[str, str]:
        if not isinstance(token, str) or len(token) > 4_096:
            raise MobileAccountAuthError("invalid session")
        parts = token.split(".")
        if len(parts) != 3 or not hmac.compare_digest(parts[2], self._sign(f"{parts[0]}.{parts[1]}".encode("ascii"))):
            raise MobileAccountAuthError("invalid session")
        header = _json_part(parts[0])
        claims = _json_part(parts[1])
        if header.get("alg") != "HS256" or claims.get("iss") != "rhythmos.mobile":
            raise MobileAccountAuthError("invalid session")
        if not isinstance(claims.get("exp"), int) or claims["exp"] <= int(self._now()):
            raise MobileAccountAuthError("session expired")
        if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("did"), str):
            raise MobileAccountAuthError("invalid session")
        return claims["sub"], claims["did"]

    @staticmethod
    def refresh_digest(refresh_token: str) -> str:
        return sha256(refresh_token.encode("utf-8")).hexdigest()

    @staticmethod
    def split_refresh_token(value: str) -> tuple[str, str]:
        session_id, separator, secret = value.partition(".")
        if not separator or not session_id or not secret or len(value) > 512:
            raise MobileAccountAuthError("invalid refresh session")
        return session_id, secret

    def _encode_json(self, payload: Mapping[str, Any]) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=").decode("ascii")

    def _sign(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(hmac.new(self._key, value, sha256).digest()).rstrip(b"=").decode("ascii")
