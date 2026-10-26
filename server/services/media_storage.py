import os
import uuid
import time
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from server.utils.config import config

logger = logging.getLogger(__name__)


class BaseMediaStorage(ABC):
    """Abstract base class for media storage providers."""

    @abstractmethod
    def save_image(
        self,
        content: bytes,
        extension: str,
        mime_type: str,
        media_id: Optional[str] = None
    ) -> str:
        """
        Saves image bytes and returns a stable reference / URL / path.
        """
        pass

    def get_url(self, storage_ref: str, expires_in: int = 3600) -> str:
        """
        Returns an accessible URL for the given media reference.
        Default implementation returns the reference unchanged (e.g. for local storage).
        """
        return storage_ref


class LocalMediaStorage(BaseMediaStorage):
    """
    Local filesystem storage provider for development and standalone environments.
    Stores files under the configured upload directory and serves them via static mount.
    """

    def __init__(self, upload_dir: Optional[str] = None, url_prefix: str = "/uploads/whatsapp"):
        if upload_dir is None:
            # server/uploads/whatsapp by default
            server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            upload_dir = os.path.join(server_dir, "uploads", "whatsapp")
        self.upload_dir = os.path.abspath(upload_dir)
        self.url_prefix = url_prefix.rstrip("/")
        os.makedirs(self.upload_dir, exist_ok=True)

    def save_image(
        self,
        content: bytes,
        extension: str,
        mime_type: str,
        media_id: Optional[str] = None
    ) -> str:
        # Sanitize and normalize extension
        ext = extension.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        # Generate safe collision-resistant filename without user-provided components
        timestamp = int(time.time())
        unique_token = uuid.uuid4().hex[:12]
        if media_id:
            safe_hash = hashlib.sha256(media_id.encode("utf-8")).hexdigest()[:8]
            filename = f"wa_{timestamp}_{safe_hash}_{unique_token}{ext}"
        else:
            filename = f"wa_{timestamp}_{unique_token}{ext}"

        # Guard against path traversal
        file_path = os.path.abspath(os.path.join(self.upload_dir, filename))
        if os.path.commonpath([self.upload_dir, file_path]) != self.upload_dir:
            raise ValueError("Potential path traversal detected during media persistence.")

        with open(file_path, "wb") as f:
            f.write(content)

        return f"{self.url_prefix}/{filename}"


