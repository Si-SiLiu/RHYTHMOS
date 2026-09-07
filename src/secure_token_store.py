"""Encrypted-at-rest storage for service-owned OAuth token material.

The desktop workflow stays compatible with its existing JSON token file unless
``POLAR_TOKEN_ENCRYPTION_KEY`` is configured.  The deployed service configures
that key and therefore never persists a readable OAuth access or refresh token
on its disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class TokenStoreError(RuntimeError):
    """A safe error for invalid or unavailable token storage."""


class JsonTokenStore:
    """Compatibility store for the existing local-only desktop workflow."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise TokenStoreError(f"Missing token store: {self.path}")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise TokenStoreError("Token store is not valid JSON") from error
        if not isinstance(value, dict):
            raise TokenStoreError("Token store must contain a JSON object")
        return value

    def save(self, value: dict[str, Any]) -> None:
        _atomic_write(self.path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


class EncryptedTokenStore:
    """A Fernet-encrypted JSON token store for the HTTPS service."""

    def __init__(self, path: Path | str, encryption_key: str | bytes):
        self.path = Path(path)
        try:
            self.fernet = Fernet(encryption_key.encode("utf-8") if isinstance(encryption_key, str) else encryption_key)
        except (TypeError, ValueError) as error:
            raise TokenStoreError("POLAR_TOKEN_ENCRYPTION_KEY is invalid") from error

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise TokenStoreError(f"Missing token store: {self.path}")
        try:
            plaintext = self.fernet.decrypt(self.path.read_bytes())
            value = json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TokenStoreError("Encrypted token store cannot be read") from error
        if not isinstance(value, dict):
            raise TokenStoreError("Encrypted token store must contain a JSON object")
        return value

    def save(self, value: dict[str, Any]) -> None:
        plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _atomic_write(self.path, self.fernet.encrypt(plaintext))


def token_store_for(path: Path | str, encryption_key: str | None = None) -> JsonTokenStore | EncryptedTokenStore:
    """Choose encrypted storage only when the deploy-time key is present."""
    key = encryption_key if encryption_key is not None else os.getenv("POLAR_TOKEN_ENCRYPTION_KEY")
    return EncryptedTokenStore(path, key) if key else JsonTokenStore(path)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
