# backend/users/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.conf import settings
import requests
from .serializers import UserSerializer, AdminUserSerializer, CustomTokenObtainPairSerializer

User = get_user_model()

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            
            if response.status_code == 200:
                user = User.objects.get(email=request.data['email'])
                refresh = RefreshToken.for_user(user)
                
                refresh['is_admin'] = user.is_admin
                refresh['email'] = user.email
                
                response.data.update({
                    'user': AdminUserSerializer(user).data if user.is_admin else UserSerializer(user).data,
                    'permissions': list(user.get_all_permissions()),
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                })
                
                response['Authorization'] = f'Bearer {response.data["access"]}'
                
            return response
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': 'Invalid credentials or server error'},
                status=status.HTTP_401_UNAUTHORIZED
            )

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            serializer = AdminUserSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()
                refresh = RefreshToken.for_user(user)
                return Response({
                    'user': UserSerializer(user).data,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class GoogleLoginView(APIView):
    permission_classes = []  # Allow unauthorized access
    authentication_classes = []  # No authentication required

    def post(self, request):
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'error': 'No token provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Verify token with Google
            google_response = requests.get(
                'https://www.googleapis.com/oauth2/v3/tokeninfo',
                params={'id_token': token}
            )
            
            if not google_response.ok:
                return Response(
                    {'error': 'Invalid token'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            google_data = google_response.json()

            # Verify that the token was issued for our application
            if google_data['aud'] != settings.GOOGLE_CLIENT_ID:
                return Response(
                    {'error': 'Token not issued for this application'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get or create user
            try:
                user = User.objects.get(email=google_data['email'])
            except User.DoesNotExist:
                # Create new user as a general user (not admin)
                user = User.objects.create_user(
                    username=google_data['email'],
                    email=google_data['email'],
                    first_name=google_data.get('given_name', ''),
                    last_name=google_data.get('family_name', ''),
                    is_admin=False  # Ensure user is created as general user
                )

            # Generate JWT token
            refresh = RefreshToken.for_user(user)
            
            # Add custom claims
            refresh['is_admin'] = user.is_admin
            refresh['email'] = user.email

            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })

        except requests.RequestException:
            return Response(
                {'error': 'Failed to verify token with Google'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )