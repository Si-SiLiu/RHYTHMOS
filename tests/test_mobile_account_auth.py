import base64
import json
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from src.mobile_account_auth import AppleIdentityTokenVerifier, MobileAccountAuthError


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class AppleIdentityTokenVerifierTests(unittest.TestCase):
    def setUp(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = self.private_key.public_key().public_numbers()
        self.jwks = {"keys": [{
            "kid": "test-kid", "kty": "EC", "crv": "P-256",
            "x": _b64(numbers.x.to_bytes(32, "big")),
            "y": _b64(numbers.y.to_bytes(32, "big")),
        }]}
        self.verifier = AppleIdentityTokenVerifier(
            "com.rhythmos.ios",
            http_get=lambda *_args, **_kwargs: _Response(self.jwks),
            now=lambda: 1_000,
        )

    def token(self, *, nonce="nonce-value-123456", audience="com.rhythmos.ios"):
        header = _b64(json.dumps({"alg": "ES256", "kid": "test-kid"}).encode())
        claims = _b64(json.dumps({
            "iss": "https://appleid.apple.com", "aud": audience, "exp": 2_000,
            "nonce": nonce, "sub": "apple-owner-subject",
        }).encode())
        signature_der = self.private_key.sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(signature_der)
        signature = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"{header}.{claims}.{signature}"

    def test_valid_apple_es256_token_is_verified(self):
        self.assertEqual(
            self.verifier.verify(self.token(), "nonce-value-123456"),
            "apple-owner-subject",
        )

    def test_nonce_and_audience_are_not_optional(self):
        with self.assertRaises(MobileAccountAuthError):
            self.verifier.verify(self.token(), "different-nonce-value")
        with self.assertRaises(MobileAccountAuthError):
            self.verifier.verify(self.token(audience="another.bundle"), "nonce-value-123456")
