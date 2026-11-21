from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Public view of a user. Never includes the password hash."""

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff"]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    """
    Input for sign-up. Only these four fields are read; anything else in the
    request (is_staff, is_superuser, ...) is ignored, so nobody can register
    themselves as an admin.
    """

    # Same rules as Django's own User.username: letters, digits and @/./+/-/_ only.
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        # Run Django's AUTH_PASSWORD_VALIDATORS (length, common, numeric, similarity).
        # An unsaved User lets the similarity check compare against username/email.
        candidate = User(username=data["username"], email=data["email"])
        try:
            validate_password(data["password"], user=candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)})

        return data

    def create(self, validated_data):
        # create_user hashes the password and leaves is_staff/is_superuser False.
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
