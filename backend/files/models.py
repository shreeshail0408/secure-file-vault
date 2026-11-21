from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .storage import delete_file


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
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # keep files if the uploader's account is deleted
        null=True,
        blank=True,
        related_name="files",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name


@receiver(post_delete, sender=FileRecord)
def remove_encrypted_file(sender, instance, **kwargs):
    """When a FileRecord is deleted, delete its .enc file too.

    A signal (not an overridden delete()) also covers bulk deletes like
    FileRecord.objects.all().delete(). on_commit waits until the database delete
    is really saved, so a rolled-back delete never loses the file.
    """
    stored_name = instance.stored_name
    transaction.on_commit(lambda: delete_file(stored_name))
