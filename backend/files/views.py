import logging
import os

from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils.http import content_disposition_header
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .crypto import DecryptionError
from .export import build_export_zip, export_filename
from .models import FileRecord
from .permissions import IsOwnerOrAdmin
from .serializers import FileRecordSerializer, RenameSerializer
from .storage import delete_file, read_decrypted, save_encrypted
from .validation import read_upload, renamed

logger = logging.getLogger(__name__)


class FileRecordViewSet(
    mixins.ListModelMixin,      # GET    /files/
    mixins.RetrieveModelMixin,  # GET    /files/<id>/
    mixins.DestroyModelMixin,   # DELETE /files/<id>/
    viewsets.GenericViewSet,
):
    """Upload, list, search, preview, download, rename, replace, delete.

    No `update` method on purpose: PUT /files/<id>/ is not allowed (405).
    Content changes go through PUT /files/<id>/replace/ instead.
    """

    serializer_class = FileRecordSerializer
    # IsOwnerOrAdmin runs inside get_object(), so every action that loads a
    # file by id gets 404 (no such id) or 403 (not yours) automatically.
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        files = FileRecord.objects.select_related("uploaded_by")

        search = self.request.query_params.get("search", "").strip()
        if search:
            files = files.filter(original_name__icontains=search)

        file_type = self.request.query_params.get("type", "").strip()
        if file_type:
            if file_type not in (FileRecord.PDF, FileRecord.IMAGE):
                raise ValidationError({"type": "Must be 'pdf' or 'image'."})
            files = files.filter(file_type=file_type)

        return files

    # POST /files/  (multipart, field "file")
    def create(self, request):
        upload = read_upload(request)  # 400 if too big, empty, or not a real PDF/PNG/JPG
        stored_name = save_encrypted(upload.data)
        try:
            record = FileRecord.objects.create(
                original_name=upload.name,
                file_type=upload.file_type,
                mime_type=upload.mime_type,
                size=len(upload.data),
                sha256=upload.sha256,
                stored_name=stored_name,
                uploaded_by=request.user,
            )
        except Exception:
            delete_file(stored_name)  # don't leave an orphan .enc behind
            raise
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    # PATCH /files/<id>/  {"original_name": "..."}
    def partial_update(self, request, pk=None):
        record = self.get_object()
        serializer = RenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record.original_name = renamed(serializer.validated_data["original_name"], record.original_name)
        record.save(update_fields=["original_name", "updated_at"])
        return Response(self.get_serializer(record).data)

    # PUT /files/<id>/replace/  (multipart, field "file")
    @action(detail=True, methods=["put"])
    def replace(self, request, pk=None):
        record = self.get_object()  # permission check BEFORE the upload is read
        upload = read_upload(request)
        if upload.file_type != record.file_type:
            raise ValidationError(
                {"file": f"The new file must be the same type as the old one ({record.file_type})."}
            )

        old_stored_name = record.stored_name
        new_stored_name = save_encrypted(upload.data)

        # Keep the name, but switch the extension if e.g. a PNG is replaced by a JPG,
        # so the name always matches the real content.
        stem = os.path.splitext(record.original_name)[0]
        record.original_name = stem + os.path.splitext(upload.name)[1]
        record.mime_type = upload.mime_type
        record.size = len(upload.data)
        record.sha256 = upload.sha256
        record.stored_name = new_stored_name
        try:
            record.save()
        except Exception:
            delete_file(new_stored_name)
            raise

        # Remove the old .enc only once the database change is saved.
        transaction.on_commit(lambda: delete_file(old_stored_name))
        return Response(self.get_serializer(record).data)

    # GET /files/export/  (admins only)
    # permission_classes here REPLACES the viewset's list for this action.
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsAdminUser])
    def export(self, request):
        records = FileRecord.objects.order_by("id")  # all files, ignores ?search/?type
        zip_file = build_export_zip(records)
        # FileResponse streams the temp file in chunks and closes (= deletes) it at the end.
        response = FileResponse(
            zip_file, as_attachment=True, filename=export_filename(), content_type="application/zip"
        )
        response["Cache-Control"] = "private, no-store"
        return response

    # GET /files/<id>/preview/
    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        return self._decrypted_file_response(as_attachment=False)

    # GET /files/<id>/download/
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        return self._decrypted_file_response(as_attachment=True)

    def _decrypted_file_response(self, as_attachment):
        record = self.get_object()
        try:
            data = read_decrypted(record.stored_name)
        except DecryptionError as error:
            logger.error("Decryption failed for file id=%s: %s", record.pk, error)
            return Response({"detail": str(error)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except FileNotFoundError:
            logger.error("Encrypted file missing on disk for file id=%s", record.pk)
            return Response(
                {"detail": "The stored file is missing on the server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(data, content_type=record.mime_type)
        # Django's helper escapes quotes and switches to the RFC 5987 form
        # filename*=utf-8''... for non-ASCII or control characters (e.g. newlines),
        # so a file name can never break or inject HTTP headers.
        response["Content-Disposition"] = content_disposition_header(as_attachment, record.original_name)
        response["Content-Length"] = len(data)
        # Decrypted content must not be stored by browsers or proxies.
        response["Cache-Control"] = "private, no-store"
        return response
