"""
Authentication API Tests
"""
import json
from django.test import TestCase, Client
from authentication.models import User


class AuthenticationAPITest(TestCase):
    """Test authentication endpoints"""
    
    def setUp(self):
        """Set up test client and test user"""
        self.client = Client()
        self.test_email = 'test@example.com'
        self.test_password = 'testpass123'
        
        # Create a test user
        self.user = User(
            email=self.test_email,
            full_name='Test User',
            tenant_id='550e8400-e29b-41d4-a716-446655440000',
            role='user'
        )
        self.user.set_password(self.test_password)
        self.user.save()
    
    def test_user_registration(self):
        """Test user registration endpoint"""
        response = self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps({
                'email': 'newuser@example.com',
                'password': 'newpass123',
                'full_name': 'New User'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], 'newuser@example.com')
        
        # Verify user was created in database
        user = User.objects.get(email='newuser@example.com')
        self.assertEqual(user.full_name, 'New User')
    
    def test_user_registration_duplicate_email(self):
        """Test registration with existing email"""
        response = self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps({
                'email': self.test_email,
                'password': 'somepass123'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
    
    def test_user_registration_weak_password(self):
        """Test registration with weak password"""
        response = self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps({
                'email': 'test2@example.com',
                'password': '123'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
    
    def test_user_login_success(self):
        """Test successful login"""
        response = self.client.post(
            '/api/v1/auth/token/',
            data=json.dumps({
                'email': self.test_email,
                'password': self.test_password
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('token', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], self.test_email)
    
    def test_user_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = self.client.post(
            '/api/v1/auth/token/',
            data=json.dumps({
                'email': self.test_email,
                'password': 'wrongpassword'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn('error', data)
    
    def test_user_login_nonexistent_user(self):
        """Test login with nonexistent user"""
        response = self.client.post(
            '/api/v1/auth/token/',
            data=json.dumps({
                'email': 'nonexistent@example.com',
                'password': 'password123'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 401)
    
    def test_get_current_user(self):
        """Test getting current user info"""
        # First login to get token
        login_response = self.client.post(
            '/api/v1/auth/token/',
            data=json.dumps({
                'email': self.test_email,
                'password': self.test_password
            }),
            content_type='application/json'
        )
        
        token = login_response.json()['access']
        
        # Get current user info
        response = self.client.get(
            '/api/v1/auth/me/',
            HTTP_AUTHORIZATION=f'Bearer {token}'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['email'], self.test_email)
    
    def test_get_current_user_unauthorized(self):
        """Test getting current user without token"""
        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 403)
    
    def test_forgot_password(self):
        """Test forgot password endpoint"""
        response = self.client.post(
            '/api/v1/auth/forgot-password/',
            data=json.dumps({
                'email': self.test_email
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertIn('reset_token', data)  # Only for testing
        
        # Verify reset token was saved
        user = User.objects.get(email=self.test_email)
        self.assertIsNotNone(user.reset_token)
        self.assertIsNotNone(user.reset_token_expires)
    
    def test_reset_password(self):
        """Test password reset with valid token"""
        # First request password reset
        forgot_response = self.client.post(
            '/api/v1/auth/forgot-password/',
            data=json.dumps({
                'email': self.test_email
            }),
            content_type='application/json'
        )
        
        reset_token = forgot_response.json()['reset_token']
        new_password = 'newpassword123'
        
        # Reset password
        response = self.client.post(
            '/api/v1/auth/reset-password/',
            data=json.dumps({
                'token': reset_token,
                'password': new_password
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify can login with new password
        login_response = self.client.post(
            '/api/v1/auth/token/',
            data=json.dumps({
                'email': self.test_email,
                'password': new_password
            }),
            content_type='application/json'
        )
        
        self.assertEqual(login_response.status_code, 200)
    
    def test_reset_password_invalid_token(self):
        """Test password reset with invalid token"""
        response = self.client.post(
            '/api/v1/auth/reset-password/',
            data=json.dumps({
                'token': 'invalid_token',
                'password': 'newpassword123'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
