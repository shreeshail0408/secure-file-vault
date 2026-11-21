"""
Builds the admin export ZIP: every .enc file (still encrypted) + manifest.json
+ README.txt.

- Nothing is decrypted. The manifest's sha256 values were saved at upload time.
- The ZIP is written to an anonymous temp file, one .enc at a time, streamed
  from disk in small chunks. So memory use stays small no matter how many files
  there are, and the temp file only ever holds ciphertext.
- ZIP_STORED (no compression): encrypted data looks random and doesn't shrink.
- The FERNET_KEY is never written. The key has to reach the mentor separately.
"""

import json
import logging
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

README = """\
Secure File Vault - encrypted export
====================================

Exported: {exported_at}
Files:    {file_count}

This archive contains:
  *.enc          the stored files, still encrypted with Fernet (AES-128 + HMAC-SHA256)
  manifest.json  for each .enc file: original_name, mime_type, size, and the
                 sha256 of the ORIGINAL file, so you can check that decryption is exact
  README.txt     this file

The encryption key (FERNET_KEY) is NOT in this archive. Get it from the vault
administrator through a separate, secure channel.

How to decrypt everything
-------------------------
1. Unzip this archive into a folder, e.g. vault-export/
2. Install the only dependency:   pip install cryptography
3. Put the key in an environment variable, so it doesn't appear on the
   command line or in the process list:

       export FERNET_KEY='<the key>'

4. Run:

       python decrypt_tool.py --input vault-export/ --output decrypted/

   decrypt_tool.py reads manifest.json, restores each file's original name,
   and checks every file against its sha256.

Decrypting a single file
------------------------
       python decrypt_tool.py --input vault-export/<name>.enc --output report.pdf

Checking a file by hand
-----------------------
       sha256sum decrypted/report.pdf    # must equal "sha256" in manifest.json

A wrong key or a modified .enc file is reported as an error; it never produces
a silently corrupted file.
"""


def build_export_zip(records):
    """Write the export ZIP for `records` into a temp file and return it.

    The returned file is open and positioned at the start; closing it deletes it.
    """
    exported_at = timezone.now().isoformat(timespec="seconds")
    storage_dir = Path(settings.STORAGE_DIR)
    manifest = {"exported_at": exported_at, "files": [], "missing": []}

    # TemporaryFile has no name on disk (Linux) and is deleted when closed.
    zip_file = tempfile.TemporaryFile(suffix=".zip")
    try:
        with zipfile.ZipFile(zip_file, "w", compression=zipfile.ZIP_STORED) as archive:
            for record in records:
                enc_path = storage_dir / record.stored_name
                if not enc_path.exists():
                    logger.warning("Export: .enc missing for file id=%s", record.pk)
                    manifest["missing"].append(record.original_name)
                    continue

                archive.write(enc_path, arcname=record.stored_name)  # streams in chunks
                manifest["files"].append({
                    "stored_name": record.stored_name,
                    "original_name": record.original_name,
                    "mime_type": record.mime_type,
                    "size": record.size,
                    "sha256": record.sha256,
                })

            manifest["file_count"] = len(manifest["files"])
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            archive.writestr(
                "README.txt",
                README.format(exported_at=exported_at, file_count=manifest["file_count"]),
            )
    except BaseException:
        zip_file.close()
        raise

    zip_file.seek(0)
    return zip_file


def export_filename():
    return f"vault-export-{timezone.now():%Y-%m-%d}.zip"
