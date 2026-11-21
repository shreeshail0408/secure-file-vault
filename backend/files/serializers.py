from rest_framework import serializers

from .models import FileRecord
from .permissions import can_modify


class FileRecordSerializer(serializers.ModelSerializer):
    """What the API shows about a file.

    stored_name is deliberately NOT included: the name of the .enc file on
    disk is an internal detail and never leaves the server.
    """

    uploaded_by = serializers.CharField(source="uploaded_by.username", read_only=True, default=None)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = FileRecord
        fields = [
            "id", "original_name", "file_type", "mime_type", "size",
            "uploaded_by", "can_edit", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_can_edit(self, record):
        # Same rule as IsOwnerOrAdmin, so the frontend can hide buttons.
        return can_modify(self.context["request"].user, record)


class RenameSerializer(serializers.Serializer):
    original_name = serializers.CharField()
