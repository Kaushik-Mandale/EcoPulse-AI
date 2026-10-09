import os
import uuid
import time
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from server.utils.config import config
from server.services.whatsapp_service import validate_image_content, MediaValidationError

router = APIRouter(prefix="/api/uploads", tags=["Uploads"])

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

CHUNK_SIZE = 64 * 1024  # 64 KB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

@router.post("")
async def upload_file(file: UploadFile = File(...)):
    # 1. Validate submitted filename extension if present
    orig_filename = file.filename or ""
    raw_ext = os.path.splitext(orig_filename)[1].strip().lower()
    if raw_ext and raw_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{raw_ext}'. Allowed formats: .jpg, .jpeg, .png, .webp"
        )

    # 2. Bounded streaming read to enforce MAX_UPLOAD_SIZE without unbounded memory consumption
    max_size = config.MAX_UPLOAD_SIZE
    chunks = []
    total_bytes = 0

    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_size:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
                    detail=f"File size exceeds maximum allowed limit of {max_size} bytes."
                )
            chunks.append(chunk)
    finally:
        await file.close()

    content = b"".join(chunks)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded."
        )

    # 3. Inspect binary magic bytes and validate MIME type
    try:
        detected_mime, detected_ext = validate_image_content(
            content=content,
            declared_mime_type=file.content_type,
            max_size=max_size
        )
    except MediaValidationError as mve:
        if "exceeds maximum limit" in str(mve).lower():
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
                detail=str(mve)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(mve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {str(e)}"
        )

    # 4. Check consistency between submitted extension and detected binary format
    if raw_ext:
        norm_raw = ".jpg" if raw_ext in (".jpg", ".jpeg") else raw_ext
        norm_det = ".jpg" if detected_ext in (".jpg", ".jpeg") else detected_ext
        if norm_raw != norm_det:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension '{raw_ext}' does not match detected image format '{detected_ext}'."
            )

    # 5. Generate collision-resistant server-controlled filename
    safe_filename = f"img_{int(time.time())}_{uuid.uuid4().hex[:12]}{detected_ext}"
    target_path = os.path.abspath(os.path.join(UPLOAD_DIR, safe_filename))

    # Guard against directory traversal
    if os.path.commonpath([UPLOAD_DIR, target_path]) != UPLOAD_DIR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target file destination."
        )

    # 6. Atomic file write with cleanup on error
    try:
        with open(target_path, "wb") as buffer:
            buffer.write(content)
    except Exception as write_err:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist uploaded image: {str(write_err)}"
        )

    return {"url": f"/uploads/{safe_filename}", "filename": safe_filename}
