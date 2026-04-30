"""Cloudinary image upload helpers."""

import os

import cloudinary
import cloudinary.uploader


def _configure() -> None:
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
    )


def upload_logo(local_path: str, school_name: str) -> str:
    """Upload a school logo and return the path to store in logo_override."""
    _configure()
    public_id = f"logos/primary/{school_name}"
    cloudinary.uploader.upload(local_path, public_id=public_id, overwrite=True, invalidate=True)
    return public_id


def logo_url(path: str) -> str:
    """Assemble a full Cloudinary URL from a stored path.

    Pass-through for legacy full URLs (e.g. old MaxPreps links) and empty strings.
    """
    if not path or path.startswith("http"):
        return path
    base = os.environ.get("CLOUDINARY_BASE_URL", "").rstrip("/")
    return f"{base}/{path}"
