import io
import os
import uuid
from fastapi import UploadFile
from PIL import Image

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pillow-heif not installed
    HEIF_SUPPORTED = False


UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

HEIC_EXTENSIONS = {".heic", ".heif"}


async def save_upload_file(f: UploadFile):
    """
    Persist an uploaded file to disk. HEIC/HEIF sources are converted to JPEG
    because OpenCV cannot read them directly.
    """
    filename = f.filename or "upload"
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    contents = await f.read()
    content_type = (f.content_type or "").lower()

    needs_heic_convert = ext in HEIC_EXTENSIONS or "heic" in content_type

    if needs_heic_convert:
        if not HEIF_SUPPORTED:
            raise ValueError("HEIC uploads require pillow-heif to be installed.")

        image = Image.open(io.BytesIO(contents))
        rgb_image = image.convert("RGB")
        ext = ".jpg"
        path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
        rgb_image.save(path, format="JPEG", quality=95)
        return path

    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext or '.jpg'}")
    with open(path, "wb") as out:
        out.write(contents)
    return path
