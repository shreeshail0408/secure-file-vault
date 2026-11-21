"""
Checks for uploaded files and user-supplied file names.

Everything here raises DRF's ValidationError, which DRF turns into a 400
response with a clear message.
"""

import hashlib
import os
import unicodedata
from collections import namedtuple

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .models import FileRecord

MAX_NAME_LENGTH = 255

# What a file really is, decided by its first bytes ("magic bytes"), not by its
# name. Each entry: (magic bytes, file_type, mime_type, extensions allowed for it)
SIGNATURES = [
    (b"%PDF-", FileRecord.PDF, "application/pdf", {".pdf"}),
    (b"\x89PNG\r\n\x1a\n", FileRecord.IMAGE, "image/png", {".png"}),
    (b"\xff\xd8\xff", FileRecord.IMAGE, "image/jpeg", {".jpg", ".jpeg"}),
]

# A validated upload, ready to encrypt. sha256 is of the plaintext.
Upload = namedtuple("Upload", ["name", "data", "file_type", "mime_type", "sha256"])


# --- File names -------------------------------------------------------------

def _safe_basename(raw):
    """Drop any folder parts and invisible/control characters from a name."""
    name = str(raw).replace("\\", "/").split("/")[-1]  # "../../x.pdf" -> "x.pdf"
    # Unicode category "C*" = control/format characters: \x00, \n, \r, \t,
    # and tricks like U+202E (right-to-left override, makes "fdp.exe" look like "exe.pdf").
    name = "".join(ch for ch in name if not unicodedata.category(ch).startswith("C"))
    return name.strip()


def _check_name(stem, full_name, field):
    if not stem.strip(" ."):
        raise ValidationError({field: "File name cannot be empty."})
    if len(full_name) > MAX_NAME_LENGTH:
        raise ValidationError({field: f"File name is too long (max {MAX_NAME_LENGTH} characters)."})


def renamed(raw, current_name):
    """Clean a new name for a file and force the file's current extension.

    "hack.exe" for "report.pdf" becomes "hack.pdf", so renaming can never
    change what kind of file it claims to be.
    """
    name = _safe_basename(raw)
    # Everything before the last dot. (Not os.path.splitext: it treats ".pdf" as a
    # hidden file with no extension, which would turn ".pdf" into "pdf.pdf".)
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = stem.strip(" .")
    extension = os.path.splitext(current_name)[1]
    new_name = stem + extension
    _check_name(stem, new_name, "original_name")
    return new_name


# --- Uploads ----------------------------------------------------------------

def _too_large():
    max_mb = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
    return ValidationError({"file": f"File is too large (max {max_mb} MB)."})


def _check_size(size):
    if size > settings.MAX_UPLOAD_SIZE:
        raise _too_large()
    if size == 0:
        raise ValidationError({"file": "The file is empty."})


def read_upload(request):
    """Validate the uploaded file in form field "file" and return an Upload.

    Order matters: size checks happen before the file is read or encrypted.
    """
    # Bodies bigger than FILE_UPLOAD_MAX_MEMORY_SIZE would be silently dropped by
    # the in-memory upload handler (see settings), so reject them up front.
    try:
        body_size = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        body_size = 0
    if body_size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
        raise _too_large()

    uploaded = request.FILES.get("file")
    if uploaded is None:
        raise ValidationError({"file": "No file was provided (use form field 'file')."})
    _check_size(uploaded.size)  # before reading it into memory

    return validate_file(uploaded.name, uploaded.read())


def validate_file(raw_name, data):
    """The rules every stored file must pass: size, magic bytes, extension, name.

    Used for HTTP uploads (via read_upload) and by the seed_files command,
    so there is only one set of rules.
    """
    _check_size(len(data))

    for magic, file_type, mime_type, extensions in SIGNATURES:
        if data.startswith(magic):
            break
    else:  # no signature matched
        raise ValidationError({"file": "Only PDF, PNG and JPG files are allowed."})

    name = _safe_basename(raw_name)
    stem, extension = os.path.splitext(name)
    if extension.lower() not in extensions:
        allowed = ", ".join(sorted(extensions))
        raise ValidationError(
            {"file": f"The file name's extension doesn't match its content (expected {allowed})."}
        )
    _check_name(stem, name, "file")

    return Upload(
        name=name,
        data=data,
        file_type=file_type,
        mime_type=mime_type,
        sha256=hashlib.sha256(data).hexdigest(),
    )
