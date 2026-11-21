from rest_framework.permissions import SAFE_METHODS, BasePermission


def can_modify(user, record):
    """True if `user` may rename, replace or delete `record`.

    Only the uploader or an admin (is_staff). Files whose uploader was deleted
    (uploaded_by is None) can only be changed by admins.
    """
    if not user.is_authenticated:
        return False
    return user.is_staff or record.uploaded_by_id == user.id


class IsOwnerOrAdmin(BasePermission):
    """Everyone logged in can read every file; only owner/admin can change it."""

    message = "Only the uploader or an admin can change or delete this file."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:  # GET, HEAD, OPTIONS
            return True
        return can_modify(request.user, obj)
