from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import RegisterSerializer, UserSerializer
from .throttles import AuthRateThrottle


class RegisterView(generics.GenericAPIView):
    """POST username, email, password, confirm_password -> 201 + the new user."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    # Public endpoint: don't even look at an Authorization header. Otherwise a
    # stale/expired token left in the browser would turn sign-up into a 401.
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Respond with the public serializer so the password never leaves the server.
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """POST username + password -> {"access": ..., "refresh": ...}. Throttled."""

    throttle_classes = [AuthRateThrottle]
    throttle_scope = "login"


class MeView(generics.RetrieveAPIView):
    """GET the logged-in user's id, username, email, is_staff."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
