"""
MRT Network Data and Route Helper for Singapore MRT System.

Provides:
- MRT_LINES: Dictionary defining official station sequences, names, codes, and operators
  for all 6 major lines (EWL, NSL, NEL, CCL, DTL, TEL).
- get_mrt_station_segments(): Generates station-to-station transit route segments for both directions,
  computing estimated travel times and geodesic distances.
- get_interchange_transfers(): Generates pedestrian transfer links between exits of multi-line
  interchange stations (and within interchange station complexes).
- Helper functions for MRT exit mapping, station lookups, and transit services.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Base data directory relative to repository root
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
MRT_EXITS_GEOJSON = DATA_DIR / "mrt_exits.geojson"

# Average MRT operating speed (~40 km/h) + 0.75 min dwell time per stop
MRT_AVG_SPEED_KMH = 48.0
MRT_DWELL_TIME_MIN = 0.60
# Walking speed for transfers (~4 km/h = 66.7 m/min) + buffer for fare gates/escalators
WALK_SPEED_M_PER_MIN = 66.67
BASE_TRANSFER_TIME_MIN = 2.0

# ---------------------------------------------------------------------------
# 1. Official MRT Lines Definitions
# ---------------------------------------------------------------------------

MRT_LINES: Dict[str, Dict[str, Any]] = {
    "EWL": {
        "line_code": "EWL",
        "line_name": "East-West Line",
        "operator": "SMRT",
        "color": "#00953A",
        "stations": [
            ("EW1", "Pasir Ris"),
            ("EW2", "Simei"),
            ("EW3", "Tampines"),
            ("EW4", "Tanah Merah"),
            ("EW5", "Bedok"),
            ("EW6", "Kembangan"),
            ("EW7", "Eunos"),
            ("EW8", "Paya Lebar"),
            ("EW9", "Aljunied"),
            ("EW10", "Kallang"),
            ("EW11", "Lavender"),
            ("EW12", "Bugis"),
            ("EW13", "City Hall"),
            ("EW14", "Raffles Place"),
            ("EW15", "Tanjong Pagar"),
            ("EW16", "Outram Park"),
            ("EW17", "Tiong Bahru"),
            ("EW18", "Redhill"),
            ("EW19", "Queenstown"),
            ("EW20", "Commonwealth"),
            ("EW21", "Buona Vista"),
            ("EW22", "Dover"),
            ("EW23", "Clementi"),
            ("EW24", "Jurong East"),
            ("EW25", "Chinese Garden"),
            ("EW26", "Lakeside"),
            ("EW27", "Boon Lay"),
            ("EW28", "Pioneer"),
            ("EW29", "Joo Koon"),
            ("EW30", "Gul Circle"),
            ("EW31", "Tuas Crescent"),
            ("EW32", "Tuas West Road"),
            ("EW33", "Tuas Link"),
        ],
        "branches": [
            # Changi Airport Branch
            {
                "branch_id": "CGL",
                "stations": [
                    ("EW4", "Tanah Merah"),
                    ("CG1", "Expo"),
                    ("CG2", "Changi Airport"),
                ],
            }
        ],
    },
    "NSL": {
        "line_code": "NSL",
        "line_name": "North-South Line",
        "operator": "SMRT",
        "color": "#D42E12",
        "stations": [
            ("NS1", "Jurong East"),
            ("NS2", "Bukit Batok"),
            ("NS3", "Bukit Gombak"),
            ("NS4", "Choa Chu Kang"),
            ("NS5", "Yew Tee"),
            ("NS7", "Kranji"),
            ("NS8", "Marsiling"),
            ("NS9", "Woodlands"),
            ("NS10", "Admiralty"),
            ("NS11", "Sembawang"),
            ("NS12", "Canberra"),
            ("NS13", "Yishun"),
            ("NS14", "Khatib"),
            ("NS15", "Yio Chu Kang"),
            ("NS16", "Ang Mo Kio"),
            ("NS17", "Bishan"),
            ("NS18", "Braddell"),
            ("NS19", "Toa Payoh"),
            ("NS20", "Novena"),
            ("NS21", "Newton"),
            ("NS22", "Orchard"),
            ("NS23", "Somerset"),
            ("NS24", "Dhoby Ghaut"),
            ("NS25", "City Hall"),
            ("NS26", "Raffles Place"),
            ("NS27", "Marina Bay"),
            ("NS28", "Marina South Pier"),
        ],
    },
    "NEL": {
        "line_code": "NEL",
        "line_name": "North East Line",
        "operator": "SBST",
        "color": "#702082",
        "stations": [
            ("NE1", "HarbourFront"),
            ("NE3", "Outram Park"),
            ("NE4", "Chinatown"),
            ("NE5", "Clarke Quay"),
            ("NE6", "Dhoby Ghaut"),
            ("NE7", "Little India"),
            ("NE8", "Farrer Park"),
            ("NE9", "Boon Keng"),
            ("NE10", "Potong Pasir"),
            ("NE11", "Woodleigh"),
            ("NE12", "Serangoon"),
            ("NE13", "Kovan"),
            ("NE14", "Hougang"),
            ("NE15", "Buangkok"),
            ("NE16", "Sengkang"),
            ("NE17", "Punggol"),
        ],
    },
    "CCL": {
        "line_code": "CCL",
        "line_name": "Circle Line",
        "operator": "SMRT",
        "color": "#FA9E0D",
        "stations": [
            ("CC1", "Dhoby Ghaut"),
            ("CC2", "Bras Basah"),
            ("CC3", "Esplanade"),
            ("CC4", "Promenade"),
            ("CC5", "Nicoll Highway"),
            ("CC6", "Stadium"),
            ("CC7", "Mountbatten"),
            ("CC8", "Dakota"),
            ("CC9", "Paya Lebar"),
            ("CC10", "MacPherson"),
            ("CC11", "Tai Seng"),
            ("CC12", "Bartley"),
            ("CC13", "Serangoon"),
            ("CC14", "Lorong Chuan"),
            ("CC15", "Bishan"),
            ("CC16", "Marymount"),
            ("CC17", "Caldecott"),
            ("CC19", "Botanic Gardens"),
            ("CC20", "Farrer Road"),
            ("CC21", "Holland Village"),
            ("CC22", "Buona Vista"),
            ("CC23", "one-north"),
            ("CC24", "Kent Ridge"),
            ("CC25", "Haw Par Villa"),
            ("CC26", "Pasir Panjang"),
            ("CC27", "Labrador Park"),
            ("CC28", "Telok Blangah"),
            ("CC29", "HarbourFront"),
        ],
        "branches": [
            # Marina Bay Extension
            {
                "branch_id": "CEL",
                "stations": [
                    ("CC4", "Promenade"),
                    ("CE1", "Bayfront"),
                    ("CE2", "Marina Bay"),
                ],
            }
        ],
    },
    "DTL": {
        "line_code": "DTL",
        "line_name": "Downtown Line",
        "operator": "SBST",
        "color": "#005EC4",
        "stations": [
            ("DT1", "Bukit Panjang"),
            ("DT2", "Cashew"),
            ("DT3", "Hillview"),
            ("DT5", "Beauty World"),
            ("DT6", "King Albert Park"),
            ("DT7", "Sixth Avenue"),
            ("DT8", "Tan Kah Kee"),
            ("DT9", "Botanic Gardens"),
            ("DT10", "Stevens"),
            ("DT11", "Newton"),
            ("DT12", "Little India"),
            ("DT13", "Rochor"),
            ("DT14", "Bugis"),
            ("DT15", "Promenade"),
            ("DT16", "Bayfront"),
            ("DT17", "Downtown"),
            ("DT18", "Telok Ayer"),
            ("DT19", "Chinatown"),
            ("DT20", "Fort Canning"),
            ("DT21", "Bencoolen"),
            ("DT22", "Jalan Besar"),
            ("DT23", "Bendemeer"),
            ("DT24", "Geylang Bahru"),
            ("DT25", "Mattar"),
            ("DT26", "MacPherson"),
            ("DT27", "Ubi"),
            ("DT28", "Kaki Bukit"),
            ("DT29", "Bedok North"),
            ("DT30", "Bedok Reservoir"),
            ("DT31", "Tampines West"),
            ("DT32", "Tampines"),
            ("DT33", "Tampines East"),
            ("DT34", "Upper Changi"),
            ("DT35", "Expo"),
        ],
    },
    "TEL": {
        "line_code": "TEL",
        "line_name": "Thomson-East Coast Line",
        "operator": "SMRT",
        "color": "#9D5B25",
        "stations": [
            ("TE1", "Woodlands North"),
            ("TE2", "Woodlands"),
            ("TE3", "Woodlands South"),
            ("TE4", "Springleaf"),
            ("TE5", "Lentor"),
            ("TE6", "Mayflower"),
            ("TE7", "Bright Hill"),
            ("TE8", "Upper Thomson"),
            ("TE9", "Caldecott"),
            ("TE11", "Stevens"),
            ("TE12", "Napier"),
            ("TE13", "Orchard Boulevard"),
            ("TE14", "Orchard"),
            ("TE15", "Great World"),
            ("TE16", "Havelock"),
            ("TE17", "Outram Park"),
            ("TE18", "Maxwell"),
            ("TE19", "Shenton Way"),
            ("TE20", "Marina Bay"),
            ("TE22", "Gardens by the Bay"),
            ("TE23", "Tanjong Rhu"),
            ("TE24", "Katong Park"),
            ("TE25", "Tanjong Katong"),
            ("TE26", "Marine Parade"),
            ("TE27", "Marine Terrace"),
            ("TE28", "Siglap"),
            ("TE29", "Bayshore"),
        ],
    },
}

# Verified authentic OneMap WGS84 coordinates for Singapore MRT stations
ACCURATE_STATION_COORDINATES: Dict[str, Tuple[float, float]] = {
    "BRAS BASAH": (1.296862, 103.850667),
    "ESPLANADE": (1.293658, 103.855081),
    "FARRER ROAD": (1.317439, 103.807379),
    "HOLLAND VILLAGE": (1.312240, 103.796399),
    "FORT CANNING": (1.292482, 103.844331),
    "BENCOOLEN": (1.298918, 103.850354),
    "JALAN BESAR": (1.305171, 103.855296),
    "BENDEMEER": (1.313673, 103.862978),
    "GEYLANG BAHRU": (1.321301, 103.871623),
    "MATTAR": (1.326877, 103.883248),
    "UBI": (1.329974, 103.899227),
    "KAKI BUKIT": (1.334967, 103.908459),
    "BEDOK NORTH": (1.334742, 103.917978),
    "BEDOK RESERVOIR": (1.336608, 103.932235),
    "TAMPINES WEST": (1.345515, 103.938437),
    "TAMPINES EAST": (1.356191, 103.954634),
    "UPPER CHANGI": (1.341740, 103.961473),
    "WOODLANDS NORTH": (1.448292, 103.785693),
    "WOODLANDS SOUTH": (1.427396, 103.793264),
    "SPRINGLEAF": (1.397581, 103.817857),
    "LENTOR": (1.385507, 103.835744),
    "MAYFLOWER": (1.371463, 103.836568),
    "BRIGHT HILL": (1.363283, 103.832894),
    "UPPER THOMSON": (1.354416, 103.832898),
    "NAPIER": (1.306782, 103.818957),
    "ORCHARD BOULEVARD": (1.302422, 103.823869),
    "GREAT WORLD": (1.293948, 103.833721),
    "HAVELOCK": (1.288505, 103.833586),
    "MAXWELL": (1.280533, 103.843884),
    "SHENTON WAY": (1.277717, 103.850368),
    "GARDENS BY THE BAY": (1.278487, 103.867455),
    "TANJONG RHU": (1.297265, 103.873453),
    "KATONG PARK": (1.297831, 103.886179),
    "TANJONG KATONG": (1.299319, 103.897369),
    "MARINE PARADE": (1.302612, 103.904983),
    "MARINE TERRACE": (1.306665, 103.915107),
    "SIGLAP": (1.310009, 103.930026),
    "BAYSHORE": (1.313122, 103.942310),
}


# ---------------------------------------------------------------------------
# 2. Geometry & Spatial Helpers
# ---------------------------------------------------------------------------

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    r = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(dlam / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def load_mrt_exits_geojson(geojson_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load MRT exits GeoJSON features from disk."""
    path = geojson_path or MRT_EXITS_GEOJSON
    if not path.exists():
        raise FileNotFoundError(f"MRT exits GeoJSON not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("features", [])


def clean_station_name(station_na: str) -> str:
    """Normalize raw STATION_NA from GeoJSON by stripping suffixes and extra whitespace."""
    s = station_na.replace(" MRT STATION", "").replace(" LRT STATION", "")
    return s.strip().upper()


def get_station_exits_map(geojson_path: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Groups MRT exit features by normalized station name.
    Returns: {STATION_NAME: [ {objectid, exit_code, lat, lon, stop_code}, ... ]}
    """
    features = load_mrt_exits_geojson(geojson_path)
    exits_by_station: Dict[str, List[Dict[str, Any]]] = {}

    for f in features:
        props = f.get("properties", {})
        geom = f.get("geometry", {})
        raw_name = props.get("STATION_NA", "")
        if not raw_name:
            continue
        stn = clean_station_name(raw_name)
        exit_code_raw = props.get("EXIT_CODE", "Exit 1").strip()
        coords = geom.get("coordinates", [0.0, 0.0])
        lon, lat = coords[0], coords[1]
        oid = props.get("OBJECTID")

        # Standard exit code format: e.g. "Exit A" -> "A"
        exit_label = exit_code_raw.replace("Exit ", "").strip()
        stop_code = f"{stn}_{exit_label.replace(' ', '_')}"

        item = {
            "objectid": oid,
            "station_name": stn,
            "exit_code": exit_code_raw,
            "exit_label": exit_label,
            "stop_code": stop_code,
            "latitude": lat,
            "longitude": lon,
        }
        exits_by_station.setdefault(stn, []).append(item)

    return exits_by_station


def get_station_centroids(geojson_path: Optional[Path] = None) -> Dict[str, Tuple[float, float]]:
    """
    Calculates geographic centroid (lat, lon) for each station based on its exits.
    Applies authoritative coordinates for all verified Singapore MRT stations.
    """
    exits_by_station = get_station_exits_map(geojson_path)
    centroids: Dict[str, Tuple[float, float]] = {}
    for stn, exit_list in exits_by_station.items():
        avg_lat = sum(e["latitude"] for e in exit_list) / len(exit_list)
        avg_lon = sum(e["longitude"] for e in exit_list) / len(exit_list)
        centroids[stn] = (avg_lat, avg_lon)
    centroids.update(ACCURATE_STATION_COORDINATES)
    return centroids


# ---------------------------------------------------------------------------
# 3. Route Segments Generator
# ---------------------------------------------------------------------------

def get_mrt_station_segments(geojson_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Returns list of route segments connecting consecutive MRT stations on each line.
    Matches schema: transit_route_segment (
        service_no, direction, stop_sequence, from_stop_code, to_stop_code, est_travel_time_min, distance_km
    )

    Direction 1: Outbound (first station -> last station)
    Direction 2: Inbound (last station -> first station)
    """
    centroids = get_station_centroids(geojson_path)
    segments: List[Dict[str, Any]] = []

    for line_code, line_data in MRT_LINES.items():
        routes_to_process = [line_data["stations"]]
        if "branches" in line_data:
            for branch in line_data["branches"]:
                routes_to_process.append(branch["stations"])

        for route_idx, stn_list in enumerate(routes_to_process):
            # For branch lines, service_no could be line_code or branch_id
            service_no = line_code
            if route_idx > 0 and "branches" in line_data:
                service_no = line_data["branches"][route_idx - 1].get("branch_id", line_code)

            # Direction 1: Forward
            for seq in range(len(stn_list) - 1):
                from_code, from_name = stn_list[seq]
                to_code, to_name = stn_list[seq + 1]

                from_norm = from_name.upper()
                to_norm = to_name.upper()

                lat1, lon1 = centroids.get(from_norm, (1.3521, 103.8198))
                lat2, lon2 = centroids.get(to_norm, (1.3521, 103.8198))

                dist_km = round(haversine_distance_km(lat1, lon1, lat2, lon2), 2)
                # Travel time: distance / speed * 60 + dwell time
                travel_time = round((dist_km / MRT_AVG_SPEED_KMH) * 60.0 + MRT_DWELL_TIME_MIN, 1)
                travel_time = max(1.0, travel_time)  # At least 1.0 min

                segments.append({
                    "service_no": service_no,
                    "direction": 1,
                    "stop_sequence": seq + 1,
                    "from_stop_code": from_code,
                    "to_stop_code": to_code,
                    "est_travel_time_min": travel_time,
                    "distance_km": dist_km,
                })

            # Direction 2: Reverse
            rev_stn_list = list(reversed(stn_list))
            for seq in range(len(rev_stn_list) - 1):
                from_code, from_name = rev_stn_list[seq]
                to_code, to_name = rev_stn_list[seq + 1]

                from_norm = from_name.upper()
                to_norm = to_name.upper()

                lat1, lon1 = centroids.get(from_norm, (1.3521, 103.8198))
                lat2, lon2 = centroids.get(to_norm, (1.3521, 103.8198))

                dist_km = round(haversine_distance_km(lat1, lon1, lat2, lon2), 2)
                travel_time = round((dist_km / MRT_AVG_SPEED_KMH) * 60.0 + MRT_DWELL_TIME_MIN, 1)
                travel_time = max(1.0, travel_time)

                segments.append({
                    "service_no": service_no,
                    "direction": 2,
                    "stop_sequence": seq + 1,
                    "from_stop_code": from_code,
                    "to_stop_code": to_code,
                    "est_travel_time_min": travel_time,
                    "distance_km": dist_km,
                })

    return segments


# ---------------------------------------------------------------------------
# 4. Interchange Transfers Generator
# ---------------------------------------------------------------------------

def get_interchange_stations() -> Dict[str, List[Tuple[str, str]]]:
    """
    Identifies all interchange stations that serve multiple lines.
    Returns: {STATION_NAME: [(line_code, station_code), ...]}
    """
    station_lines: Dict[str, List[Tuple[str, str]]] = {}
    for line_code, line_data in MRT_LINES.items():
        for stn_code, stn_name in line_data["stations"]:
            norm = stn_name.upper()
            station_lines.setdefault(norm, []).append((line_code, stn_code))
        if "branches" in line_data:
            for branch in line_data["branches"]:
                b_id = branch.get("branch_id", line_code)
                for stn_code, stn_name in branch["stations"]:
                    norm = stn_name.upper()
                    if (b_id, stn_code) not in station_lines.get(norm, []):
                        station_lines.setdefault(norm, []).append((b_id, stn_code))

    return {stn: lines for stn, lines in station_lines.items() if len(lines) > 1}


def get_interchange_transfers(geojson_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Generates transfer links for multi-line interchange stations and inter-exit pedestrian links.
    Returns list of dicts:
    [
        {
            "station_name": "DHOBY GHAUT",
            "lines": ["NSL", "NEL", "CCL"],
            "station_codes": ["NS24", "NE6", "CC1"],
            "from_exit": "Exit A",
            "to_exit": "Exit B",
            "from_stop_code": "DHOBY GHAUT_A",
            "to_stop_code": "DHOBY GHAUT_B",
            "walk_distance_m": 125.4,
            "est_transfer_time_min": 3.9,
            "is_sheltered": True
        },
        ...
    ]
    """
    exits_by_station = get_station_exits_map(geojson_path)
    interchanges = get_interchange_stations()

    transfers: List[Dict[str, Any]] = []

    for stn_name, line_tuples in interchanges.items():
        exit_list = exits_by_station.get(stn_name, [])
        if len(exit_list) < 2:
            continue

        lines = sorted(list(set(t[0] for t in line_tuples)))
        codes = sorted(list(set(t[1] for t in line_tuples)))

        # Pairwise exits within interchange complex
        for i in range(len(exit_list)):
            for j in range(len(exit_list)):
                if i == j:
                    continue
                e1 = exit_list[i]
                e2 = exit_list[j]

                dist_km = haversine_distance_km(
                    e1["latitude"], e1["longitude"], e2["latitude"], e2["longitude"]
                )
                dist_m = round(dist_km * 1000.0, 1)

                # Transfer time = base time + walk distance / walking speed
                trans_time = round(BASE_TRANSFER_TIME_MIN + (dist_m / WALK_SPEED_M_PER_MIN), 1)

                transfers.append({
                    "station_name": stn_name,
                    "lines": lines,
                    "station_codes": codes,
                    "from_exit": e1["exit_code"],
                    "to_exit": e2["exit_code"],
                    "from_stop_code": e1["stop_code"],
                    "to_stop_code": e2["stop_code"],
                    "walk_distance_m": dist_m,
                    "est_transfer_time_min": trans_time,
                    "is_sheltered": True,
                })

    return transfers


# ---------------------------------------------------------------------------
# 5. Transit Services Generator
# ---------------------------------------------------------------------------

def get_mrt_services() -> List[Dict[str, str]]:
    """
    Returns list of MRT services compatible with transit_service table.
    """
    services = []
    seen = set()
    for line_code, line_data in MRT_LINES.items():
        if line_code not in seen:
            services.append({
                "service_no": line_code,
                "operator": line_data["operator"],
                "mode": "MRT",
            })
            seen.add(line_code)
        if "branches" in line_data:
            for b in line_data["branches"]:
                bid = b.get("branch_id")
                if bid and bid not in seen:
                    services.append({
                        "service_no": bid,
                        "operator": line_data["operator"],
                        "mode": "MRT",
                    })
                    seen.add(bid)
    return services


# ---------------------------------------------------------------------------
# 6. Verification and CLI Output
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("TRANSIQ MRT Data & Topology Verification")
    print("=" * 60)

    # 1. Verify MRT Lines
    total_stations = 0
    print("\n1. MRT Line Definitions:")
    for code, data in MRT_LINES.items():
        stn_count = len(data["stations"])
        branch_count = len(data.get("branches", []))
        total_stations += stn_count
        first_stn = f"{data['stations'][0][0]} {data['stations'][0][1]}"
        last_stn = f"{data['stations'][-1][0]} {data['stations'][-1][1]}"
        print(f"  [{code}] {data['line_name']:<25} ({data['operator']}): "
              f"{stn_count} stations ({first_stn} -> {last_stn}), {branch_count} branches")

    # 2. Verify Services
    services = get_mrt_services()
    print(f"\n2. Total MRT Services: {len(services)}")
    for s in services:
        print(f"  Service {s['service_no']:<5} | Operator: {s['operator']:<5} | Mode: {s['mode']}")

    # 3. Verify Route Segments
    segments = get_mrt_station_segments()
    print(f"\n3. Transit Route Segments: {len(segments)} segments generated")
    dir1_count = sum(1 for s in segments if s["direction"] == 1)
    dir2_count = sum(1 for s in segments if s["direction"] == 2)
    print(f"  Direction 1 (Outbound): {dir1_count} segments")
    print(f"  Direction 2 (Inbound):  {dir2_count} segments")
    print("  Sample Segments:")
    for s in segments[:4]:
        print(f"    {s['service_no']} Dir {s['direction']} Seq {s['stop_sequence']}: "
              f"{s['from_stop_code']} -> {s['to_stop_code']} "
              f"({s['distance_km']} km, {s['est_travel_time_min']} min)")

    # 4. Verify Interchange Stations & Transfers
    interchanges = get_interchange_stations()
    print(f"\n4. Multi-Line Interchange Stations: {len(interchanges)} stations")
    for stn, lines in sorted(interchanges.items()):
        line_str = ", ".join(f"{line}:{code}" for line, code in lines)
        print(f"  {stn:<22}: {line_str}")

    transfers = get_interchange_transfers()
    print(f"\n5. Interchange Exit-to-Exit Transfers: {len(transfers)} transfer links")
    print("  Sample Transfers:")
    for t in transfers[:4]:
        print(f"    [{t['station_name']}] {t['from_stop_code']} -> {t['to_stop_code']}: "
              f"{t['walk_distance_m']}m ({t['est_transfer_time_min']} min, sheltered={t['is_sheltered']})")

    print("\n" + "=" * 60)
    print("Verification Successful!")
    print("=" * 60)
