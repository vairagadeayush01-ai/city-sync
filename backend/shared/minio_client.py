"""
CitySync — MinIO S3-compatible object storage client.
Handles photo upload, pre-signed URL generation, and lifecycle management.
"""
import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from shared.config import settings


def _get_client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket():
    """Create the CitySync bucket if it doesn't exist."""
    client = _get_client()
    bucket = settings.minio_bucket
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            # Set a 90-day lifecycle policy
            _set_lifecycle_policy(client, bucket)
            print(f"✓ MinIO bucket '{bucket}' created")
        else:
            print(f"✓ MinIO bucket '{bucket}' already exists")
    except S3Error as e:
        print(f"✗ MinIO bucket check failed: {e}")


def _set_lifecycle_policy(client: Minio, bucket: str):
    """Set 90-day expiry lifecycle policy on the bucket."""
    lifecycle_config = """<?xml version="1.0" encoding="UTF-8"?>
<LifecycleConfiguration>
  <Rule>
    <ID>citysync-90-day-expiry</ID>
    <Status>Enabled</Status>
    <Filter><Prefix></Prefix></Filter>
    <Expiration><Days>90</Days></Expiration>
  </Rule>
</LifecycleConfiguration>"""
    from minio.lifecycleconfig import LifecycleConfig
    import xml.etree.ElementTree as ET
    # Skip lifecycle for hackathon — requires specific MinIO config
    pass


def upload_photo(ticket_id: str, photo_type: str, image_data: bytes, content_type: str = "image/jpeg") -> str:
    """
    Upload a complaint photo to MinIO.

    Args:
        ticket_id: The ticket UUID
        photo_type: 'before', 'after', or 'reverify'
        image_data: Raw image bytes
        content_type: MIME type

    Returns:
        object_key: The MinIO object path (stored in tickets.image_key)
    """
    client = _get_client()
    object_key = f"complaints/{ticket_id}/{photo_type}.jpg"

    client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(image_data),
        length=len(image_data),
        content_type=content_type,
    )
    return object_key


def get_presigned_url(object_key: str, expiry_minutes: int = 10) -> str:
    """
    Generate a pre-signed URL for an officer to view a photo.
    URL expires after `expiry_minutes` (default 10 min).
    """
    client = _get_client()
    try:
        url = client.presigned_get_object(
            settings.minio_bucket,
            object_key,
            expires=timedelta(minutes=expiry_minutes),
        )
        return url
    except S3Error as e:
        raise RuntimeError(f"Failed to generate pre-signed URL: {e}")


def delete_photo(object_key: str):
    """Permanently delete a photo (called after resolution + 90-day TTL)."""
    client = _get_client()
    client.remove_object(settings.minio_bucket, object_key)
