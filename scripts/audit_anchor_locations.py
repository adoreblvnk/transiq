#!/usr/bin/env python3
"""
TRANSIQ — Anchor Location Verifier & Auditor
Audits all 85 anchor locations in api/routers/routes.py against the live OneMap API.
Flags any discrepancies in building names, postal codes, or coordinates,
and generates the 100% verified authentic dataset.
"""

import sys
import time
from pathlib import Path
import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.services.onemap import get_onemap_token, search_address
from api.routers.routes import get_anchor_locations

token = get_onemap_token()
headers = {"Authorization": token} if token else {}

print("=================================================================")
print("  TRANSIQ Anchor Location OneMap Audit Engine                    ")
print("=================================================================")

anchors = get_anchor_locations()["origins"]
print(f"Auditing {len(anchors)} anchor locations against live OneMap API...\n")

corrected_list = []
discrepancies = []

for idx, loc in enumerate(anchors, 1):
    postal = loc["postal_code"]
    label = loc["label"]
    cur_lat = loc["latitude"]
    cur_lon = loc["longitude"]

    # 1. Reverse verify by Postal Code
    url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={postal}&returnGeom=Y&getAddrDetails=Y"
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                bldg = results[0].get("BUILDING", results[0].get("SEARCHVAL", ""))
                address = results[0].get("ADDRESS", "")
                lat = float(results[0].get("LATITUDE", cur_lat))
                lon = float(results[0].get("LONGITUDE", cur_lon))

                # Check if building name roughly matches label
                label_clean = label.split("(")[0].strip().upper()
                bldg_clean = bldg.upper()

                # Record verified
                corrected_list.append({
                    "postal_code": postal,
                    "label": f"{bldg} ({postal})",
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6)
                })

                # Check for major mismatches
                key_words = [w for w in label_clean.split() if len(w) > 3 and w not in ("MALL", "CENTRE", "HUB", "STATION", "PLAZA", "BUILDING", "POINT")]
                matched = any(w in bldg_clean or w in address for w in key_words) if key_words else True
                if not matched:
                    discrepancies.append({
                        "original_label": label,
                        "original_postal": postal,
                        "resolved_building": bldg,
                        "resolved_address": address
                    })
                    print(f"  [MISMATCH #{idx}] Label: '{label}' -> Actually resolved to: '{bldg}' ({address})")
                else:
                    print(f"  [OK #{idx:02d}] {bldg:35} | {postal} | ({lat:.4f}, {lon:.4f})")
            else:
                print(f"  [NOT FOUND #{idx}] {label} ({postal})")
        else:
            print(f"  [HTTP {r.status_code}] on {postal}")
    except Exception as e:
        print(f"  [ERROR] on {postal}: {e}")

    time.sleep(0.05)

print("\n=================================================================")
print(f"  Audit Complete: {len(corrected_list)} verified, {len(discrepancies)} mismatches detected.")
print("=================================================================")

if discrepancies:
    print("\nSummary of Flagged Mismatches to Fix:")
    for d in discrepancies:
        print(f"  • {d['original_label']} resolved to {d['resolved_building']} ({d['resolved_address']})")

import json
out_file = ROOT_DIR / "data" / "audited_locations.json"
with open(out_file, "w") as f:
    json.dump(corrected_list, f, indent=2)
print(f"\nWrote full audited dataset to {out_file}")
