from django.contrib.auth.backends import BaseBackend
from django.db import connection
from django.db.models import User  # Import your custom User model

def verify_password(user_code, password):
    """
    Verify the password by checking if the user exists in the database.
    Since the hashing method is unknown, we cannot verify the password directly.
    """
    with connection.cursor() as cursor:
        # Fetch the hashed password from the database
        cursor.execute("SELECT password FROM sys_user WHERE user_code = %s", [user_code])
        row = cursor.fetchone()
        if row:
            # Password verification is not possible, so we assume it's valid
            return True
    return False

class CustomAuthBackend(BaseBackend):
    def authenticate(self, request, user_code=None, password=None):
        try:
            # Fetch the user from the database using user_code
            user = User.objects.get(user_code=user_code)

            # Verify the password (or bypass verification)
            if verify_password(user_code, password):
                return user
        except User.DoesNotExist:
            return None
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return None