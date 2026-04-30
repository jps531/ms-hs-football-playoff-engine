"""Cloudinary image upload helpers."""

import os
from typing import Literal

import cloudinary
import cloudinary.uploader

LogoType = Literal["primary", "secondary", "tertiary"]


def _configure() -> None:
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
    )


def upload_logo(local_path: str, school_name: str, logo_type: LogoType = "primary") -> str:
    """Upload a school logo and return the path to store in the DB."""
    _configure()
    public_id = f"logos/{logo_type}/{school_name.replace(' ', '_')}"
    cloudinary.uploader.upload(
        local_path,
        public_id=public_id,
        asset_folder=f"logos/{logo_type}",
        overwrite=True,
        invalidate=True,
    )
    return public_id


def logo_url(path: str) -> str:
    """Assemble a full Cloudinary URL from a stored path.

    Pass-through for legacy full URLs (e.g. old MaxPreps links) and empty strings.
    """
    if not path or path.startswith("http"):
        return path
    base = os.environ.get("CLOUDINARY_BASE_URL", "").rstrip("/")
    return f"{base}/{path}"
