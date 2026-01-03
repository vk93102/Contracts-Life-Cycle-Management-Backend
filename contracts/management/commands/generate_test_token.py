"""
Django management command to generate test JWT tokens
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import jwt
import uuid
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Generate a test JWT token for API testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            default='test@example.com',
            help='Email for the test user'
        )
        parser.add_argument(
            '--tenant-id',
            type=str,
            default=None,
            help='Tenant ID (UUID). If not provided, a random one will be generated'
        )
        parser.add_argument(
            '--role',
            type=str,
            default='admin',
            help='User role (admin, user, etc.)'
        )

    def handle(self, *args, **options):
        email = options['email']
        tenant_id = options['tenant_id'] or str(uuid.uuid4())
        role = options['role']
        user_id = str(uuid.uuid4())
        
        # Create JWT payload
        payload = {
            'sub': user_id,
            'email': email,
            'role': role,
            'aud': 'authenticated',
            'user_metadata': {
                'tenant_id': tenant_id
            },
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        
        # Generate token
        token = jwt.encode(
            payload,
            settings.SUPABASE_JWT_SECRET,
            algorithm='HS256'
        )
        
        self.stdout.write(self.style.SUCCESS('\n=== Test JWT Token Generated ==='))
        self.stdout.write(f'User ID: {user_id}')
        self.stdout.write(f'Email: {email}')
        self.stdout.write(f'Tenant ID: {tenant_id}')
        self.stdout.write(f'Role: {role}')
        self.stdout.write('\nToken:')
        self.stdout.write(self.style.WARNING(token))
        self.stdout.write('\nUse this token in your API calls:')
        self.stdout.write(f'curl -H "Authorization: Bearer {token}" http://localhost:8888/api/v1/auth/me/')
        self.stdout.write('\n')
