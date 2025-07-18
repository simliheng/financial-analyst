# backend/users/serializers.py

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'password', 'permissions')
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def get_permissions(self, obj):
        return list(obj.get_all_permissions())

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class AdminUserSerializer(UserSerializer):
    """Serializer for admin users with additional fields"""
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('is_admin',)
        extra_kwargs = {
            **UserSerializer.Meta.extra_kwargs,
            'is_admin': {'read_only': True}
        }

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data