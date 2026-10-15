"""Find and prepare lightweight grocery catalogue images from Open Food Facts."""
from __future__ import annotations

from io import BytesIO
import re
from difflib import SequenceMatcher

import requests
from PIL import Image, ImageOps

OFF_HEADERS = {"User-Agent": "GouriSupermartPOS/1.0 (product catalogue image lookup)"}
TIMEOUT = 8
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_SOURCE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_IMAGE_PIXELS = 40_000_000


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _download_image(url: str) -> bytes | None:
    if not url or not url.startswith("https://"):
        return None
    try:
        response = requests.get(url, headers=OFF_HEADERS, timeout=TIMEOUT, stream=True)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            return None
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > MAX_DOWNLOAD_BYTES:
                return None
        # Validate the response is a real image before returning it.
        with Image.open(BytesIO(data)) as im:
            im.verify()
        return bytes(data)
    except Exception:
        return None


def find_grocery_image(product_name: str, barcode: str = "") -> bytes | None:
    """Return a likely Open Food Facts image; avoid unrelated name-only matches."""
    barcode = (barcode or "").strip()
    if barcode:
        try:
            r = requests.get(
                f"https://world.openfoodfacts.org/api/v2/product/{requests.utils.quote(barcode)}.json",
                headers=OFF_HEADERS, timeout=TIMEOUT,
            )
            if r.ok:
                product = r.json().get("product") or {}
                image = product.get("image_front_url") or product.get("image_url")
                if image:
                    found = _download_image(image)
                    if found:
                        return found
        except Exception:
            pass

    name = (product_name or "").strip()
    if len(name) < 3:
        return None
    try:
        r = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={"search_terms": name, "search_simple": 1, "action": "process",
                    "json": 1, "page_size": 8, "fields": "product_name,product_name_en,image_front_url,image_url"},
            headers=OFF_HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        products = r.json().get("products", [])
    except Exception:
        return None

    wanted = _normalise(name)
    wanted_tokens = set(wanted.split())
    ranked = []
    for product in products:
        candidate = _normalise(product.get("product_name_en") or product.get("product_name") or "")
        if not candidate:
            continue
        token_score = len(wanted_tokens & set(candidate.split())) / max(1, len(wanted_tokens))
        ratio = SequenceMatcher(None, wanted, candidate).ratio()
        score = max(ratio, token_score)
        ranked.append((score, product))
    ranked.sort(key=lambda x: x[0], reverse=True)
    for score, product in ranked:
        if score < 0.62:
            continue
        image_url = product.get("image_front_url") or product.get("image_url")
        image = _download_image(image_url)
        if image:
            return image
    return None


def prepare_catalogue_image(image_bytes: bytes, size: int = 320, quality: int = 72) -> bytes:
    """Validate an image and make a small square WebP for the product catalogue."""
    if not image_bytes:
        raise ValueError("Choose an image to upload.")
    if len(image_bytes) > MAX_SOURCE_IMAGE_BYTES:
        raise ValueError("Screenshots and product images must be 20 MB or smaller.")

    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Upload a JPEG, PNG, or WebP screenshot/image.")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("Animated images are not supported.")
            if source.width * source.height > MAX_SOURCE_IMAGE_PIXELS:
                raise ValueError("Images must be 40 megapixels or smaller.")

            source.load()
            image = ImageOps.exif_transpose(source)
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                background.alpha_composite(rgba)
                image = background.convert("RGB")
            else:
                image = image.convert("RGB")
    except ValueError:
        raise
    except (Image.DecompressionBombError, OSError) as exc:
        raise ValueError("The uploaded file is not a valid supported image.") from exc

    for output_size, output_quality in (
        (size, quality),
        (size, 55),
        (size, 40),
        (min(size, 256), 40),
        (min(size, 224), 35),
    ):
        thumbnail = ImageOps.fit(
            image,
            (output_size, output_size),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        output = BytesIO()
        thumbnail.save(
            output,
            format="WEBP",
            quality=output_quality,
            method=6,
        )
        result = output.getvalue()
        if len(result) <= 100 * 1024:
            return result

    raise ValueError("Could not compress this image to the 100 KB catalogue limit.")