class R2MediaStorage(BaseMediaStorage):
    """
    Cloudflare R2 (S3-compatible) object storage provider.
    Maintains private, persistent bucket storage across container restarts and redeployments.
    """

    def __init__(
        self,
        account_id: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        bucket_name: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        public_url: Optional[str] = None,
        prefix: str = "complaints",
        s3_client: Optional[Any] = None,
    ):
        self.account_id = (account_id or getattr(config, "R2_ACCOUNT_ID", None) or os.getenv("R2_ACCOUNT_ID", "")).strip()
        self.endpoint_url = (endpoint_url or getattr(config, "R2_ENDPOINT_URL", None) or os.getenv("R2_ENDPOINT_URL", "")).strip()
        if not self.endpoint_url and self.account_id:
            self.endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"

        self.bucket_name = (
            bucket_name
            or getattr(config, "R2_BUCKET_NAME", None)
            or os.getenv("R2_BUCKET_NAME", os.getenv("R2_BUCKET", ""))
        ).strip()
        self.access_key_id = (access_key_id or getattr(config, "R2_ACCESS_KEY_ID", None) or os.getenv("R2_ACCESS_KEY_ID", "")).strip()
        self.secret_access_key = (secret_access_key or getattr(config, "R2_SECRET_ACCESS_KEY", None) or os.getenv("R2_SECRET_ACCESS_KEY", "")).strip()
        self.public_url = (public_url or getattr(config, "R2_PUBLIC_URL", None) or os.getenv("R2_PUBLIC_URL", os.getenv("R2_CUSTOM_DOMAIN", ""))).strip().rstrip("/")
        self.prefix = prefix.strip().strip("/")

        if s3_client is not None:
            self.s3_client = s3_client
        else:
            if not self.bucket_name or not self.access_key_id or not self.secret_access_key:
                raise ValueError("Cloudflare R2 configuration error: R2_BUCKET_NAME, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY are required.")
            if not self.endpoint_url:
                raise ValueError("Cloudflare R2 configuration error: Either R2_ENDPOINT_URL or R2_ACCOUNT_ID must be specified.")

            try:
                import boto3
                from botocore.config import Config as BotoConfig
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name="auto",
                    config=BotoConfig(
                        signature_version="s3v4",
                        s3={"addressing_style": "path"}
                    )
                )
            except ImportError as err:
                raise RuntimeError("boto3 is required for Cloudflare R2 storage. Run 'pip install boto3'.") from err

    def save_image(
        self,
        content: bytes,
        extension: str,
        mime_type: str,
        media_id: Optional[str] = None
    ) -> str:
        # Sanitize and normalize extension
        ext = extension.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError(f"Unsupported media extension '{ext}' for R2 storage.")

        timestamp = int(time.time())
        unique_token = uuid.uuid4().hex[:12]
        if media_id:
            safe_hash = hashlib.sha256(media_id.encode("utf-8")).hexdigest()[:8]
            filename = f"wa_{timestamp}_{safe_hash}_{unique_token}{ext}"
        else:
            filename = f"img_{timestamp}_{unique_token}{ext}"

        object_key = f"{self.prefix}/{filename}" if self.prefix else filename

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=content,
                ContentType=mime_type,
            )
        except Exception as exc:
            logger.error(f"[R2 STORAGE] Failed to put object '{object_key}': {type(exc).__name__}")
            raise RuntimeError(f"Failed to store media in Cloudflare R2: {type(exc).__name__}") from exc

        # If a public custom domain / CDN URL is configured, return the full public URL.
        # Otherwise, return an expiring presigned URL (private by default).
        if self.public_url:
            return f"{self.public_url}/{object_key}"

        return self.generate_presigned_url(object_key, expires_in=7 * 24 * 3600)

    def generate_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        """Generates an expiring pre-signed GET URL for secure, authenticated access."""
        try:
            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            logger.error(f"[R2 STORAGE] Presigned URL generation failed for '{object_key}': {type(exc).__name__}")
            raise RuntimeError(f"Failed to generate presigned URL: {type(exc).__name__}") from exc

    def get_object(self, object_key: str) -> bytes:
        """Retrieves raw object bytes from Cloudflare R2."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            return response["Body"].read()
        except Exception as exc:
            logger.error(f"[R2 STORAGE] Failed to retrieve object '{object_key}': {type(exc).__name__}")
            raise RuntimeError(f"Failed to retrieve object from R2: {type(exc).__name__}") from exc

    def get_url(self, storage_ref: str, expires_in: int = 3600) -> str:
        """Resolves an object reference into a reachable URL."""
        if storage_ref.startswith("http://") or storage_ref.startswith("https://"):
            return storage_ref
        clean_key = storage_ref.lstrip("/")
        if self.public_url:
            return f"{self.public_url}/{clean_key}"
        return self.generate_presigned_url(clean_key, expires_in=expires_in)



class SupabaseMediaStorage(BaseMediaStorage):
    """
    Supabase Storage provider for private complaint image hosting.
    Stores objects in a private bucket and generates short-lived signed URLs for retrieval.
    Persists stable object key references (prefixed with 'supabase:') in the database
    instead of expiring signed URLs.
    """

    # Prefix used in stored references to distinguish Supabase object keys
    REF_PREFIX = "supabase:"

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        signed_url_ttl: Optional[int] = None,
        prefix: str = "complaints",
        client: Optional[Any] = None,
    ):
        self.supabase_url = (
            supabase_url
            or getattr(config, "SUPABASE_URL", None)
            or os.getenv("SUPABASE_URL", "")
        ).strip().rstrip("/")
        self.service_role_key = (
            service_role_key
            or getattr(config, "SUPABASE_SERVICE_ROLE_KEY", None)
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()
        self.bucket_name = (
            bucket_name
            or getattr(config, "SUPABASE_STORAGE_BUCKET", None)
            or os.getenv("SUPABASE_STORAGE_BUCKET", "complaint-images")
        ).strip()
        self.signed_url_ttl = int(
            signed_url_ttl
            if signed_url_ttl is not None
            else (
                getattr(config, "SUPABASE_SIGNED_URL_TTL_SECONDS", None)
                or os.getenv("SUPABASE_SIGNED_URL_TTL_SECONDS", "900")
            )
        )
        self.prefix = prefix.strip().strip("/")

        if client is not None:
            self._client = client
        else:
            if not self.supabase_url or not self.service_role_key:
                raise ValueError(
                    "Supabase configuration error: SUPABASE_URL and "
                    "SUPABASE_SERVICE_ROLE_KEY are required."
                )
            try:
                from supabase import create_client
                self._client = create_client(self.supabase_url, self.service_role_key)
            except ImportError as err:
                raise RuntimeError(
                    "supabase is required for Supabase storage. "
                    "Run 'pip install supabase'."
                ) from err

    @property
    def storage(self):
        """Returns the Supabase Storage file API for the configured bucket."""
        return self._client.storage.from_(self.bucket_name)

    def _generate_object_key(
        self, extension: str, media_id: Optional[str] = None
    ) -> str:
        """Generates a collision-resistant object key."""
        ext = extension.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError(
                f"Unsupported media extension '{ext}' for Supabase storage."
            )

        timestamp = int(time.time())
        unique_token = uuid.uuid4().hex[:12]
        if media_id:
            safe_hash = hashlib.sha256(media_id.encode("utf-8")).hexdigest()[:8]
            filename = f"wa_{timestamp}_{safe_hash}_{unique_token}{ext}"
        else:
            filename = f"img_{timestamp}_{unique_token}{ext}"

        return f"{self.prefix}/{filename}" if self.prefix else filename

    def save_image(
        self,
        content: bytes,
        extension: str,
        mime_type: str,
        media_id: Optional[str] = None,
    ) -> str:
        """
        Uploads image bytes to the private Supabase bucket.
        Returns a stable reference string (prefixed with 'supabase:') suitable
        for permanent storage in the database.
        """
        object_key = self._generate_object_key(extension, media_id)

        try:
            self.storage.upload(
                path=object_key,
                file=content,
                file_options={"content-type": mime_type},
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            # Supabase returns 409/duplicate when key already exists
            if "duplicate" in error_msg or "already exists" in error_msg:
                logger.warning(
                    "[SUPABASE STORAGE] Object '%s' already exists; treating as success.",
                    object_key,
                )
            else:
                logger.error(
                    "[SUPABASE STORAGE] Failed to upload object '%s': %s",
                    object_key,
                    type(exc).__name__,
                )
                raise RuntimeError(
                    f"Failed to store media in Supabase Storage: {type(exc).__name__}"
                ) from exc

        return f"{self.REF_PREFIX}{object_key}"

    def create_signed_url(
        self, object_key: str, expires_in: Optional[int] = None
    ) -> str:
        """Generates a short-lived signed URL for private object access."""
        ttl = expires_in if expires_in is not None else self.signed_url_ttl
        try:
            result = self.storage.create_signed_url(object_key, ttl)
            if isinstance(result, dict):
                url = result.get("signedURL") or result.get("signedUrl", "")
            else:
                url = str(result)
            if not url:
                raise RuntimeError("Supabase returned an empty signed URL.")
            return url
        except Exception as exc:
            logger.error(
                "[SUPABASE STORAGE] Signed URL generation failed for '%s': %s",
                object_key,
                type(exc).__name__,
            )
            raise RuntimeError(
                f"Failed to generate Supabase signed URL: {type(exc).__name__}"
            ) from exc

    def get_url(self, storage_ref: str, expires_in: Optional[int] = None) -> str:
        """
        Resolves a storage reference into a browser-accessible URL.
        - 'supabase:...' references → fresh signed URL
        - 'http(s)://...' or 'data:...' → returned unchanged
        - '/uploads/...' local paths → returned unchanged
        """
        if not storage_ref:
            return storage_ref
        if storage_ref.startswith(self.REF_PREFIX):
            object_key = storage_ref[len(self.REF_PREFIX):]
            return self.create_signed_url(object_key, expires_in)
        # Legacy absolute URLs, data URIs, or local paths — pass through
        return storage_ref



_storage_instance: Optional[BaseMediaStorage] = None


def get_media_storage() -> BaseMediaStorage:
    """Returns the configured media storage instance based on MEDIA_STORAGE_BACKEND."""
    global _storage_instance
    if _storage_instance is None:
        backend = (os.getenv("MEDIA_STORAGE_BACKEND") or getattr(config, "MEDIA_STORAGE_BACKEND", "local") or "local").strip().lower()
        if backend in ("r2", "s3", "cloudflare"):
            _storage_instance = R2MediaStorage()
        elif backend == "supabase":
            _storage_instance = SupabaseMediaStorage()
        else:
            _storage_instance = LocalMediaStorage()
    return _storage_instance


def set_media_storage(storage: Optional[BaseMediaStorage]) -> None:
    """Allows overriding or mocking the media storage instance (e.g. in tests or cloud swap)."""
    global _storage_instance
    _storage_instance = storage
