"""Tests for image URL assembly in image_helpers.py."""

import pytest

from backend.helpers.image_helpers import logo_url


class TestLogoUrl:
    """logo_url assembles a full Cloudinary URL from a stored path."""

    def test_empty_string_passthrough(self):
        """Empty string returns empty string unchanged."""
        assert logo_url("") == ""

    def test_full_http_url_passthrough(self):
        """Legacy full http:// URLs are returned unchanged."""
        url = "http://cdn.maxpreps.com/logos/taylorsville.png"
        assert logo_url(url) == url

    def test_full_https_url_passthrough(self):
        """Legacy full https:// URLs are returned unchanged."""
        url = "https://cdn.maxpreps.com/logos/taylorsville.png"
        assert logo_url(url) == url

    def test_path_assembled_with_base_url(self, monkeypatch):
        """A bare path is prefixed with CLOUDINARY_BASE_URL."""
        monkeypatch.setenv("CLOUDINARY_BASE_URL", "https://res.cloudinary.com/mycloud/image/upload")
        assert logo_url("logos/primary/Taylorsville") == (
            "https://res.cloudinary.com/mycloud/image/upload/logos/primary/Taylorsville"
        )

    def test_trailing_slash_on_base_url_is_stripped(self, monkeypatch):
        """Trailing slash on CLOUDINARY_BASE_URL does not produce a double slash."""
        monkeypatch.setenv("CLOUDINARY_BASE_URL", "https://res.cloudinary.com/mycloud/image/upload/")
        assert logo_url("logos/primary/Taylorsville") == (
            "https://res.cloudinary.com/mycloud/image/upload/logos/primary/Taylorsville"
        )

    def test_missing_base_url_env_var(self, monkeypatch):
        """Missing CLOUDINARY_BASE_URL produces a leading-slash URL rather than raising."""
        monkeypatch.delenv("CLOUDINARY_BASE_URL", raising=False)
        assert logo_url("logos/primary/Taylorsville") == "/logos/primary/Taylorsville"
