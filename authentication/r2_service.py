"""
Cloudflare R2 Storage Service
"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
import uuid
import mimetypes


class R2StorageService:
    """
    Service for interacting with Cloudflare R2 storage
    """
    
    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        self.bucket_name = settings.R2_BUCKET_NAME
    
    def upload_file(self, file_obj, tenant_id, filename=None):
        """
        Upload a file to R2
        
        Args:
            file_obj: Django UploadedFile object
            tenant_id: UUID of the tenant
            filename: Optional custom filename
        
        Returns:
            str: The R2 key (path) of the uploaded file
        """
        if not filename:
            filename = file_obj.name
        
        # Generate unique key with tenant isolation
        file_extension = filename.split('.')[-1] if '.' in filename else ''
        unique_id = str(uuid.uuid4())
        r2_key = f"{tenant_id}/contracts/{unique_id}.{file_extension}"
        
        # Detect content type
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = 'application/octet-stream'
        
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=r2_key,
                Body=file_obj.read(),
                ContentType=content_type,
                Metadata={
                    'tenant_id': str(tenant_id),
                    'original_filename': filename
                }
            )
            return r2_key
        except ClientError as e:
            raise Exception(f"Failed to upload file to R2: {str(e)}")
    
    def generate_presigned_url(self, r2_key, expiration=3600):
        """
        Generate a presigned URL for secure file access
        
        Args:
            r2_key: The R2 key (path) of the file
            expiration: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            str: Presigned URL
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': r2_key
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            raise Exception(f"Failed to generate presigned URL: {str(e)}")
    
    def delete_file(self, r2_key):
        """
        Delete a file from R2
        
        Args:
            r2_key: The R2 key (path) of the file to delete
        
        Returns:
            bool: True if successful
        """
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=r2_key
            )
            return True
        except ClientError as e:
            raise Exception(f"Failed to delete file from R2: {str(e)}")
    
    def file_exists(self, r2_key):
        """
        Check if a file exists in R2
        
        Args:
            r2_key: The R2 key (path) of the file
        
        Returns:
            bool: True if file exists
        """
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=r2_key
            )
            return True
        except ClientError:
            return False
