"""Private object storage service (S3 / MinIO) - ADR-007.

Buckets per purpose (``settings.S3_BUCKETS``): ``quarantine`` (raw uploads, never served),
``documents`` (clean files), ``exports`` (expiring), ``public`` (logos). Browsers only ever
receive short-lived presigned URLs; objects are never public.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Literal

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

Purpose = Literal["quarantine", "documents", "exports", "public"]

PUT_TTL_SECONDS = 600
GET_TTL_SECONDS = 60


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    content_type: str
    etag: str
    metadata: dict[str, str]


def bucket_for(purpose: Purpose) -> str:
    try:
        return settings.S3_BUCKETS[purpose]
    except KeyError as exc:
        raise ValueError(f"Unknown storage purpose: {purpose}") from exc


def _make_client(endpoint: str | None) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=20,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


@functools.cache
def client() -> Any:
    """Server-side client (talks to the internal endpoint, e.g. http://minio:9000)."""
    return _make_client(settings.S3_ENDPOINT_URL)


@functools.cache
def presign_client() -> Any:
    """Client used only to sign URLs for browsers (public endpoint, e.g. http://localhost:9000)."""
    return _make_client(settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL)


def reset_clients() -> None:
    client.cache_clear()
    presign_client.cache_clear()


def presign_put(
    purpose: Purpose, key: str, content_type: str, ttl: int = PUT_TTL_SECONDS
) -> dict[str, Any]:
    """Return ``{"url", "method", "headers", "expires_in"}`` for a direct browser PUT."""
    url = presign_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket_for(purpose), "Key": key, "ContentType": content_type},
        ExpiresIn=ttl,
        HttpMethod="PUT",
    )
    return {
        "url": url,
        "method": "PUT",
        "headers": {"Content-Type": content_type},
        "expires_in": ttl,
    }


def presign_get(
    purpose: Purpose,
    key: str,
    ttl: int = GET_TTL_SECONDS,
    filename: str | None = None,
    inline: bool = False,
) -> str:
    params: dict[str, Any] = {"Bucket": bucket_for(purpose), "Key": key}
    if filename:
        safe = filename.replace('"', "").replace("\r", "").replace("\n", "")
        disposition = "inline" if inline else "attachment"
        params["ResponseContentDisposition"] = f'{disposition}; filename="{safe}"'
    return presign_client().generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)


def head_object(purpose: Purpose, key: str) -> ObjectInfo | None:
    try:
        resp = client().head_object(Bucket=bucket_for(purpose), Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return ObjectInfo(
        key=key,
        size=int(resp.get("ContentLength", 0)),
        content_type=resp.get("ContentType", ""),
        etag=str(resp.get("ETag", "")).strip('"'),
        metadata=dict(resp.get("Metadata", {})),
    )


def put_bytes(purpose: Purpose, key: str, data: bytes, content_type: str) -> None:
    client().put_object(Bucket=bucket_for(purpose), Key=key, Body=data, ContentType=content_type)


def get_bytes(purpose: Purpose, key: str, max_bytes: int | None = None) -> bytes:
    params: dict[str, Any] = {"Bucket": bucket_for(purpose), "Key": key}
    if max_bytes is not None:
        params["Range"] = f"bytes=0-{max_bytes - 1}"
    return client().get_object(**params)["Body"].read()


def move_object(
    src_purpose: Purpose, src_key: str, dst_purpose: Purpose, dst_key: str | None = None
) -> str:
    """Copy to the destination bucket then delete the source. Returns the destination key."""
    dst_key = dst_key or src_key
    client().copy_object(
        Bucket=bucket_for(dst_purpose),
        Key=dst_key,
        CopySource={"Bucket": bucket_for(src_purpose), "Key": src_key},
        MetadataDirective="COPY",
    )
    delete_object(src_purpose, src_key)
    return dst_key


def delete_object(purpose: Purpose, key: str) -> None:
    client().delete_object(Bucket=bucket_for(purpose), Key=key)


def check_bucket(purpose: Purpose = "documents") -> None:
    """Raise if the bucket is unreachable (used by /readyz)."""
    client().head_bucket(Bucket=bucket_for(purpose))
