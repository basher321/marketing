"""Encryption helpers for secrets (e.g. stored integration credentials)."""
import base64

from cryptography.fernet import Fernet

from app.config import get_settings

settings = get_settings()


def _fernet() -> Fernet:
    # Derive a 32-byte urlsafe base64 key from ENCRYPTION_KEY for local/dev use.
    key_bytes = settings.ENCRYPTION_KEY.get_secret_value().encode("utf-8").ljust(32, b"0")[:32]
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
