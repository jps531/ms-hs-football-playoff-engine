"""Cloudinary image upload helpers."""

import asyncio
import io
import logging
import os
import tempfile
from collections.abc import Callable
from typing import Literal

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

_log = logging.getLogger(__name__)

LogoType = Literal["primary", "secondary", "tertiary"]
HelmetImageType = Literal["left", "right", "photo"]

ALLOWED_UPLOAD_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
# What a file really is (read from its bytes, not the type the client declared) and its extension.
_SNIFFED_TYPES = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
    "GIF": ("image/gif", ".gif"),
}
MAX_UPLOAD_PIXELS = 40_000_000  # far past any photo; refuses decompression bombs


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


def sniff_image(contents: bytes) -> tuple[str, str]:
    """Return ``(mime_type, extension)`` for what *contents* actually is; HTTP 422 unless it's an allowed image.

    The client's declared content type is only a claim: this opens the bytes, so a script or an
    HTML page renamed ``.png`` is refused, as is an image too large in pixels to be a real photo.
    """
    try:
        with Image.open(io.BytesIO(contents)) as img:
            fmt = img.format
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        fmt = None
        width = height = 0
    if fmt not in _SNIFFED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The file isn't a supported image. Allowed: {sorted(ALLOWED_UPLOAD_MIME_TYPES)}",
        )
    if width * height > MAX_UPLOAD_PIXELS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Image dimensions are too large")
    return _SNIFFED_TYPES[fmt]


def save_temp(filename: str | None, contents: bytes, suffix: str | None = None) -> str:
    """Write upload contents to a named temp file (mode 0600) and return its path.

    *suffix* defaults to *filename*'s extension (or ``.png``).
    """
    suffix = suffix or os.path.splitext(filename or "")[1] or ".png"
    tmp = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()
    return tmp.name


async def check_upload(file: UploadFile) -> None:
    """Refuse *file* (HTTP 422) unless it's an allowed image within the size limits, by what its bytes
    are (:func:`sniff_image`); leave it ready to be read again.

    Call it before storing anything about a submission, so a refused file doesn't leave a submission
    with no image behind it. :func:`save_and_upload` checks again as it uploads.
    """
    contents = await file.read()
    validate_upload(file.content_type, len(contents))
    sniff_image(contents)
    await file.seek(0)


async def save_and_upload(file: UploadFile, upload_fn: Callable[[str], str]) -> str:
    """Read, validate, and temp-save *file*, call ``upload_fn(tmp_path)``, then clean up.

    *upload_fn* should be a closure/partial with all upload-specific arguments
    (school, logo_type, submission_id, etc.) already bound except the local file path.
    The file must really be an allowed image (see :func:`sniff_image`), whatever it claims to be;
    the temp file gets the extension of what it is. The upload runs in a worker thread so it
    doesn't stall other requests. The temp file is removed whether or not the upload succeeds.
    """
    contents = await file.read()
    validate_upload(file.content_type, len(contents))
    _, extension = sniff_image(contents)
    tmp_path = save_temp(file.filename, contents, suffix=extension)
    try:
        return await asyncio.to_thread(upload_fn, tmp_path)
    finally:
        os.unlink(tmp_path)


def delete_images(public_ids: list[str]) -> None:  # pragma: no cover - Cloudinary call
    """Delete uploaded images from Cloudinary (best effort: a failure is logged, not raised)."""
    if not public_ids:
        return
    _configure()
    for public_id in public_ids:
        try:
            cloudinary.uploader.destroy(public_id, invalidate=True)
        except Exception as exc:  # noqa: BLE001 - one failed delete shouldn't stop the rest
            _log.warning("cloudinary: couldn't delete %s: %s", public_id, exc)


def _configure() -> None:
    """Configure Cloudinary client from environment variables."""
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
    )


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


def upload_submission_logo(local_path: str, school_name: str, logo_type: LogoType, submission_id: int) -> str:
    """Upload a logo reference for a submission and return the Cloudinary path to store in the DB.

    Path: ``logos/submissions/{logo_type}/{school_normalized}_{submission_id}`` — keyed by
    submission id (not just school+logo_type) so a second pending submission for the same
    school/logo_type never clobbers a prior one's staged reference. References persist
    indefinitely as evidence; they are never promoted/renamed into production — a moderator
    uploads a brand-new asset against a real team_logos row via :func:`upload_team_logo` instead.
    """
    _configure()
    name = school_name.replace(" ", "_")
    public_id = f"logos/submissions/{logo_type}/{name}_{submission_id}"
    cloudinary.uploader.upload(
        local_path,
        public_id=public_id,
        asset_folder=f"logos/submissions/{logo_type}",
        overwrite=True,
        invalidate=True,
    )
    return public_id


def upload_team_logo(local_path: str, school_name: str, logo_type: LogoType, team_logo_id: int) -> str:
    """Upload a published logo asset and return the path to store in team_logos.image_url.

    Path: ``logos/{logo_type}/{school_normalized}_{team_logo_id}``, keyed by team_logos.id,
    since a school can have multiple historical assets per logo_type.
    A genuinely new upload, not a rename of any submitted reference.
    """
    _configure()
    name = school_name.replace(" ", "_")
    public_id = f"logos/{logo_type}/{name}_{team_logo_id}"
    cloudinary.uploader.upload(
        local_path,
        public_id=public_id,
        asset_folder=f"logos/{logo_type}",
        overwrite=True,
        invalidate=True,
    )
    return public_id


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
