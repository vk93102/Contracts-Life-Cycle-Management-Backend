"""
URL configuration for authentication app
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    TokenView,
    RegisterView,
    CurrentUserView,
    ForgotPasswordView,
    ResetPasswordView,
)

urlpatterns = [
    path('login/', TokenView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('me/', CurrentUserView.as_view(), name='current_user'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
]
