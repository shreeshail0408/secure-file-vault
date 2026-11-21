from rest_framework.routers import SimpleRouter

from .views import FileRecordViewSet

# Creates /files/, /files/<id>/, /files/<id>/preview/, /download/, /replace/
router = SimpleRouter()
router.register("files", FileRecordViewSet, basename="file")

urlpatterns = router.urls
