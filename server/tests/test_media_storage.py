"""
Automated unit and integration tests for Media Storage:
  - LocalMediaStorage (development/test fallback)
  - Cloudflare R2 / S3 storage provider (mocked S3 client, no real credentials needed)
  - Configuration validation and fail-closed security guards
  - Presigned URL generation and private bucket handling
  - Error handling and upload route integration
"""
import os
import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from server.services.media_storage import (
    BaseMediaStorage,
    LocalMediaStorage,
    R2MediaStorage,
    SupabaseMediaStorage,
    get_media_storage,
    set_media_storage,
)
from server.utils.config import config
from server.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixture: clean storage instance teardown
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def reset_storage_instance():
    """Ensures each test starts and ends with a clean storage instance."""
    set_media_storage(None)
    yield
    set_media_storage(None)


# ---------------------------------------------------------------------------
# 1. Local Storage Fallback & Behavior
# ---------------------------------------------------------------------------
class TestLocalStorage:
    def test_default_storage_is_local(self, monkeypatch):
        monkeypatch.delenv("MEDIA_STORAGE_BACKEND", raising=False)
        monkeypatch.setattr(config, "MEDIA_STORAGE_BACKEND", "local")
        storage = get_media_storage()
        assert isinstance(storage, LocalMediaStorage)

    def test_local_storage_saves_and_returns_relative_url(self, tmp_path):
        storage = LocalMediaStorage(upload_dir=str(tmp_path), url_prefix="/uploads/test")
        content = b"fake_jpeg_binary_data"
        ref = storage.save_image(
            content=content,
            extension=".jpg",
            mime_type="image/jpeg",
            media_id="wa_msg_12345"
        )
        assert ref.startswith("/uploads/test/")
        assert ref.endswith(".jpg")

        # Verify file was written to disk
        filename = os.path.basename(ref)
        file_path = tmp_path / filename
        assert file_path.exists()
        assert file_path.read_bytes() == content

    def test_local_storage_path_traversal_protection(self, tmp_path):
        storage = LocalMediaStorage(upload_dir=str(tmp_path))
        # Extension containing directory traversal attempts must be rejected with ValueError
        with pytest.raises(ValueError, match="Potential path traversal"):
            storage.save_image(b"data", "../../../evil.jpg", "image/jpeg")


