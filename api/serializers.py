from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.db import connection, connections
from django.contrib.auth import get_user_model
from.models import *
class OCRSerializer(serializers.Serializer):
    image = serializers.ImageField()
    
User = get_user_model()
class LoginSerializer(serializers.Serializer):
        
    username = serializers.CharField(required=True, max_length=100)
    password = serializers.CharField(required=True, write_only=True)
    def __init__(self, *args, **kwargs):
        self.db_alias = kwargs.pop('db_alias', 'default')  # Default to 'default' if not provided
        super().__init__(*args, **kwargs)

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            raise serializers.ValidationError("Username and password are required.")
        try:    
            user = User.objects.using(self.db_alias).get(user_code=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("User doesn't exist.")
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute("SELECT dbo.fn_decrypt_pb(%s) AS decrypted_password", [user.password])
            row = cursor.fetchone()
            decrypted_password = row[0]   
       # if not check_password(password, user.password):
        if password != decrypted_password:
            raise serializers.ValidationError('Password is incorrect.')  # Incorrect password
        data['user'] = user
        return data

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'
        

class TripTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripTicketModel
        fields = '__all__'
        
class TripDriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripDriverModel
        fields = '__all__'

class TripDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripDetailsModel
        fields = '__all__'
        
class TripBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripBranchModel
        fields = '__all__'
        
class OutslipImagesSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutslipImagesModel
        fields = '__all__'
        
class OutslipItemQtySerializer(serializers.ModelSerializer):
    class Meta:
        model = OutslipItemQtyModel
        fields = '__all__'

class CustomerMFSerializer(serializers.ModelSerializer):
    class Meta:
        model= TripCustomerModel    
        fields = '__all__'
class ItemMFSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemMFModel
        fields = '__all__'

class UOMMFSerializer(serializers.ModelSerializer):
    class Meta:
        model = UOMMFModel
        fields = '__all__'
          
class BranchLogsSerializer(serializers.ModelSerializer):
    branch_details = TripBranchSerializer(source='branch', read_only=True)
    class Meta:
        model = TripTicketBranchLogsModel
        fields = '__all__'
        
class TripTicketDetailReceivingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripTicketDetailReceivingModel
        fields = '__all__'

class InventoryCountRowManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryCountRowManagerModel
        fields = '__all__'
        
class ItemFullCountScanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFullCountScanModel
        fields = '__all__'

class LayerMFSerializer(serializers.ModelSerializer):
    class Meta:
        model = LayerMFModel
        fields = '__all__'

class SerialFullCountScanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SerialFullCountScanModel
        fields = '__all__'