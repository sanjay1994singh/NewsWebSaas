from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from subscriptions.models import CustomerAcquisition


def _digits(value):
    return ''.join(char for char in str(value or '') if char.isdigit())


class IdentifierBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get(get_user_model().USERNAME_FIELD) or '').strip()
        if not identifier or password is None:
            return None

        User = get_user_model()
        candidates = list(User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).order_by('id'))
        digits = _digits(identifier)
        if digits:
            for acquisition in CustomerAcquisition.objects.select_related('user').filter(mobile__icontains=digits[-10:]).order_by('id'):
                if _digits(acquisition.mobile).endswith(digits[-10:]) and acquisition.user not in candidates:
                    candidates.append(acquisition.user)

        for user in candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None
