import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from src.secure_token_store import EncryptedTokenStore, TokenStoreError


class EncryptedTokenStoreTests(unittest.TestCase):
    def test_round_trip_does_not_write_readable_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "polar_tokens.enc"
            store = EncryptedTokenStore(path, Fernet.generate_key())
            store.save({"access_token": "sensitive-access-token", "refresh_token": "refresh"})

            self.assertEqual(store.load()["access_token"], "sensitive-access-token")
            self.assertNotIn(b"sensitive-access-token", path.read_bytes())

    def test_wrong_key_cannot_read_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "polar_tokens.enc"
            EncryptedTokenStore(path, Fernet.generate_key()).save({"access_token": "token"})

            with self.assertRaises(TokenStoreError):
                EncryptedTokenStore(path, Fernet.generate_key()).load()


if __name__ == "__main__":
    unittest.main()
