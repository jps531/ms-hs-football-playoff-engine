"""Tests for image URL assembly and Cloudinary upload helpers in image_helpers.py."""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.helpers.image_helpers import (
    MAX_UPLOAD_FILE_BYTES,
    _configure,
    logo_url,
    promote_submission_logo,
    save_temp,
    upload_helmet,
    upload_logo,
    upload_submission_helmet_image,
    upload_submission_logo,
    validate_upload,
)


@pytest.fixture
def cloudinary_env(monkeypatch):
    """Set required Cloudinary env vars for tests that call _configure."""
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "testcloud")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "testkey")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "testsecret")


class TestConfigure:
    """_configure wires up the Cloudinary client from environment variables."""

    def test_calls_cloudinary_config_with_env_vars(self, cloudinary_env):
        """cloudinary.config is called with values read from the environment."""
        with patch("cloudinary.config") as mock_config:
            _configure()
        mock_config.assert_called_once_with(
            cloud_name="testcloud",
            api_key="testkey",
            api_secret="testsecret",
        )

    def test_missing_env_var_raises(self, monkeypatch):
        """KeyError is raised when a required env var is absent."""
        monkeypatch.delenv("CLOUDINARY_CLOUD_NAME", raising=False)
        monkeypatch.setenv("CLOUDINARY_API_KEY", "testkey")
        monkeypatch.setenv("CLOUDINARY_API_SECRET", "testsecret")
        with pytest.raises(KeyError):
            _configure()


class TestUploadLogo:
    """upload_logo uploads to logos/{logo_type}/{school} and returns the public_id."""

    def test_returns_expected_public_id(self, cloudinary_env):
        """Return value is the Cloudinary public_id for the uploaded logo."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_logo("/tmp/logo.png", "Taylorsville", "primary")
        assert result == "logos/primary/Taylorsville"

    def test_spaces_replaced_with_underscores(self, cloudinary_env):
        """School names with spaces are normalized to underscores in the path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_logo("/tmp/logo.png", "South Panola", "secondary")
        assert result == "logos/secondary/South_Panola"

    def test_default_logo_type_is_primary(self, cloudinary_env):
        """Omitting logo_type defaults to 'primary'."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_logo("/tmp/logo.png", "Taylorsville")
        assert result == "logos/primary/Taylorsville"

    def test_upload_called_with_correct_args(self, cloudinary_env):
        """cloudinary.uploader.upload receives the correct public_id and folder."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload") as mock_upload:
            upload_logo("/tmp/logo.png", "Taylorsville", "primary")
        mock_upload.assert_called_once_with(
            "/tmp/logo.png",
            public_id="logos/primary/Taylorsville",
            asset_folder="logos/primary",
            overwrite=True,
            invalidate=True,
        )


class TestUploadHelmet:
    """upload_helmet uploads to helmets/{image_type}/{school}_{year}_{helmet_id}."""

    def test_returns_expected_public_id(self, cloudinary_env):
        """Return value encodes school, year, and helmet_id in the path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_helmet("/tmp/helmet.png", "Taylorsville", 2023, "left", 42)
        assert result == "helmets/left/Taylorsville_2023_42"

    def test_spaces_replaced_with_underscores(self, cloudinary_env):
        """School names with spaces are normalized to underscores in the path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_helmet("/tmp/helmet.png", "South Panola", 2022, "right", 7)
        assert result == "helmets/right/South_Panola_2022_7"

    def test_upload_called_with_correct_args(self, cloudinary_env):
        """cloudinary.uploader.upload receives the correct public_id and folder."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload") as mock_upload:
            upload_helmet("/tmp/helmet.png", "Taylorsville", 2023, "photo", 1)
        mock_upload.assert_called_once_with(
            "/tmp/helmet.png",
            public_id="helmets/photo/Taylorsville_2023_1",
            asset_folder="helmets/photo",
            overwrite=True,
            invalidate=True,
        )


class TestUploadSubmissionLogo:
    """upload_submission_logo stages to logos/submissions/{logo_type}/{school}."""

    def test_returns_staged_path(self, cloudinary_env):
        """Return value is the staged Cloudinary path (not the production path)."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_submission_logo("/tmp/logo.png", "Taylorsville", "primary")
        assert result == "logos/submissions/primary/Taylorsville"

    def test_spaces_replaced_with_underscores(self, cloudinary_env):
        """School names with spaces are normalized to underscores in the path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_submission_logo("/tmp/logo.png", "South Panola", "tertiary")
        assert result == "logos/submissions/tertiary/South_Panola"

    def test_upload_called_with_correct_args(self, cloudinary_env):
        """cloudinary.uploader.upload receives the correct staged public_id and folder."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload") as mock_upload:
            upload_submission_logo("/tmp/logo.png", "Taylorsville", "secondary")
        mock_upload.assert_called_once_with(
            "/tmp/logo.png",
            public_id="logos/submissions/secondary/Taylorsville",
            asset_folder="logos/submissions/secondary",
            overwrite=True,
            invalidate=True,
        )


