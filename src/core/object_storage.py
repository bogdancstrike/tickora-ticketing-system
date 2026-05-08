"""S3/MinIO object-storage helper."""
from __future__ import annotations

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from src.config import Config

_client = None


def get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=Config.S3_ENDPOINT_URL,
            region_name=Config.S3_REGION,
            aws_access_key_id=Config.S3_ACCESS_KEY,
            aws_secret_access_key=Config.S3_SECRET_KEY,
            config=BotoConfig(signature_version="s3v4"),
        )
    return _client


def ensure_bucket(bucket: str) -> None:
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
    allowed_origins = Config.ALLOWED_ORIGINS or ["*"]
    client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": allowed_origins,
                    "AllowedMethods": ["GET", "PUT", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 600,
                }
            ]
        },
    )


def object_exists(bucket: str, key: str) -> bool:
    try:
        get_s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def presigned_put_url(bucket: str, key: str, *, content_type: str | None, expires: int) -> str:
    params = {"Bucket": bucket, "Key": key}
    if content_type:
        params["ContentType"] = content_type
    return get_s3_client().generate_presigned_url(
        "put_object",
        Params=params,
        ExpiresIn=expires,
    )


def presigned_get_url(bucket: str, key: str, *, expires: int) -> str:
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )
