"""Cloudinary image upload helpers."""

import os
import tempfile
from collections.abc import Callable
from typing import Literal

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile, status

LogoType = Literal["primary", "secondary", "tertiary"]
HelmetImageType = Literal["left", "right", "photo"]

ALLOWED_UPLOAD_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_upload(content_type: str | None, size: int) -> None:
    """Raise HTTP 422 if *content_type*/*size* describe a disallowed image upload."""
    if size > MAX_UPLOAD_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_FILE_BYTES // 1024 // 1024} MB",
        )
    if content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported file type '{content_type}'. Allowed: {sorted(ALLOWED_UPLOAD_MIME_TYPES)}",
        )


def save_temp(filename: str | None, contents: bytes) -> str:
    """Write upload contents to a named temp file (mode 0600) and return its path."""
    suffix = os.path.splitext(filename or "")[1] or ".png"
    tmp = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()
    return tmp.name


async def save_and_upload(file: UploadFile, upload_fn: Callable[[str], str]) -> str:
    """Read, validate, and temp-save *file*, call ``upload_fn(tmp_path)``, then clean up.

    *upload_fn* should be a closure/partial with all upload-specific arguments
    (school, logo_type, submission_id, etc.) already bound except the local file path.
    The temp file is removed whether or not the upload succeeds.
    """
    contents = await file.read()
    validate_upload(file.content_type, len(contents))
    tmp_path = save_temp(file.filename, contents)
    try:
        return upload_fn(tmp_path)
    finally:
        os.unlink(tmp_path)


def _configure() -> None:
    """Configure Cloudinary client from environment variables."""
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


def upload_helmet(local_path: str, school_name: str, year: int, image_type: HelmetImageType, helmet_id: int) -> str:
    """Upload a helmet image and return the path to store in the DB."""
    _configure()
    name = school_name.replace(" ", "_")
    public_id = f"helmets/{image_type}/{name}_{year}_{helmet_id}"
    cloudinary.uploader.upload(
        local_path,
        public_id=public_id,
        asset_folder=f"helmets/{image_type}",
        overwrite=True,
        invalidate=True,
    )
    return public_id


def upload_submission_logo(local_path: str, school_name: str, logo_type: LogoType) -> str:
    """Upload a logo to the staging area and return the Cloudinary path to store in the DB.

    Staged path: ``logos/submissions/{logo_type}/{school_normalized}``.
    Call :func:`promote_submission_logo` after moderator approval to move it to production.
    """
    _configure()
    name = school_name.replace(" ", "_")
    public_id = f"logos/submissions/{logo_type}/{name}"
    cloudinary.uploader.upload(
        local_path,
        public_id=public_id,
        asset_folder=f"logos/submissions/{logo_type}",
        overwrite=True,
        invalidate=True,
    )
    return public_id


def promote_submission_logo(staging_path: str, logo_type: LogoType) -> str:
    """Rename a staged logo from ``logos/submissions/…`` to the live ``logos/…`` folder.

    Uses Cloudinary's server-side rename so there is no window where the asset is missing.
    Returns the new production path.
    """
    _configure()
    school_segment = staging_path.split("/")[-1]
    target_path = f"logos/{logo_type}/{school_segment}"
    cloudinary.uploader.rename(
        staging_path,
        target_path,
        overwrite=True,
        invalidate=True,
    )
    return target_path


def upload_submission_helmet_image(
    local_path: str,
    school_name: str,
    submission_id: int,
    index: int,
) -> str:
    """Upload one reference image for a helmet submission and return the Cloudinary path.

    Path: ``helmets/submissions/{school_normalized}_{submission_id}_{index}``.
    These images are used by the moderator to create a helmet mockup; they are never
    promoted to a production path automatically.
    """
    _configure()
    name = school_name.replace(" ", "_")
    public_id = f"helmets/submissions/{name}_{submission_id}_{index}"
    cloudinary.uploader.upload(
        local_path,
        public_id=public_id,
        asset_folder="helmets/submissions",
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
