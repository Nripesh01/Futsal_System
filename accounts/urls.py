from django.urls import path

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import RegisterView, LogoutView, LoginView, AdminManagementView


urlpatterns = [
    
    path('register/', RegisterView.as_view(), name='register'),

    path('logout/', LogoutView.as_view(), name='logout'),

    path('login/', LoginView.as_view(), name='login'),

    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('admin/manage-users/', AdminManagementView.as_view(), name='admin-manage-users')

]
