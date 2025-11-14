from smart_open import open as smart_open
import os
from django.conf import settings


def  upload_to_s3_with_smart_open(uploaded_file, s3_filename):
    """
    Upload file to S3 using smart_open
    """
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    s3_uri = f"s3://{bucket_name}/{s3_filename}"
    
    # Transport params for authentication
    transport_params = {
        'client_kwargs': {
            'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
            'region_name': settings.AWS_S3_REGION_NAME
        }
    }
    
    # Upload using smart_open
    with smart_open(s3_uri, 'wb', transport_params=transport_params) as s3_file:
        # For Django UploadedFile
        for chunk in uploaded_file.chunks():
            s3_file.write(chunk)
    
    # Generate S3 URL
    s3_url = f"https://{bucket_name}.s3.{os.getenv('AWS_S3_REGION_NAME')}.amazonaws.com/{s3_filename}"
    return s3_url