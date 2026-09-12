"""
Image Generator Module
------------------------
This module does two things:
1. Converts scene text into a short search query
2. Sends that query to Pexels, downloads a matching real stock photo,
   and fits it to a fixed target resolution for each scene

WHY PEXELS:
Pollinations and Together.ai both turned out to require paid credits
for reliable image generation. Pexels has a genuinely free-forever API
(no credits, no balance to run out of): https://www.pexels.com/api/

IMPORTANT TRADE-OFF:
Pexels does NOT generate AI images from a prompt - it SEARCHES a huge
library of real, licensed stock photos and returns the best match for
your search terms.

WHY WE RESIZE/CROP EVERY IMAGE TO A FIXED SIZE:
Pexels photos come back at inconsistent, often very large sizes.
Feeding oversized images straight into MoviePy's per-frame Ken Burns
zoom effect can exhaust memory during rendering. To avoid this, every
downloaded photo is center-cropped and resized down to a fixed
TARGET_WIDTH x TARGET_HEIGHT canvas right after download.

Get a free Pexels API key at: https://www.pexels.com/api/
"""

import re
from io import BytesIO
import requests
from PIL import Image


PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
FALLBACK_QUERY = "cinematic landscape"

TARGET_WIDTH = 1024
TARGET_HEIGHT = 768


def build_image_prompt(scene_text: str, max_words: int = 8) -> str:
    """
    Convert scene narration text into a short, keyword-style search
    query. Stock photo search works better with a handful of concrete
    keywords than with a full narrated sentence.
    """
    cleaned = re.sub(r"[^\w\s]", "", scene_text.strip())
    words = cleaned.split()
    return " ".join(words[:max_words]) if words else FALLBACK_QUERY


def _search_pexels(query: str, api_key: str, orientation: str = "landscape") -> dict:
    """Run a single Pexels search and return the first photo result (or None)."""
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 1, "orientation": orientation}

    response = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=30)

    if response.status_code == 401:
        raise RuntimeError(
            "Pexels rejected the API key (401 Unauthorized). "
            "Get a free key at https://www.pexels.com/api/ and double check it was copied correctly."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "Pexels rate limit hit (429 Too Many Requests). "
            "The free tier allows 200 requests/hour and 20,000/month - wait a bit and try again."
        )

    if response.status_code != 200:
        raise RuntimeError(f"Pexels search failed: {response.status_code} - {response.text[:200]}")

    data = response.json()
    photos = data.get("photos", [])
    return photos[0] if photos else None


def _fit_and_save_image(image_bytes: bytes, output_path: str, width: int = TARGET_WIDTH, height: int = TARGET_HEIGHT):
    """
    Center-crop the downloaded photo to the target aspect ratio, then
    resize it down to an exact width x height canvas, and save as PNG.
    """
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

    src_ratio = image.width / image.height
    target_ratio = width / height

    if src_ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        left = (image.width - new_width) // 2
        image = image.crop((left, 0, left + new_width, image.height))
    else:
        new_height = int(image.width / target_ratio)
        top = (image.height - new_height) // 2
        image = image.crop((0, top, image.width, top + new_height))

    image = image.resize((width, height), Image.LANCZOS)
    image.save(output_path, "PNG")


def generate_image(scene_text: str, output_path: str, api_key: str):
    """
    Search Pexels for a photo matching scene_text, download it, fit it
    to the fixed target resolution, and save it to output_path. Falls
    back to a broader/generic query if needed.
    """
    if not api_key:
        raise RuntimeError(
            "No Pexels API key provided. Get a free key at https://www.pexels.com/api/ "
            "and paste it into the 'Pexels API key' field."
        )

    query = build_image_prompt(scene_text)
    photo = _search_pexels(query, api_key)

    if photo is None:
        broad_query = " ".join(query.split()[:3]) or FALLBACK_QUERY
        photo = _search_pexels(broad_query, api_key)

    if photo is None:
        photo = _search_pexels(FALLBACK_QUERY, api_key)

    if photo is None:
        raise RuntimeError(f"No Pexels image found for scene text: '{scene_text[:80]}...'")

    image_url = photo["src"]["large2x"]
    img_response = requests.get(image_url, timeout=60)

    if img_response.status_code != 200:
        raise RuntimeError(f"Failed to download image from Pexels: {img_response.status_code}")

    _fit_and_save_image(img_response.content, output_path)


def generate_all_images(scenes: list, output_folder: str, api_key: str = None) -> list:
    """
    Main function: takes list of scenes, finds/downloads one matching
    photo per scene from Pexels, and returns the scenes list updated
    with image_path for each scene.
    """
    for scene in scenes:
        scene_id = scene["scene_id"]
        query = build_image_prompt(scene["text"])
        image_path = f"{output_folder}/scene_{scene_id}.png"

        generate_image(scene["text"], image_path, api_key=api_key)

        scene["image_prompt"] = query
        scene["image_path"] = image_path

    return scenes


if __name__ == "__main__":
    import os
    test_key = os.environ.get("PEXELS_API_KEY")

    test_scenes = [
        {"scene_id": 1, "text": "Pakistan is a beautiful country located in South Asia."},
    ]

    result = generate_all_images(test_scenes, "../static/images", api_key=test_key)
    for scene in result:
        print(f"Scene {scene['scene_id']}: {scene['image_path']}")
        print(f"   Search query used: {scene['image_prompt']}")