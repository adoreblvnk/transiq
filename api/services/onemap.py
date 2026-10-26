"""OneMap API Client for authentic address search and geocoding."""

import os
import time
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

ONEMAP_API_KEY = os.getenv("ONEMAP_API_KEY") or os.getenv("ONEMAP_TOKEN")
ONEMAP_EMAIL = os.getenv("ONEMAP_EMAIL")
ONEMAP_PASSWORD = os.getenv("ONEMAP_PASSWORD")
_cached_token: Optional[str] = None
_token_expiry: float = 0.0


def get_onemap_token() -> Optional[str]:
    """Retrieve or refresh OneMap authentication bearer token or API key."""
    global _cached_token, _token_expiry
    if ONEMAP_API_KEY:
        return ONEMAP_API_KEY

    now = time.time()
    if _cached_token and now < _token_expiry:
        return _cached_token
    if not ONEMAP_EMAIL or not ONEMAP_PASSWORD:
        return None

    try:
        url = "https://www.onemap.gov.sg/api/auth/post/getToken"
        res = requests.post(
            url,
            json={"email": ONEMAP_EMAIL, "password": ONEMAP_PASSWORD},
            timeout=8
        )
        if res.status_code == 200:
            data = res.json()
            _cached_token = data.get("access_token")
            # Cache for 2 days (OneMap tokens typically valid for 3 days)
            _token_expiry = now + 172800
            return _cached_token
    except Exception:
        pass
    return None


def search_address(query: str) -> List[Dict[str, Any]]:
    """Search OneMap for building coordinates by postal code or address."""
    clean_q = query.strip()
    if not clean_q:
        return []

    output = []
    try:
        token = get_onemap_token()
        headers = {"Authorization": token} if token else {}
        url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={clean_q}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            results = res.json().get("results", [])
            for r in results:
                postal = r.get("POSTAL")
                lat = r.get("LATITUDE")
                lon = r.get("LONGITUDE")

                # If it lacks a valid 6-digit postal code, omit from address results
                if postal and postal != "NIL" and len(postal) == 6 and postal.isdigit() and lat and lon:
                    output.append({
                        "postal_code": postal,
                        "address": r.get("ADDRESS", ""),
                        "building": r.get("BUILDING", r.get("SEARCHVAL", "")),
                        "block_no": r.get("BLK_NO", ""),
                        "road_name": r.get("ROAD_NAME", ""),
                        "latitude": float(lat),
                        "longitude": float(lon),
                    })
    except Exception:
        pass

    # Deduplicate results by postal code and building
    seen = set()
    unique_out = []
    for o in output:
        key = (o["postal_code"], o["building"])
        if key not in seen:
            seen.add(key)
            unique_out.append(o)

    return unique_out
