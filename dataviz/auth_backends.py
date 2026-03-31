from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailModelBackend(ModelBackend):
    """Authenticate users with email address for site login flows."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get("email") or username
        if email is None or password is None:
            return None

        user_model = get_user_model()

        try:
            user = user_model._default_manager.get(email__iexact=email)
        except user_model.DoesNotExist:
            user_model().set_password(password)
            return None
        except user_model.MultipleObjectsReturned:
            user = user_model._default_manager.filter(email__iexact=email).order_by("id").first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
