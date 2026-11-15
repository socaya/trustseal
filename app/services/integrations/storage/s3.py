"""S3-compatible :class:`ObjectStore` implementation.

Hard requirements (enforced at construction time):

* The bucket **must** have server-side encryption with a KMS key
  (``sse_kms_key_id``). Objects without SSE-KMS are rejected on write.
* Writes always go through ``PutObject`` with ``ServerSideEncryption``
  set so an accidentally mis-configured bucket does not silently
  persist unencrypted bytes.

Object lock is handled by the deployment's bucket policy, not by this
class — enforcing it at the application layer is a defence-in-depth
measure that would mask a mis-configured bucket.

The ``endpoint_url`` parameter supports MinIO and S3-compatible
providers for local parity.
"""
from __future__ import annotations

from typing import BinaryIO, Iterator

from .base import ObjectMeta, ObjectPut, ObjectStore, ObjectStoreError, ObjectVersion


class S3ObjectStore(ObjectStore):
    def __init__(
        self,
        bucket: str,
        *,
        sse_kms_key_id: str,
        region: str | None = None,
        endpoint_url: str | None = None,
        client=None,
    ) -> None:
        if not bucket or not isinstance(bucket, str):
            raise ObjectStoreError("S3 bucket name is required")
        if not sse_kms_key_id or not isinstance(sse_kms_key_id, str):
            raise ObjectStoreError("SSE-KMS key id is required")
        self._bucket = bucket
        self._kms_key_id = sse_kms_key_id
        if client is None:
            import boto3  # local import so unit tests that never touch S3

            client = boto3.client(
                "s3", region_name=region, endpoint_url=endpoint_url
            )
        self._s3 = client

    # ----- helpers --------------------------------------------------

    def _put_kwargs(self, body: bytes, content_type: str, metadata: dict[str, str] | None):
        extra: dict = {
            "Bucket": self._bucket,
            "Body": body,
            "ContentType": content_type,
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": self._kms_key_id,
        }
        if metadata:
            extra["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
        return extra

    # ----- interface ------------------------------------------------

    def put(
        self,
        key: str,
        body: bytes | BinaryIO,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> ObjectPut:
        self.validate_key(key)
        if hasattr(body, "read"):
            payload = body.read()
        else:
            payload = bytes(body)
        try:
            response = self._s3.put_object(
                Key=key, **self._put_kwargs(payload, content_type, metadata)
            )
        except Exception as exc:  # boto3 ClientError plumbing
            raise ObjectStoreError(f"S3 put failed: {exc}") from exc
        return ObjectPut(
            key=key,
            size=len(payload),
            etag=(response.get("ETag") or "").strip('"'),
            version_id=response.get("VersionId"),
        )

    def get(self, key: str) -> bytes:
        self.validate_key(key)
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise ObjectStoreError(f"S3 get failed: {exc}") from exc
        return response["Body"].read()

    def stream(self, key: str) -> Iterator[bytes]:
        self.validate_key(key)
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise ObjectStoreError(f"S3 stream failed: {exc}") from exc
        body = response["Body"]
        try:
            while True:
                chunk = body.read(64 * 1024)
                if not chunk:
                    return
                yield chunk
        finally:
            body.close()

    def head(self, key: str) -> ObjectMeta:
        self.validate_key(key)
        try:
            response = self._s3.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise ObjectStoreError(f"S3 head failed: {exc}") from exc
        return ObjectMeta(
            key=key,
            size=int(response.get("ContentLength", 0)),
            content_type=response.get("ContentType", "application/octet-stream"),
            etag=(response.get("ETag") or "").strip('"'),
            last_modified_epoch=int(response["LastModified"].timestamp())
            if response.get("LastModified")
            else 0,
        )

    def exists(self, key: str) -> bool:
        try:
            self.head(key)
            return True
        except ObjectStoreError:
            return False

    def delete(self, key: str) -> None:
        self.validate_key(key)
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise ObjectStoreError(f"S3 delete failed: {exc}") from exc

    def list_versions(self, key: str) -> list[ObjectVersion]:
        self.validate_key(key)
        try:
            response = self._s3.list_object_versions(
                Bucket=self._bucket, Prefix=key
            )
        except Exception as exc:
            raise ObjectStoreError(f"S3 list_versions failed: {exc}") from exc
        versions: list[ObjectVersion] = []
        for entry in response.get("Versions", []) or []:
            if entry.get("Key") != key:
                continue
            versions.append(
                ObjectVersion(
                    key=key,
                    version_id=entry.get("VersionId") or "",
                    size=int(entry.get("Size", 0)),
                    created_at_epoch=int(entry["LastModified"].timestamp())
                    if entry.get("LastModified")
                    else 0,
                    is_latest=bool(entry.get("IsLatest")),
                )
            )
        return versions

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("ttl_seconds must be between 1 and 3600")
        self.validate_key(key)
        try:
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=int(ttl_seconds),
            )
        except Exception as exc:
            raise ObjectStoreError(f"S3 presign failed: {exc}") from exc
