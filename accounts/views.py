from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegisterSerializer, CustomTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth import get_user_model

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data['refresh']
            token = RefreshToken(refresh_token)

            token.blacklist()

            return Response({"message": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)


class AdminManagementView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        action = request.data.get('action')
        user_id = request.data.get('user_id')

        if not action or not user_id:
            return Response("missing action or user id", status=status.HTTP_400_BAD_REQUEST)
        
        if action == 'assign_roles':
            role_id = request.data.get('role_id')

            if not role_id:
                return Response("role id is not found", status=status.HTTP_400_BAD_REQUEST)
            
            result = request.user.assign_roles(get_user_id=user_id, get_role_id=role_id)

        elif action in ['ban', 'activated']:
            result = request.user.manage_users(get_user_id=user_id, action=action)

        else:
            return Response({"error": "Invalid action string"}, status=status.HTTP_400_BAD_REQUEST)
        
        if "Permission denied" in result:
            return Response({"error" : result}, status=status.HTTP_403_FORBIDDEN)
        
        elif "not found" in result:
            return Response({"error": result}, status=status.HTTP_404_NOT_FOUND)
            
        return Response({"message": result}, status=status.HTTP_200_OK)

            
