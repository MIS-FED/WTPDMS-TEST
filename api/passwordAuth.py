from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import get_user_model
from django.db import connections

class MultiDBJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        User = get_user_model()
        user_id = validated_token.get('user_id')
        
        if not user_id:
            return None

        # Try both databases
        for db_alias in ['default', 'tsl_db']:
            try:
                user = User.objects.using(db_alias).get(pk=user_id)
                return user
            except User.DoesNotExist:
                continue
        
        return None