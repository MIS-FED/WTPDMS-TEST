import os
import django

# Set up Django settings before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DjangoBackend.settings")
django.setup()

from django.contrib.auth.hashers import make_password, check_password
from api.models import User

def hash_existing_passwords():
    users = User.objects.all()
    updated_count = 0

    for user in users:
        if len(user.password) == 64 and all(c in "0123456789abcdef" for c in user.password.lower()):
            print(f"Skipping {user.user_code}: Already hashed.")
            continue  # Already hashed, skip

        try:
            if not check_password(user.password, user.password):  # Detect plaintext
                hashed_password = make_password(user.password)  # Hash password
                user.password = hashed_password
                user.save(update_fields=["password"])
                updated_count += 1
                print(f"Hashed password for {user.user_code}")
        except Exception as e:
            print(f"Error processing {user.user_code}: {e}")

    print(f"\n🔹 Completed! {updated_count} passwords hashed.")

if __name__ == "__main__":
    hash_existing_passwords()
