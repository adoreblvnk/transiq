"""Router for transit route pathfinding and itinerary optimization."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from api.services.db import get_neo4j_session, get_pg_connection
from api.services.onemap import search_address

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CATALOG_FILE = ROOT_DIR / "data" / "verified_88_locations.json"
router = APIRouter(prefix="/api/routes", tags=["Routing"])


class RouteSearchRequest(BaseModel):
    origin_postal: str = Field(default="640183", description="Origin HDB 6-digit postal code")
    dest_postal: str = Field(default="648886", description="Destination commercial or HDB 6-digit postal code")
    mode: str = Field(default="FASTEST", description="Optimization mode: RAIN_SHIELD, COMFORT_SEATS, LEAST_TRANSFERS, FASTEST")
    strict_mode: bool = Field(default=False, description="Whether to reject non-compliant legs strictly")
    weight_unsheltered: Optional[float] = Field(default=None, description="Custom penalty per meter unsheltered")
    weight_crowd: Optional[float] = Field(default=None, description="Custom penalty per LSD crowded leg")
    weight_transfer: Optional[float] = Field(default=None, description="Custom penalty per vehicle transfer")


class ItineraryStep(BaseModel):
    step_type: str  # WALK, TRANSIT, TRANSFER
    transit_mode: Optional[str] = None  # BUS, MRT, WALK, TRANSFER
    from_name: str
    to_name: str
    service: Optional[str] = None
    distance_m: Optional[float] = None
    duration_min: float
    is_sheltered: bool = True
    live_load: Optional[str] = None
    coordinates: Optional[List[List[float]]] = None
    stop_count: Optional[int] = 1
class RouteOption(BaseModel):
    route_index: int
    score: float
    base_travel_time: float
    sheltered_m: float
    unsheltered_m: float
    transfer_count: int
    lsd_leg_count: int
    itinerary_nodes: List[str]
    steps: List[ItineraryStep]
    coordinates: List[List[float]]  # [[lat, lon], ...]


@router.get("/geocode")
def geocode_address(query: str = Query(..., min_length=2)):
    """Geocode address or postal code live using OneMap API."""
    return search_address(query)

def ensure_postal_in_graph(session, postal_code: str) -> bool:
    """Ensure a postal code exists as an indexed node in Neo4j connected to transit."""
    clean_p = postal_code.strip()
    exists = session.run("MATCH (n {postal_code: $p}) RETURN n.postal_code LIMIT 1", p=clean_p).single()
    if exists:
        return True

    name = f"Location {clean_p}"
    lat, lon = None, None

    # 1. Check PostgreSQL hdb_building
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT block_no, street_name, town, latitude, longitude FROM hdb_building WHERE postal_code = %s;",
                (clean_p,)
            )
            r = cur.fetchone()
            if r:
                name = f"Blk {r[0]} {r[1]} ({r[2]})"
                lat, lon = float(r[3]), float(r[4])

    # 2. Check live OneMap geocode if not in Postgres
    if lat is None or lon is None:
        om_results = search_address(clean_p)
        if om_results:
            first = om_results[0]
            name = first.get("building") or first.get("address") or f"Location {clean_p}"
            lat, lon = float(first["latitude"]), float(first["longitude"])

    if lat is None or lon is None:
        return False

    # Dynamically inject node and connect to transit within 500m
    session.run(
        """
        MERGE (n:HDBBlock {postal_code: $postal})
        SET n.name = $name, n.lat = $lat, n.lon = $lon,
            n.location = point({latitude: $lat, longitude: $lon})
        WITH n
        MATCH (s) WHERE (s:BusStop OR s:MRTExit) AND point.distance(n.location, s.location) <= 500
        MERGE (n)-[w1:SHELTERED_WALK]->(s)
        SET w1.distance_m = round(point.distance(n.location, s.location)), w1.is_covered = true
        MERGE (s)-[w2:SHELTERED_WALK]->(n)
        SET w2.distance_m = round(point.distance(n.location, s.location)), w2.is_covered = true
        """,
        postal=clean_p, name=name, lat=lat, lon=lon
    )
    return True

@router.get("/anchors")
def get_anchor_locations():
    """Retrieve 100% verified OneMap landmark catalog across all 22 Singapore regions."""
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE) as f:
            raw = json.load(f)
            clean_locs = [
                {
                    "postal_code": item["postal_code"],
                    "label": item["label"],
                    "latitude": item["latitude"],
                    "longitude": item["longitude"]
                }
                for item in raw
            ]
            return {"origins": clean_locs, "destinations": clean_locs}

    locations = [
        # 1. Sembawang
        {"postal_code": "757713", "label": "Sun Plaza Sembawang (757713)", "latitude": 1.4480, "longitude": 103.8195},
        {"postal_code": "759775", "label": "Sembawang MRT & Interchange (759775)", "latitude": 1.4491, "longitude": 103.8200},
        {"postal_code": "750133", "label": "Canberra Plaza (750133)", "latitude": 1.4431, "longitude": 103.8297},
        {"postal_code": "750501", "label": "Blk 501 Sembawang Way (750501)", "latitude": 1.4475, "longitude": 103.8180},
        # 2. Woodlands
        {"postal_code": "738099", "label": "Causeway Point Woodlands (738099)", "latitude": 1.4360, "longitude": 103.7865},
        {"postal_code": "737900", "label": "Woodlands North MRT (737900)", "latitude": 1.4485, "longitude": 103.7858},
        {"postal_code": "730101", "label": "Blk 101 Woodlands Ave 1 (730101)", "latitude": 1.4332, "longitude": 103.7845},
        # 3. Yishun
        {"postal_code": "769098", "label": "Northpoint City Yishun (769098)", "latitude": 1.4294, "longitude": 103.8360},
        {"postal_code": "768643", "label": "Yishun Bus Interchange (768643)", "latitude": 1.4290, "longitude": 103.8355},
        {"postal_code": "760846", "label": "Khatib Central Hub (760846)", "latitude": 1.4174, "longitude": 103.8329},
        {"postal_code": "760101", "label": "Blk 101 Yishun Ring Rd (760101)", "latitude": 1.4310, "longitude": 103.8320},
        # 4. Choa Chu Kang
        {"postal_code": "689812", "label": "Lot One Shoppers Mall (689812)", "latitude": 1.3854, "longitude": 103.7443},
        {"postal_code": "689810", "label": "Choa Chu Kang Bus Interchange (689810)", "latitude": 1.3850, "longitude": 103.7440},
        {"postal_code": "689578", "label": "Yew Tee Point (689578)", "latitude": 1.3973, "longitude": 103.7474},
        {"postal_code": "680101", "label": "Blk 101 Teck Whye Lane (680101)", "latitude": 1.3820, "longitude": 103.7530},
        # 5. Bukit Batok
        {"postal_code": "658713", "label": "West Mall Bukit Batok (658713)", "latitude": 1.3500, "longitude": 103.7496},
        {"postal_code": "650100", "label": "Bukit Batok Central Interchange (650100)", "latitude": 1.3495, "longitude": 103.7490},
        {"postal_code": "659083", "label": "Bukit Gombak MRT Plaza (659083)", "latitude": 1.3587, "longitude": 103.7519},
        {"postal_code": "650101", "label": "Blk 101 Bukit Batok West Ave 6 (650101)", "latitude": 1.3450, "longitude": 103.7460},
        # 6. Jurong East
        {"postal_code": "608532", "label": "Westgate & JEM Mall (608532)", "latitude": 1.3331, "longitude": 103.7423},
        {"postal_code": "609601", "label": "IMM Building Jurong East (609601)", "latitude": 1.3348, "longitude": 103.7468},
        {"postal_code": "609731", "label": "Jurong East Integrated Transport Hub (609731)", "latitude": 1.3335, "longitude": 103.7420},
        {"postal_code": "609894", "label": "Singapore Science Centre (609894)", "latitude": 1.3320, "longitude": 103.7360},
        # 7. Jurong West
        {"postal_code": "640183", "label": "Blk 183 Boon Lay Ave (640183)", "latitude": 1.3482, "longitude": 103.7081},
        {"postal_code": "640638", "label": "Pioneer Mall (640638)", "latitude": 1.3415, "longitude": 103.6975},
        {"postal_code": "648348", "label": "Gek Poh Shopping Centre (648348)", "latitude": 1.3489, "longitude": 103.6977},
        {"postal_code": "649040", "label": "Jurong West Sports Hub (649040)", "latitude": 1.3385, "longitude": 103.6945},
        # 8. Boon Lay
        {"postal_code": "648886", "label": "Jurong Point Mall (648886)", "latitude": 1.3397, "longitude": 103.7067},
        {"postal_code": "648340", "label": "Boon Lay Bus Interchange (648340)", "latitude": 1.3390, "longitude": 103.7060},
        {"postal_code": "640221", "label": "Boon Lay Shopping Centre (640221)", "latitude": 1.3465, "longitude": 103.7125},
        {"postal_code": "640207", "label": "Blk 207 Boon Lay Place (640207)", "latitude": 1.3490, "longitude": 103.7135},
        # 9. Clementi
        {"postal_code": "129588", "label": "The Clementi Mall (129588)", "latitude": 1.3151, "longitude": 103.7652},
        {"postal_code": "129901", "label": "321 Clementi (129901)", "latitude": 1.3140, "longitude": 103.7645},
        {"postal_code": "120101", "label": "Blk 101 Clementi West St 1 (120101)", "latitude": 1.3060, "longitude": 103.7680},
        # 10. Bukit Timah
        {"postal_code": "588177", "label": "Beauty World Centre (588177)", "latitude": 1.3413, "longitude": 103.7758},
        {"postal_code": "588996", "label": "Bukit Timah Plaza (588996)", "latitude": 1.3385, "longitude": 103.7770},
        {"postal_code": "599491", "label": "King Albert Park Mall (599491)", "latitude": 1.3358, "longitude": 103.7834},
        {"postal_code": "276403", "label": "Sixth Avenue MRT (276403)", "latitude": 1.3308, "longitude": 103.7969},
        # 11. Queenstown
        {"postal_code": "149053", "label": "Queensway Shopping Centre (149053)", "latitude": 1.2875, "longitude": 103.8035},
        {"postal_code": "159957", "label": "Anchorpoint Mall (159957)", "latitude": 1.2882, "longitude": 103.8048},
        {"postal_code": "149732", "label": "Queenstown Community Centre (149732)", "latitude": 1.2970, "longitude": 103.8020},
        {"postal_code": "140101", "label": "Blk 101 Commonwealth Crescent (140101)", "latitude": 1.3065, "longitude": 103.8000},
        # 12. Tanglin
        {"postal_code": "247933", "label": "Tanglin Mall (247933)", "latitude": 1.3045, "longitude": 103.8235},
        {"postal_code": "248649", "label": "Orchard Boulevard MRT (248649)", "latitude": 1.3025, "longitude": 103.8240},
        {"postal_code": "249676", "label": "Dempsey Hill Lifestyle Hub (249676)", "latitude": 1.3040, "longitude": 103.8115},
        {"postal_code": "258439", "label": "Napier MRT Station (258439)", "latitude": 1.3060, "longitude": 103.8185},
        # 13. Bukit Merah
        {"postal_code": "159471", "label": "Bukit Merah Central Hub (159471)", "latitude": 1.2825, "longitude": 103.8180},
        {"postal_code": "168732", "label": "Tiong Bahru Plaza (168732)", "latitude": 1.2861, "longitude": 103.8269},
        {"postal_code": "150101", "label": "Blk 101 Henderson Crescent (150101)", "latitude": 1.2910, "longitude": 103.8220},
        {"postal_code": "100001", "label": "Blk 1 Bukit Merah Central (100001)", "latitude": 1.2830, "longitude": 103.8175},
        # 14. Outram & Downtown
        {"postal_code": "048616", "label": "Raffles Place CBD Tower (048616)", "latitude": 1.2840, "longitude": 103.8515},
        {"postal_code": "059413", "label": "Chinatown Point (059413)", "latitude": 1.2846, "longitude": 103.8439},
        {"postal_code": "018956", "label": "Marina Bay Sands Hub (018956)", "latitude": 1.2834, "longitude": 103.8607},
        {"postal_code": "169078", "label": "Outram Park MRT Interchange (169078)", "latitude": 1.2803, "longitude": 103.8395},
        # 15. Hougang
        {"postal_code": "538766", "label": "Hougang Mall (538766)", "latitude": 1.3713, "longitude": 103.8924},
        {"postal_code": "538692", "label": "Kang Kar Mall Hougang (538692)", "latitude": 1.3725, "longitude": 103.8940},
        {"postal_code": "530101", "label": "Blk 101 Hougang Ave 1 (530101)", "latitude": 1.3550, "longitude": 103.8890},
        # 16. Sengkang
        {"postal_code": "545078", "label": "Compass One Sengkang (545078)", "latitude": 1.3917, "longitude": 103.8955},
        {"postal_code": "544834", "label": "Sengkang Grand Mall (544834)", "latitude": 1.3829, "longitude": 103.8931},
        {"postal_code": "545025", "label": "Rivervale Mall (545025)", "latitude": 1.3920, "longitude": 103.9045},
        {"postal_code": "540101", "label": "Blk 101 Rivervale Walk (540101)", "latitude": 1.3870, "longitude": 103.9020},
        # 17. Punggol
        {"postal_code": "828761", "label": "Waterway Point Punggol (828761)", "latitude": 1.4067, "longitude": 103.9022},
        {"postal_code": "828629", "label": "One Punggol Hub (828629)", "latitude": 1.4085, "longitude": 103.9030},
        {"postal_code": "828815", "label": "Oasis Terraces Punggol (828815)", "latitude": 1.4030, "longitude": 103.9130},
        {"postal_code": "828836", "label": "Northshore Plaza (828836)", "latitude": 1.4160, "longitude": 103.9075},
        # 18. Pasir Ris
        {"postal_code": "518457", "label": "White Sands Pasir Ris (518457)", "latitude": 1.3730, "longitude": 103.9493},
        {"postal_code": "519599", "label": "Downtown East Hub (519599)", "latitude": 1.3780, "longitude": 103.9550},
        {"postal_code": "510735", "label": "Pasir Ris West Plaza (510735)", "latitude": 1.3695, "longitude": 103.9380},
        {"postal_code": "510101", "label": "Blk 101 Pasir Ris St 12 (510101)", "latitude": 1.3680, "longitude": 103.9580},
        # 19. Tampines
        {"postal_code": "529536", "label": "Tampines 1 Shopping Mall (529536)", "latitude": 1.3542, "longitude": 103.9452},
        {"postal_code": "529510", "label": "Tampines Mall & Hub (529510)", "latitude": 1.3524, "longitude": 103.9447},
        {"postal_code": "529509", "label": "Century Square (529509)", "latitude": 1.3520, "longitude": 103.9435},
        {"postal_code": "520101", "label": "Blk 101 Tampines St 11 (520101)", "latitude": 1.3489, "longitude": 103.9482},
        # 20. Paya Lebar
        {"postal_code": "409057", "label": "Paya Lebar Quarter PLQ (409057)", "latitude": 1.3178, "longitude": 103.8924},
        {"postal_code": "409051", "label": "Paya Lebar Square (409051)", "latitude": 1.3185, "longitude": 103.8930},
        {"postal_code": "408600", "label": "SingPost Centre (408600)", "latitude": 1.3195, "longitude": 103.8945},
        {"postal_code": "402001", "label": "Geylang Serai Market (402001)", "latitude": 1.3168, "longitude": 103.8980},
        # 21. Bedok
        {"postal_code": "467360", "label": "Bedok Mall Interchange (467360)", "latitude": 1.3246, "longitude": 103.9298},
        {"postal_code": "469662", "label": "Heartbeat@Bedok Hub (469662)", "latitude": 1.3268, "longitude": 103.9315},
        {"postal_code": "460001", "label": "Blk 1 Bedok South Ave 1 (460001)", "latitude": 1.3210, "longitude": 103.9310},
        {"postal_code": "460101", "label": "Blk 101 Bedok North Ave 4 (460101)", "latitude": 1.3320, "longitude": 103.9360},
        # 22. Geylang
        {"postal_code": "409286", "label": "City Plaza Geylang (409286)", "latitude": 1.3150, "longitude": 103.8935},
        {"postal_code": "437157", "label": "Kinex Mall Geylang (437157)", "latitude": 1.3145, "longitude": 103.8960},
        {"postal_code": "389801", "label": "Aljunied MRT Station (389801)", "latitude": 1.3164, "longitude": 103.8829},
        {"postal_code": "380101", "label": "Blk 101 Aljunied Crescent (380101)", "latitude": 1.3200, "longitude": 103.8830},
    ]
    return {"origins": locations, "destinations": locations}

def collapse_consecutive_transit_steps(raw_steps: List[ItineraryStep]) -> List[ItineraryStep]:
    """
    Collapses consecutive transit steps on the same line/service into a single step
    (e.g., Boon Lay -> Tampines on MRT EWL instead of 24 separate station steps).
    Breaks and separates steps whenever switching lines, modes, or transfer walks occur.
    """
    if not raw_steps:
        return []

    collapsed = []
    current: Optional[ItineraryStep] = None

    for s in raw_steps:
        if current is None:
            current = s.model_copy()
            continue

        can_merge_transit = (
            current.step_type == "TRANSIT" and
            s.step_type == "TRANSIT" and
            current.transit_mode == s.transit_mode and
            current.service == s.service and
            current.service is not None and
            current.service != ""
        )

        can_merge_walk = (
            current.step_type == "WALK" and
            s.step_type == "WALK" and
            current.is_sheltered == s.is_sheltered
        )

        can_merge_transfer = (
            current.step_type == "TRANSFER" and
            s.step_type == "TRANSFER"
        )

        if can_merge_transit or can_merge_walk or can_merge_transfer:
            current.to_name = s.to_name
            current.duration_min = round(current.duration_min + s.duration_min, 1)
            if current.distance_m is not None and s.distance_m is not None:
                current.distance_m = round(current.distance_m + s.distance_m, 1)
            elif s.distance_m is not None:
                current.distance_m = s.distance_m

            if can_merge_transit:
                current.stop_count = (current.stop_count or 1) + (s.stop_count or 1)
                crowd_priority = {"LSD": 3, "SDA": 2, "SEA": 1}
                cur_p = crowd_priority.get(current.live_load or "", 1)
                s_p = crowd_priority.get(s.live_load or "", 1)
                if s_p > cur_p:
                    current.live_load = s.live_load

            if s.coordinates:
                if not current.coordinates:
                    current.coordinates = list(s.coordinates)
                else:
                    current.coordinates.extend(s.coordinates[1:] if len(s.coordinates) > 1 else s.coordinates)
        else:
            collapsed.append(current)
            current = s.model_copy()

    if current is not None:
        collapsed.append(current)

    return collapsed


@router.post("/search", response_model=List[RouteOption])
def search_transit_routes(req: RouteSearchRequest):
    """Find multi-modal transit routes matching commuter mode preferences."""
    # Guard: Origin and Destination are identical
    if req.origin_postal.strip() == req.dest_postal.strip():
        postal = req.origin_postal.strip()
        with get_neo4j_session() as session:
            ensure_postal_in_graph(session, postal)
            n_res = session.run("MATCH (n {postal_code: $p}) RETURN coalesce(n.name, n.postal_code) AS name, n.lat AS lat, n.lon AS lon LIMIT 1", p=postal).single()
            loc_name = n_res["name"] if n_res and n_res["name"] else f"Location {postal}"
            coords = [[float(n_res["lat"]), float(n_res["lon"])]] if n_res and n_res["lat"] is not None else []

        return [RouteOption(
            route_index=1,
            score=0.0,
            base_travel_time=0.0,
            sheltered_m=0.0,
            unsheltered_m=0.0,
            transfer_count=0,
            lsd_leg_count=0,
            itinerary_nodes=[loc_name],
            steps=[ItineraryStep(
                step_type="WALK",
                from_name=loc_name,
                to_name=f"{loc_name} (Same Location)",
                duration_min=0.0,
                distance_m=0.0,
                is_sheltered=True
            )],
            coordinates=coords
        )]

    # Penalty weights based on commuter mode
    w_unsh = req.weight_unsheltered
    w_crowd = req.weight_crowd
    w_trans = req.weight_transfer

    if req.mode == "RAIN_SHIELD":
        if w_unsh is None: w_unsh = 0.08
        if w_crowd is None: w_crowd = 2.0
        if w_trans is None: w_trans = 5.0
    elif req.mode == "COMFORT_SEATS":
        if w_unsh is None: w_unsh = 0.02
        if w_crowd is None: w_crowd = 20.0
        if w_trans is None: w_trans = 5.0
    elif req.mode == "LEAST_TRANSFERS":
        if w_unsh is None: w_unsh = 0.02
        if w_crowd is None: w_crowd = 5.0
        if w_trans is None: w_trans = 25.0
    else:  # FASTEST
        if w_unsh is None: w_unsh = 0.005
        if w_crowd is None: w_crowd = 0.5
        if w_trans is None: w_trans = 1.0

    params = {
        "origin_postal": req.origin_postal,
        "dest_postal": req.dest_postal,
        "strict_mode": req.strict_mode,
        "weight_unsheltered": float(w_unsh),
        "weight_crowd": float(w_crowd),
        "weight_transfer": float(w_trans),
    }

    # Query 1: Local Multi-Modal Transit (up to 4 hops)
    cypher_local = """
    MATCH (start {postal_code: $origin_postal})
    MATCH (dest {postal_code: $dest_postal})

    MATCH (start)-[w1:SHELTERED_WALK|UNSHELTERED_WALK]->(s1)
    WHERE s1:BusStop OR s1:MRTExit
    MATCH tp = (s1)-[:TRANSIT_RIDE|STATION_TRANSFER*1..4]->(s2)
    WHERE (s2:BusStop OR s2:MRTExit) AND (
        $strict_mode = false OR (
            ALL(r IN relationships(tp) WHERE type(r) <> 'TRANSIT_RIDE' OR r.live_load <> 'LSD') AND
            type(w1) = 'SHELTERED_WALK'
        )
    )
    MATCH (s2)-[w2:SHELTERED_WALK|UNSHELTERED_WALK]->(dest)
    WHERE $strict_mode = false OR type(w2) = 'SHELTERED_WALK'

    WITH start, dest, w1, tp, w2,
         [r IN relationships(tp) WHERE type(r) = 'TRANSIT_RIDE'] AS transit_legs
    WITH start, dest, w1, tp, w2, transit_legs,
         reduce(t = 0.0, r IN transit_legs | t + r.avg_duration_min) AS base_travel_time,
         (CASE WHEN type(w1) = 'UNSHELTERED_WALK' THEN w1.distance_m ELSE 0.0 END +
          CASE WHEN type(w2) = 'UNSHELTERED_WALK' THEN w2.distance_m ELSE 0.0 END) AS unsheltered_m,
         (CASE WHEN type(w1) = 'SHELTERED_WALK' THEN w1.distance_m ELSE 0.0 END +
          CASE WHEN type(w2) = 'SHELTERED_WALK' THEN w2.distance_m ELSE 0.0 END) AS sheltered_m,
         CASE WHEN size(transit_legs) > 0 THEN size(transit_legs) - 1 ELSE 0 END AS transfer_count,
         size([r IN transit_legs WHERE r.live_load = 'LSD']) AS lsd_leg_count,
         nodes(tp) AS tp_nodes,
         relationships(tp) AS tp_rels

    RETURN
        [start] + tp_nodes + [dest] AS node_objs,
        [w1] + tp_rels + [w2] AS rel_objs,
        [n IN ([start] + tp_nodes + [dest]) | coalesce(n.name, n.postal_code, n.code)] AS itinerary,
        transfer_count,
        base_travel_time,
        sheltered_m,
        unsheltered_m,
        lsd_leg_count,
        (base_travel_time
          + (unsheltered_m * $weight_unsheltered)
          + (lsd_leg_count * $weight_crowd)
          + (transfer_count * $weight_transfer)) AS score
    ORDER BY score ASC
    LIMIT 3;
    """

    # Query 2: Long-distance Transit via ShortestPath on Transit Graph
    # Query 2: Multi-Modal Transit ShortestPath Traversal (up to 45 hops)
    cypher_long = """
    MATCH (start {postal_code: $origin_postal})
    MATCH (dest {postal_code: $dest_postal})

    MATCH p = shortestPath((start)-[:SHELTERED_WALK|UNSHELTERED_WALK|TRANSIT_RIDE|STATION_TRANSFER*..45]->(dest))
    WHERE ($strict_mode = false OR (
        ALL(r IN relationships(p) WHERE type(r) <> 'TRANSIT_RIDE' OR r.live_load <> 'LSD') AND
        ALL(r IN relationships(p) WHERE type(r) <> 'UNSHELTERED_WALK')
    ))

    WITH p,
         [r IN relationships(p) WHERE type(r) = 'TRANSIT_RIDE'] AS transit_legs,
         [r IN relationships(p) WHERE type(r) = 'UNSHELTERED_WALK'] AS unsheltered_walks,
         [r IN relationships(p) WHERE type(r) = 'SHELTERED_WALK'] AS sheltered_walks
    WITH p, transit_legs, unsheltered_walks, sheltered_walks,
         reduce(t = 0.0, r IN transit_legs | t + coalesce(r.avg_duration_min, 3.0)) +
         ((reduce(u = 0.0, r IN unsheltered_walks | u + coalesce(r.distance_m, 50.0)) +
           reduce(s = 0.0, r IN sheltered_walks | s + coalesce(r.distance_m, 50.0))) / 75.0) AS base_travel_time,
         reduce(u = 0.0, r IN unsheltered_walks | u + coalesce(r.distance_m, 50.0)) AS unsheltered_m,
         reduce(s = 0.0, r IN sheltered_walks | s + coalesce(r.distance_m, 50.0)) AS sheltered_m,
         CASE WHEN size(transit_legs) > 0 THEN size(transit_legs) - 1 ELSE 0 END AS transfer_count,
         size([r IN transit_legs WHERE r.live_load = 'LSD']) AS lsd_leg_count

    RETURN
        nodes(p) AS node_objs,
        relationships(p) AS rel_objs,
        [n IN nodes(p) | coalesce(n.name, n.postal_code, n.code)] AS itinerary,
        transfer_count,
        base_travel_time,
        sheltered_m,
        unsheltered_m,
        lsd_leg_count,
        (base_travel_time
          + (unsheltered_m * $weight_unsheltered)
          + (lsd_leg_count * $weight_crowd)
          + (transfer_count * $weight_transfer)) AS score
    ORDER BY score ASC
    LIMIT 3;
    """

    # Query 3: High-Speed Rail Trunk with First/Last Mile Feeder Integration
    cypher_rail = """
    MATCH (start {postal_code: $origin_postal})
    MATCH (dest {postal_code: $dest_postal})

    MATCH (m1:MRTExit)
    WITH start, dest, m1 ORDER BY point.distance(start.location, m1.location) ASC LIMIT 1

    MATCH (m2:MRTExit)
    WITH start, dest, m1, m2 ORDER BY point.distance(dest.location, m2.location) ASC LIMIT 1

    MATCH p_first = shortestPath((start)-[:SHELTERED_WALK|UNSHELTERED_WALK|TRANSIT_RIDE*..6]->(m1))
    MATCH p_mrt = shortestPath((m1)-[:TRANSIT_RIDE|STATION_TRANSFER*..45]->(m2))
    MATCH p_last = shortestPath((m2)-[:SHELTERED_WALK|UNSHELTERED_WALK|TRANSIT_RIDE*..6]->(dest))
    WHERE ($strict_mode = false OR (
        ALL(r IN relationships(p_first) WHERE type(r) <> 'UNSHELTERED_WALK') AND
        ALL(r IN relationships(p_mrt) WHERE type(r) <> 'TRANSIT_RIDE' OR r.live_load <> 'LSD') AND
        ALL(r IN relationships(p_last) WHERE type(r) <> 'UNSHELTERED_WALK')
    ))

    WITH start, dest, p_first, p_mrt, p_last,
         relationships(p_first) + relationships(p_mrt) + relationships(p_last) AS all_rels,
         nodes(p_first) + nodes(p_mrt)[1..] + nodes(p_last)[1..] AS all_nodes
    WITH all_rels, all_nodes,
         [r IN all_rels WHERE type(r) = 'TRANSIT_RIDE'] AS transit_legs,
         [r IN all_rels WHERE type(r) = 'STATION_TRANSFER'] AS transfer_legs,
         [r IN all_rels WHERE type(r) = 'UNSHELTERED_WALK'] AS unsheltered_walks,
         [r IN all_rels WHERE type(r) = 'SHELTERED_WALK'] AS sheltered_walks
    WITH all_rels, all_nodes, transit_legs,
         reduce(t = 0.0, r IN transit_legs | t + coalesce(r.avg_duration_min, 2.5)) +
         reduce(tr = 0.0, r IN transfer_legs | tr + coalesce(r.walking_time_min, 2.0)) +
         ((reduce(u = 0.0, r IN unsheltered_walks | u + coalesce(r.distance_m, 50.0)) +
           reduce(s = 0.0, r IN sheltered_walks | s + coalesce(r.distance_m, 50.0))) / 75.0) AS base_travel_time,
         reduce(u = 0.0, r IN unsheltered_walks | u + coalesce(r.distance_m, 50.0)) AS unsheltered_m,
         reduce(s = 0.0, r IN sheltered_walks | s + coalesce(r.distance_m, 50.0)) AS sheltered_m,
         size([r IN all_rels WHERE type(r) = 'STATION_TRANSFER']) + (CASE WHEN size(transit_legs) > 0 THEN size(transit_legs) - 1 ELSE 0 END) AS transfer_count,
         size([r IN transit_legs WHERE r.live_load = 'LSD']) AS lsd_leg_count

    RETURN
        all_nodes AS node_objs,
        all_rels AS rel_objs,
        [n IN all_nodes | coalesce(n.name, n.postal_code, n.code)] AS itinerary,
        transfer_count,
        base_travel_time,
        sheltered_m,
        unsheltered_m,
        lsd_leg_count,
        (base_travel_time
          + (unsheltered_m * $weight_unsheltered)
          + (lsd_leg_count * $weight_crowd)
          + (transfer_count * $weight_transfer)) AS score
    ORDER BY score ASC
    LIMIT 1;
    """

    records = []
    with get_neo4j_session() as session:
        ensure_postal_in_graph(session, req.origin_postal)
        ensure_postal_in_graph(session, req.dest_postal)

        # Spatial gate: check direct distance between origin and destination
        dist_res = session.run(
            """
            MATCH (start {postal_code: $origin_postal})
            MATCH (dest {postal_code: $dest_postal})
            RETURN point.distance(start.location, dest.location) AS dist_m
            LIMIT 1
            """,
            params
        ).single()
        dist_m = float(dist_res["dist_m"]) if dist_res and dist_res["dist_m"] is not None else 10000.0

        candidates = []
        if dist_m <= 3500.0:
            try:
                local_res = list(session.run(cypher_local, params))
                candidates.extend(local_res)
            except Exception:
                pass

        # 1. Multi-modal surface/bus corridor
        try:
            long_res = list(session.run(cypher_long, params))
            candidates.extend(long_res)
        except Exception:
            pass

        # 2. High-speed rail corridor (MRT lines with interchange transfers)
        try:
            rail_res = list(session.run(cypher_rail, params))
            candidates.extend(rail_res)
        except Exception:
            pass

        # Sort candidates strictly by TRANSIQ score ascending (Fastest/best score wins!)
        seen_itineraries = set()
        for c in sorted(candidates, key=lambda x: float(x.get("score", 9999.0))):
            itin_key = tuple(c.get("itinerary", []))
            if itin_key not in seen_itineraries:
                seen_itineraries.add(itin_key)
                records.append(c)
            if len(records) >= 3:
                break
    results = []
    for idx, rec in enumerate(records, 1):
        node_objs = rec["node_objs"]
        rel_objs = rec["rel_objs"]

        coords = []
        for n in node_objs:
            lat = n.get("lat") or n.get("latitude")
            lon = n.get("lon") or n.get("longitude")
            if lat is not None and lon is not None:
                coords.append([float(lat), float(lon)])

        steps = []
        for i, rel in enumerate(rel_objs):
            from_n = node_objs[i]
            to_n = node_objs[i + 1]
            rtype = rel.type
            from_name = from_n.get("name") or from_n.get("postal_code") or from_n.get("code") or "Origin"
            to_name = to_n.get("name") or to_n.get("postal_code") or to_n.get("code") or "Destination"

            from_c = [float(from_n["lat"]), float(from_n["lon"])] if from_n.get("lat") and from_n.get("lon") else None
            to_c = [float(to_n["lat"]), float(to_n["lon"])] if to_n.get("lat") and to_n.get("lon") else None
            step_coords = [from_c, to_c] if from_c and to_c else []

            if rtype == "SHELTERED_WALK":
                dist = float(rel.get("distance_m", 50.0))
                steps.append(ItineraryStep(
                    step_type="WALK",
                    transit_mode="WALK",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=dist,
                    duration_min=round(dist / 75.0, 1),
                    is_sheltered=True,
                    coordinates=step_coords
                ))
            elif rtype == "UNSHELTERED_WALK":
                dist = float(rel.get("distance_m", 50.0))
                steps.append(ItineraryStep(
                    step_type="WALK",
                    transit_mode="WALK",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=dist,
                    duration_min=round(dist / 75.0, 1),
                    is_sheltered=False,
                    coordinates=step_coords
                ))
            elif rtype == "TRANSIT_RIDE":
                svc = str(rel.get("service", "Transit")).strip()
                mrt_lines = {"EWL", "NSL", "NEL", "CCL", "DTL", "TEL"}
                is_mrt = svc.upper() in mrt_lines or "MRT" in str(from_name).upper() or "MRT" in str(to_name).upper()
                t_mode = "MRT" if is_mrt else "BUS"
                dist = round(float(rel.get("distance_km", 1.0)) * 1000.0, 0)
                steps.append(ItineraryStep(
                    step_type="TRANSIT",
                    transit_mode=t_mode,
                    from_name=str(from_name),
                    to_name=str(to_name),
                    service=svc,
                    distance_m=dist,
                    duration_min=float(rel.get("avg_duration_min", 3.0)),
                    is_sheltered=True,
                    live_load=str(rel.get("live_load", "SEA")),
                    coordinates=step_coords
                ))
            elif rtype == "STATION_TRANSFER":
                dist = float(rel.get("distance_m", 80.0))
                steps.append(ItineraryStep(
                    step_type="TRANSFER",
                    transit_mode="TRANSFER",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=dist,
                    duration_min=float(rel.get("walking_time_min", 2.0)),
                    is_sheltered=True,
                    coordinates=step_coords
                ))

        results.append(RouteOption(
            route_index=idx,
            score=round(float(rec["score"]), 2),
            base_travel_time=round(float(rec["base_travel_time"]), 1),
            sheltered_m=round(float(rec["sheltered_m"]), 1),
            unsheltered_m=round(float(rec["unsheltered_m"]), 1),
            transfer_count=max(0, int(rec["transfer_count"])),
            lsd_leg_count=int(rec["lsd_leg_count"]),
            itinerary_nodes=[str(x) for x in rec["itinerary"]],
            steps=collapse_consecutive_transit_steps(steps),
            coordinates=coords
        ))

    return results
