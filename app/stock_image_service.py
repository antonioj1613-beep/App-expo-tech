"""
Stock photo lookup for photo-description lesson items (Listening Part 1,
Writing photo-sentence tasks) — Pexels API.

Optional integration, same "optional key, graceful degradation" pattern as
GEMINI_API_KEY/Ollama elsewhere in this app: no PEXELS_API_KEY set, no HTTP
call is even attempted, and the caller leaves image_url/image_credit blank
rather than fabricating a placeholder. Pexels' free tier requires only a
signup (no billing) and its license permits hotlinking without mandatory
attribution — image_credit is stored anyway as good practice.

Called only from the seed management commands today, never from a live user
request — a slow or failed lookup at seed time is fine to just skip.
"""

from __future__ import annotations

import os

import httpx

PEXELS_API_BASE_URL = "https://api.pexels.com/v1/search"
LOOKUP_TIMEOUT_SECONDS = 10.0


def get_stock_image(query: str) -> dict | None:
    """Look up one licensed stock photo for `query`.

    Returns {"url": ..., "credit": ...} or None on any failure (no key,
    network error, no results) — caller leaves image_url/image_credit blank."""
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key or not query:
        return None

    try:
        response = httpx.get(
            PEXELS_API_BASE_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return None
        photos = response.json().get("photos") or []
        if not photos:
            return None
        photo = photos[0]
        url = (photo.get("src") or {}).get("large")
        if not url:
            return None
        photographer = str(photo.get("photographer", "")).strip()
        credit = f"Photo by {photographer} on Pexels" if photographer else "Photo via Pexels"
        return {"url": url, "credit": credit}
    except (httpx.HTTPError, OSError, KeyError, ValueError):
        return None
