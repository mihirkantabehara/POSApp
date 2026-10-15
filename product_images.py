import os
import tempfile
from io import BytesIO
from pathlib import Path


PRODUCT_IMAGE_DIR = Path(
    os.getenv(
        "PRODUCT_IMAGE_DIR",
        str(Path(__file__).resolve().parent / "product-images"),
    )
).expanduser().resolve()

MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PRODUCT_IMAGE_PIXELS = 25_000_000

_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


def prepare_product_image(data: bytes) -> bytes:
    """Validate and re-encode an uploaded JPEG, PNG, or WebP image."""
    if not data:
        raise ValueError("Choose an image to upload.")
    if len(data) > MAX_PRODUCT_IMAGE_BYTES:
        raise ValueError("Product images must be 5 MB or smaller.")

    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required to upload product images. Install Pillow and retry."
        ) from exc

    try:
        with Image.open(BytesIO(data)) as source:
            image_format = source.format
            if image_format not in _IMAGE_FORMATS:
                raise ValueError("Use a JPEG, PNG, or WebP product image.")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("Animated images are not supported.")
            if source.width * source.height > MAX_PRODUCT_IMAGE_PIXELS:
                raise ValueError("Product images must be 25 megapixels or smaller.")

            source.load()
            image = ImageOps.exif_transpose(source)
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            image = image.convert("RGBA" if has_alpha else "RGB")

            output = BytesIO()
            if image_format == "JPEG":
                if image.mode == "RGBA":
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                image.save(output, format="JPEG", quality=88, optimize=True)
            elif image_format == "PNG":
                image.save(output, format="PNG", optimize=True)
            else:
                image.save(output, format="WEBP", quality=88, method=4)
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded file is not a valid supported image.") from exc

    normalized = output.getvalue()
    if len(normalized) > MAX_PRODUCT_IMAGE_BYTES:
        raise ValueError("The processed product image exceeds the 5 MB limit.")
    return normalized


def product_image_path(product_id: int) -> Path:
    return PRODUCT_IMAGE_DIR / f"{int(product_id)}.image"


def get_product_image_path(product_id: int) -> Path | None:
    if int(product_id) <= 0:
        return None
    path = product_image_path(product_id)
    return path if path.is_file() else None


def product_image_media_type(path: Path) -> str:
    with path.open("rb") as image_file:
        header = image_file.read(12)

    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Stored product image has an unsupported format.")


def save_product_image(product_id: int, image_data: bytes) -> None:
    PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    destination = product_image_path(product_id)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=PRODUCT_IMAGE_DIR,
            prefix=f".{int(product_id)}-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(image_data)

        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def delete_product_image(product_id: int) -> None:
    path = product_image_path(product_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
