import os
from urllib.parse import urlsplit

import httpx
import pytest

# Ensure tests run hermetically against local database without requiring external network connectivity
os.environ.setdefault("DATABASE_URL", "sqlite:///./ecopulse.db")
os.environ["MEDIA_STORAGE_BACKEND"] = "local"


@pytest.fixture(autouse=True)
def prevent_live_meta_api_requests(monkeypatch):
    """Keep the test suite from sending credentials or requests to Meta."""
    original_get = httpx.Client.get
    original_post = httpx.Client.post

    def is_meta_url(url):
        hostname = (urlsplit(str(url)).hostname or "").lower()
        return hostname == "facebook.com" or hostname.endswith(
            (".facebook.com", ".fbcdn.net", ".fbsbx.com")
        )

    def mocked_get(self, url, *args, **kwargs):
        if is_meta_url(url):
            return httpx.Response(
                503,
                request=httpx.Request("GET", str(url)),
                json={"error": {"message": "Meta API is mocked in tests"}},
            )
        return original_get(self, url, *args, **kwargs)

    def mocked_post(self, url, *args, **kwargs):
        if is_meta_url(url):
            return httpx.Response(
                200,
                request=httpx.Request("POST", str(url)),
                json={"messages": [{"id": "wamid.mocked-test-send"}]},
            )
        return original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", mocked_get)
    monkeypatch.setattr(httpx.Client, "post", mocked_post)
