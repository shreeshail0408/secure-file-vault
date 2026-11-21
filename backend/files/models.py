from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .storage import delete_file, save_encrypted


class FileRecord(models.Model):
    """Metadata for one encrypted file. The file itself lives in STORAGE_DIR."""

    PDF = "pdf"
    IMAGE = "image"
    FILE_TYPE_CHOICES = [(PDF, "PDF"), (IMAGE, "Image")]

    original_name = models.CharField(max_length=255)  # shown to users, renameable
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    mime_type = models.CharField(max_length=100)  # e.g. "application/pdf"
    size = models.PositiveIntegerField()  # plaintext size in bytes
    stored_name = models.CharField(max_length=255, unique=True)  # "<uuid4>.enc"
    # SHA-256 of the ORIGINAL (plaintext) bytes, saved at upload/replace time.
    # Goes into the export manifest so a decrypted copy can be checked for an
    # exact match, without the server ever decrypting during export.
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # keep files if the uploader's account is deleted
        null=True,
        blank=True,
        related_name="files",
    )
    # Set only for demo files made by `manage.py seed_files` (e.g. "invoice_2026_03.pdf").
    # Lets the command skip files it already made, even if they were renamed,
    # and lets --reset delete only seeded files. NULL for real uploads.
    seed_key = models.CharField(max_length=100, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    @classmethod
    def create_from_upload(cls, upload, owner, seed_key=None):
        """Encrypt a validated Upload, store the .enc, and create its record.

        The one place new files are created: used by the upload view and by seed_files.
        """
        stored_name = save_encrypted(upload.data)
        try:
            return cls.objects.create(
                original_name=upload.name,
                file_type=upload.file_type,
                mime_type=upload.mime_type,
                size=len(upload.data),
                sha256=upload.sha256,
                stored_name=stored_name,
                uploaded_by=owner,
                seed_key=seed_key,
            )
        except Exception:
            delete_file(stored_name)  # don't leave an orphan .enc behind
            raise


@receiver(post_delete, sender=FileRecord)
def remove_encrypted_file(sender, instance, **kwargs):
    """When a FileRecord is deleted, delete its .enc file too.

    A signal (not an overridden delete()) also covers bulk deletes like
    FileRecord.objects.all().delete(). on_commit waits until the database delete
    is really saved, so a rolled-back delete never loses the file.
    """
    stored_name = instance.stored_name
    transaction.on_commit(lambda: delete_file(stored_name))
