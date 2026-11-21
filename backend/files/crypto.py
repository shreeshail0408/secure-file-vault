"""
Encryption helpers. This is the ONLY module that uses Fernet directly.

Fernet = AES-128-CBC for secrecy + HMAC-SHA256 for integrity. Because of the
HMAC, a file that was modified, or encrypted with a different key, is detected
and rejected instead of decrypting to garbage.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class DecryptionError(Exception):
    """Raised when stored data can't be decrypted (tampered file or wrong key)."""


def _fernet():
    # Read the key on every call (not once at import) so tests can override it.
    return Fernet(settings.FERNET_KEY)


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt plaintext bytes and return the Fernet token (ciphertext)."""
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    """Decrypt a Fernet token. Raises DecryptionError instead of InvalidToken."""
    try:
        return _fernet().decrypt(token)
    except InvalidToken:
        # "from None" hides Fernet's internal traceback; the message says it all.
        raise DecryptionError(
            "Could not decrypt file: it was modified or encrypted with a different key."
        ) from None