class TestPromoteSubmissionLogo:
    """promote_submission_logo renames staged path to production path via Cloudinary rename."""

    def test_returns_production_path(self, cloudinary_env):
        """Return value is the production path after promotion."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.rename"):
            result = promote_submission_logo("logos/submissions/primary/Taylorsville", "primary")
        assert result == "logos/primary/Taylorsville"

    def test_tertiary_logo_type(self, cloudinary_env):
        """Tertiary logo type is preserved in the promoted production path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.rename"):
            result = promote_submission_logo("logos/submissions/tertiary/West_Point", "tertiary")
        assert result == "logos/tertiary/West_Point"

    def test_rename_called_with_correct_args(self, cloudinary_env):
        """cloudinary.uploader.rename receives the staged and production paths."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.rename") as mock_rename:
            promote_submission_logo("logos/submissions/secondary/South_Panola", "secondary")
        mock_rename.assert_called_once_with(
            "logos/submissions/secondary/South_Panola",
            "logos/secondary/South_Panola",
            overwrite=True,
            invalidate=True,
        )


class TestUploadSubmissionHelmetImage:
    """upload_submission_helmet_image stages to helmets/submissions/{school}_{id}_{index}."""

    def test_returns_expected_path(self, cloudinary_env):
        """Return value encodes school, submission_id, and index in the path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_submission_helmet_image("/tmp/img.png", "Taylorsville", 5, 0)
        assert result == "helmets/submissions/Taylorsville_5_0"

    def test_spaces_replaced_with_underscores(self, cloudinary_env):
        """School names with spaces are normalized to underscores in the path."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload"):
            result = upload_submission_helmet_image("/tmp/img.png", "South Panola", 12, 3)
        assert result == "helmets/submissions/South_Panola_12_3"

    def test_upload_called_with_correct_args(self, cloudinary_env):
        """cloudinary.uploader.upload receives the correct staged public_id and folder."""
        with patch("cloudinary.config"), patch("cloudinary.uploader.upload") as mock_upload:
            upload_submission_helmet_image("/tmp/img.png", "Taylorsville", 7, 2)
        mock_upload.assert_called_once_with(
            "/tmp/img.png",
            public_id="helmets/submissions/Taylorsville_7_2",
            asset_folder="helmets/submissions",
            overwrite=True,
            invalidate=True,
        )


class TestValidateUpload:
    """validate_upload rejects disallowed MIME types and oversized files."""

    def test_allowed_type_and_size_passes(self):
        """A recognised image type under the size limit raises nothing."""
        validate_upload("image/png", 1024)

    def test_oversized_file_raises_422(self):
        """A file over MAX_UPLOAD_FILE_BYTES raises HTTP 422."""
        with pytest.raises(HTTPException) as exc_info:
            validate_upload("image/png", MAX_UPLOAD_FILE_BYTES + 1)
        assert exc_info.value.status_code == 422

    def test_disallowed_mime_type_raises_422(self):
        """A MIME type outside the allowed set raises HTTP 422."""
        with pytest.raises(HTTPException) as exc_info:
            validate_upload("application/pdf", 1024)
        assert exc_info.value.status_code == 422

    def test_none_content_type_raises_422(self):
        """A missing content type (None) is treated as disallowed."""
        with pytest.raises(HTTPException):
            validate_upload(None, 1024)

    def test_size_exactly_at_limit_passes(self):
        """A file exactly at MAX_UPLOAD_FILE_BYTES is not considered oversized."""
        validate_upload("image/png", MAX_UPLOAD_FILE_BYTES)


class TestSaveTemp:
    """save_temp writes contents to a temp file and returns its path."""

    def test_writes_contents_to_returned_path(self):
        """The file at the returned path contains exactly the given bytes."""
        path = save_temp("photo.png", b"fake-image-bytes")
        try:
            with open(path, "rb") as f:
                assert f.read() == b"fake-image-bytes"
        finally:
            os.unlink(path)

    def test_suffix_derived_from_filename(self):
        """The temp file suffix matches the original filename's extension."""
        path = save_temp("helmet.webp", b"data")
        try:
            assert path.endswith(".webp")
        finally:
            os.unlink(path)

    def test_missing_filename_defaults_to_png_suffix(self):
        """A None/empty filename falls back to a .png suffix."""
        path = save_temp(None, b"data")
        try:
            assert path.endswith(".png")
        finally:
            os.unlink(path)


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
