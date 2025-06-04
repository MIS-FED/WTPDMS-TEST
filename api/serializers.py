from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.db import connection
from.models import *
class OCRSerializer(serializers.Serializer):
    image = serializers.ImageField()
    
class UserRegistrationSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = User
        fields = ['username', 'password']
        
 
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user
    
class LoginSerializer(serializers.Serializer):
        
    username = serializers.CharField(required=True, max_length=100)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            raise serializers.ValidationError("Username and password are required.")
        try:    
            user = User.objects.get(user_code=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("User doesn't exist.")
        with connection.cursor() as cursor:
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