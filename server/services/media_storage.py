import os
import uuid
import time
import hashlib
from abc import ABC, abstractmethod
from typing import Optional
from server.utils.config import config


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


_storage_instance: Optional[BaseMediaStorage] = None


def get_media_storage() -> BaseMediaStorage:
    """Returns the configured media storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalMediaStorage()
    return _storage_instance


def set_media_storage(storage: Optional[BaseMediaStorage]) -> None:
    """Allows overriding or mocking the media storage instance (e.g. in tests or cloud swap)."""
    global _storage_instance
    _storage_instance = storage
