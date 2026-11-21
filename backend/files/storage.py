"""
Reading and writing encrypted files in settings.STORAGE_DIR.

Rules:
- Plaintext never touches disk. We encrypt in memory first, then write.
- Stored filenames are "<uuid4 hex>.enc". User input never becomes part of a path.
- Writes are atomic: write to a temp file, then rename it into place. A crash
  mid-write leaves at most a stray *.tmp, never a half-written .enc file.
"""

import os
import re
import tempfile
import uuid
from pathlib import Path

from django.conf import settings

from .crypto import decrypt_bytes, encrypt_bytes

# Exactly 32 lowercase hex characters + ".enc" (what uuid4().hex produces).
STORED_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.enc$")


def _path_for(stored_name: str) -> Path:
    """Turn a stored name into a full path, refusing anything that isn't ours."""
    if not STORED_NAME_PATTERN.match(stored_name):
        # Blocks "../../etc/passwd", absolute paths, user-chosen names, etc.
        raise ValueError(f"Invalid stored file name: {stored_name!r}")
    return Path(settings.STORAGE_DIR) / stored_name


def save_encrypted(data: bytes) -> str:
    """Encrypt `data`, write it to a new .enc file, and return its stored name."""
    storage_dir = Path(settings.STORAGE_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}.enc"
    final_path = _path_for(stored_name)
    ciphertext = encrypt_bytes(data)  # in memory; plaintext is never written

    # The temp file is in the same folder so os.replace is a same-disk rename,
    # which the OS performs atomically.
    fd, temp_path = tempfile.mkstemp(dir=storage_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as temp_file:
            temp_file.write(ciphertext)
            temp_file.flush()
            os.fsync(temp_file.fileno())  # make sure bytes are on disk before rename
        os.replace(temp_path, final_path)
    except BaseException:
        # Clean up the partial temp file, then let the error propagate.
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return stored_name


def read_decrypted(stored_name: str) -> bytes:
    """Read a .enc file and return the decrypted bytes (in memory only).

    Raises crypto.DecryptionError if the file was tampered with or the key is wrong.
    """
    return decrypt_bytes(_path_for(stored_name).read_bytes())


def delete_file(stored_name: str) -> None:
    """Delete a .enc file. Does nothing if it is already gone."""
    _path_for(stored_name).unlink(missing_ok=True)