# ---------------------------------------------------------------------------
# 2. R2 Configuration & Validation
# ---------------------------------------------------------------------------
class TestR2Configuration:
    def test_r2_missing_credentials_raises_error(self, monkeypatch):
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(ValueError) as exc:
            R2MediaStorage(
                bucket_name="",
                access_key_id="",
                secret_access_key="",
                endpoint_url="https://account.r2.cloudflarestorage.com"
            )
        assert "R2_BUCKET_NAME, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY are required" in str(exc.value)

    def test_r2_missing_endpoint_and_account_id_raises_error(self):
        with pytest.raises(ValueError) as exc:
            R2MediaStorage(
                bucket_name="my-bucket",
                access_key_id="test-key",
                secret_access_key="test-secret",
                endpoint_url="",
                account_id="",
            )
        assert "Either R2_ENDPOINT_URL or R2_ACCOUNT_ID must be specified" in str(exc.value)

    def test_r2_account_id_derives_endpoint(self):
        mock_s3 = MagicMock()
        storage = R2MediaStorage(
            account_id="abc123def456",
            bucket_name="test-bucket",
            access_key_id="key",
            secret_access_key="secret",
            s3_client=mock_s3
        )
        assert storage.endpoint_url == "https://abc123def456.r2.cloudflarestorage.com"

    def test_production_fails_when_r2_configured_without_credentials(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("CORS_ORIGINS", "https://city-swap-frontend.onrender.com")
        monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token")
        monkeypatch.setenv("META_APP_SECRET", "secret")
        monkeypatch.setenv("WHATSAPP_TOKEN", "token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
        monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "r2")
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        monkeypatch.delenv("R2_BUCKET", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)

        with pytest.raises(RuntimeError) as exc:
            config.validate_production_settings()
        assert "Cloudflare R2 storage settings are incomplete" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. R2 Upload, Presigned URLs, and Storage Operations
# ---------------------------------------------------------------------------
class TestR2StorageOperations:
    @pytest.fixture
    def mock_s3(self):
        return MagicMock()

    @pytest.fixture
    def r2_storage(self, mock_s3):
        return R2MediaStorage(
            account_id="testaccount",
            bucket_name="ecopulse-test-bucket",
            access_key_id="mock_key",
            secret_access_key="mock_secret",
            s3_client=mock_s3
        )

    def test_r2_save_image_uploads_to_s3(self, r2_storage, mock_s3):
        content = b"fake_image_bytes"
        mock_s3.generate_presigned_url.return_value = "https://mock-presigned-url.com/complaint.jpg"

        url = r2_storage.save_image(
            content=content,
            extension=".jpg",
            mime_type="image/jpeg",
            media_id="msg_9999"
        )

        # Verify S3 put_object call
        assert mock_s3.put_object.called
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "ecopulse-test-bucket"
        assert call_kwargs["ContentType"] == "image/jpeg"
        assert call_kwargs["Body"] == content
        assert call_kwargs["Key"].startswith("complaints/wa_")
        assert call_kwargs["Key"].endswith(".jpg")

        # Verify presigned URL returned by default (private bucket)
        assert url == "https://mock-presigned-url.com/complaint.jpg"

    def test_r2_save_image_with_public_cdn_url(self, mock_s3):
        storage = R2MediaStorage(
            account_id="testaccount",
            bucket_name="ecopulse-test-bucket",
            access_key_id="mock_key",
            secret_access_key="mock_secret",
            public_url="https://media.ecopulse.ai",
            s3_client=mock_s3
        )
        url = storage.save_image(
            content=b"bytes",
            extension=".png",
            mime_type="image/png"
        )
        assert url.startswith("https://media.ecopulse.ai/complaints/img_")
        assert url.endswith(".png")
        assert not mock_s3.generate_presigned_url.called

    def test_r2_rejects_unsupported_extensions(self, r2_storage):
        with pytest.raises(ValueError) as exc:
            r2_storage.save_image(b"evil", ".exe", "application/x-msdownload")
        assert "Unsupported media extension" in str(exc.value)

    def test_r2_get_object_success(self, r2_storage, mock_s3):
        mock_s3.get_object.return_value = {"Body": io.BytesIO(b"stored_content")}
        data = r2_storage.get_object("complaints/test.jpg")
        assert data == b"stored_content"
        mock_s3.get_object.assert_called_once_with(
            Bucket="ecopulse-test-bucket",
            Key="complaints/test.jpg"
        )

    def test_r2_upload_error_raises_runtime_error_without_leaking_secrets(self, r2_storage, mock_s3):
        mock_s3.put_object.side_effect = Exception("AWS S3 PutObject ConnectionReset")
        with pytest.raises(RuntimeError) as exc:
            r2_storage.save_image(b"data", ".jpg", "image/jpeg")
        assert "Failed to store media in Cloudflare R2" in str(exc.value)
        # Verify secrets are NOT leaked in exception message
        assert "mock_secret" not in str(exc.value)

    def test_r2_get_url_resolution(self, r2_storage, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://signed.example.com/item"
        # Full URL should be returned as is
        assert r2_storage.get_url("https://signed.example.com/item") == "https://signed.example.com/item"
        # Relative key should generate presigned URL
        signed = r2_storage.get_url("complaints/img_123.jpg")
        assert signed == "https://signed.example.com/item"


# ---------------------------------------------------------------------------
# 4. Upload Route Integration with R2
# ---------------------------------------------------------------------------
class TestUploadRouteR2Integration:
    def test_upload_route_uses_r2_when_configured(self):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://r2.example.com/complaints/img_test.jpg"
        r2_storage = R2MediaStorage(
            account_id="mock_account",
            bucket_name="mock-bucket",
            access_key_id="mock_key",
            secret_access_key="mock_secret",
            s3_client=mock_s3
        )
        set_media_storage(r2_storage)

        # Upload a valid JPEG (with JPEG magic bytes FF D8 FF)
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 100
        response = client.post(
            "/api/uploads",
            files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["url"] == "https://r2.example.com/complaints/img_test.jpg"
        assert data["filename"].endswith(".jpg")
        assert mock_s3.put_object.called


# ---------------------------------------------------------------------------
# 5. Supabase Storage Configuration & Guards
# ---------------------------------------------------------------------------
class TestSupabaseConfiguration:
    def test_supabase_missing_credentials_raises_error(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.setattr(config, "SUPABASE_URL", "")
        monkeypatch.setattr(config, "SUPABASE_SERVICE_ROLE_KEY", "")

        with pytest.raises(ValueError) as exc:
            SupabaseMediaStorage()
        assert "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required" in str(exc.value)

    def test_supabase_custom_credentials_accepted(self):
        mock_client = MagicMock()
        storage = SupabaseMediaStorage(
            supabase_url="https://custom.supabase.co",
            service_role_key="secret-service-key",
            bucket_name="custom-bucket",
            signed_url_ttl=600,
            client=mock_client
        )
        assert storage.supabase_url == "https://custom.supabase.co"
        assert storage.service_role_key == "secret-service-key"
        assert storage.bucket_name == "custom-bucket"
        assert storage.signed_url_ttl == 600

    def test_production_fails_when_supabase_configured_without_credentials(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("CORS_ORIGINS", "https://city-swap-frontend.onrender.com")
        monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token")
        monkeypatch.setenv("META_APP_SECRET", "secret")
        monkeypatch.setenv("WHATSAPP_TOKEN", "token")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
        monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "supabase")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.setattr(config, "MEDIA_STORAGE_BACKEND", "supabase")
        monkeypatch.setattr(config, "SUPABASE_URL", "")
        monkeypatch.setattr(config, "SUPABASE_SERVICE_ROLE_KEY", "")

        with pytest.raises(RuntimeError) as exc:
            config.validate_production_settings()
        assert "Supabase storage settings are incomplete" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. Supabase Storage Operations (Upload, Keys, Signed URLs, Pass-through)
# ---------------------------------------------------------------------------
class TestSupabaseStorageOperations:
    @pytest.fixture
    def mock_supabase_client(self):
        client = MagicMock()
        storage_api = MagicMock()
        client.storage.from_.return_value = storage_api
        return client, storage_api

    @pytest.fixture
    def supabase_storage(self, mock_supabase_client):
        client, storage_api = mock_supabase_client
        storage = SupabaseMediaStorage(
            supabase_url="https://test.supabase.co",
            service_role_key="test-service-key",
            bucket_name="complaint-images",
            signed_url_ttl=900,
            client=client
        )
        return storage, storage_api

    def test_supabase_save_image_returns_supabase_prefixed_reference(self, supabase_storage):
        storage, storage_api = supabase_storage
        content = b"fake-image-bytes"
        ref = storage.save_image(
            content=content,
            extension=".jpg",
            mime_type="image/jpeg"
        )
        assert ref.startswith("supabase:complaints/img_")
        assert ref.endswith(".jpg")
        storage_api.upload.assert_called_once()

    def test_supabase_save_image_with_media_id(self, supabase_storage):
        storage, storage_api = supabase_storage
        content = b"fake-image-bytes"
        ref = storage.save_image(
            content=content,
            extension=".png",
            mime_type="image/png",
            media_id="wa_media_12345"
        )
        assert ref.startswith("supabase:complaints/wa_")
        assert ref.endswith(".png")

    def test_supabase_rejects_unsupported_extensions(self, supabase_storage):
        storage, _ = supabase_storage
        with pytest.raises(ValueError) as exc:
            storage.save_image(b"data", ".exe", "application/octet-stream")
        assert "Unsupported media extension" in str(exc.value)

    def test_supabase_upload_duplicate_treated_as_success(self, supabase_storage):
        storage, storage_api = supabase_storage
        storage_api.upload.side_effect = Exception("The resource already exists / duplicate")
        ref = storage.save_image(b"data", ".jpg", "image/jpeg")
        assert ref.startswith("supabase:complaints/")

    def test_supabase_upload_error_raises_runtime_error_without_leaking_secrets(self, supabase_storage):
        storage, storage_api = supabase_storage
        storage_api.upload.side_effect = Exception("Database connection failure with secret key secret-service-key")
        with pytest.raises(RuntimeError) as exc:
            storage.save_image(b"data", ".jpg", "image/jpeg")
        assert "Failed to store media in Supabase Storage" in str(exc.value)
        assert "secret-service-key" not in str(exc.value)

    def test_supabase_create_signed_url(self, supabase_storage):
        storage, storage_api = supabase_storage
        storage_api.create_signed_url.return_value = {"signedURL": "https://test.supabase.co/storage/v1/object/sign/complaint-images/complaints/img_123.jpg?token=abc"}
        url = storage.create_signed_url("complaints/img_123.jpg")
        assert url == "https://test.supabase.co/storage/v1/object/sign/complaint-images/complaints/img_123.jpg?token=abc"
        storage_api.create_signed_url.assert_called_once_with("complaints/img_123.jpg", 900)

    def test_supabase_get_url_resolution(self, supabase_storage):
        storage, storage_api = supabase_storage
        storage_api.create_signed_url.return_value = {"signedURL": "https://signed.supabase.co/photo.jpg"}

        # 1. 'supabase:...' reference resolves to signed URL
        resolved = storage.get_url("supabase:complaints/img_123.jpg")
        assert resolved == "https://signed.supabase.co/photo.jpg"

        # 2. Legacy local paths pass through untouched
        assert storage.get_url("/uploads/whatsapp/img_123.jpg") == "/uploads/whatsapp/img_123.jpg"

        # 3. Web base64 data URLs pass through untouched
        assert storage.get_url("data:image/jpeg;base64,xxxx") == "data:image/jpeg;base64,xxxx"

        # 4. External URLs pass through untouched
        assert storage.get_url("https://images.unsplash.com/sample.jpg") == "https://images.unsplash.com/sample.jpg"


# ---------------------------------------------------------------------------
# 7. Upload Route Integration with Supabase
# ---------------------------------------------------------------------------
class TestUploadRouteSupabaseIntegration:
    def test_upload_route_uses_supabase_when_configured(self):
        mock_client = MagicMock()
        storage_api = MagicMock()
        mock_client.storage.from_.return_value = storage_api

        supabase_storage = SupabaseMediaStorage(
            supabase_url="https://test.supabase.co",
            service_role_key="mock_key",
            bucket_name="complaint-images",
            client=mock_client
        )
        set_media_storage(supabase_storage)

        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 100
        response = client.post(
            "/api/uploads",
            files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["filename"].endswith(".jpg")
        assert storage_api.upload.called
