from django.core.management.base import BaseCommand
from api.models import User
from django.contrib.auth.hashers import make_password

class Command(BaseCommand):
    help = "Hashes all plaintext passwords in the database"

    def handle(self, *args, **kwargs):
        users = User.objects.using('sys_user').all()

        for user in users:
            if not user.password.startswith("tite6$"):  # Check if already hashed
                user.password = make_password(user.password)
                user.save(using='sys_user')

        self.stdout.write(self.style.SUCCESS("All user passwords have been hashed successfully!"))
