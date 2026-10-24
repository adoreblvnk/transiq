"""Router for transit route pathfinding and itinerary optimization."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from api.services.db import get_neo4j_session, get_pg_connection

router = APIRouter(prefix="/api/routes", tags=["Routing"])


class RouteSearchRequest(BaseModel):
    origin_postal: str = Field(default="640183", description="Origin HDB 6-digit postal code")
    dest_postal: str = Field(default="648886", description="Destination commercial or HDB 6-digit postal code")
    mode: str = Field(default="RAIN_SHIELD", description="Optimization mode: RAIN_SHIELD, COMFORT_SEATS, LEAST_TRANSFERS, FASTEST")
    strict_mode: bool = Field(default=False, description="Whether to reject non-compliant legs strictly")
    weight_unsheltered: Optional[float] = Field(default=None, description="Custom penalty per meter unsheltered")
    weight_crowd: Optional[float] = Field(default=None, description="Custom penalty per LSD crowded leg")
    weight_transfer: Optional[float] = Field(default=None, description="Custom penalty per vehicle transfer")


class ItineraryStep(BaseModel):
    step_type: str  # WALK, TRANSIT, TRANSFER
    from_name: str
    to_name: str
    service: Optional[str] = None
    distance_m: Optional[float] = None
    duration_min: float
    is_sheltered: bool = True
    live_load: Optional[str] = None


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


@router.get("/anchors")
def get_anchor_locations():
    """Retrieve sample origins (HDBs) and destinations (Hubs/HDBs) for the UI."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT postal_code, block_no, street_name, town, latitude, longitude
                FROM hdb_building
                WHERE postal_code IN ('640183', '010001', '100001', '520101', '560101', '730101')
                ORDER BY town;
                """
            )
            hdbs = [
                {
                    "postal_code": r[0],
                    "label": f"Blk {r[1]} {r[2]} ({r[3]}) - {r[0]}",
                    "latitude": float(r[4]),
                    "longitude": float(r[5]),
                    "type": "HDB"
                }
                for r in cur.fetchall()
            ]

    commercial_destinations = [
        {"postal_code": "648886", "label": "Jurong Point Mall (648886)", "latitude": 1.3397, "longitude": 103.7067, "type": "DESTINATION"},
        {"postal_code": "048616", "label": "Raffles Place CBD Tower (048616)", "latitude": 1.2840, "longitude": 103.8515, "type": "DESTINATION"},
        {"postal_code": "238839", "label": "Orchard Central Hub (238839)", "latitude": 1.3008, "longitude": 103.8398, "type": "DESTINATION"},
        {"postal_code": "529536", "label": "Tampines 1 Shopping Mall (529536)", "latitude": 1.3542, "longitude": 103.9452, "type": "DESTINATION"},
        {"postal_code": "738099", "label": "Woodlands Civic Centre (738099)", "latitude": 1.4360, "longitude": 103.7865, "type": "DESTINATION"},
    ]

    return {"origins": hdbs, "destinations": commercial_destinations + hdbs}


@router.post("/search", response_model=List[RouteOption])
def search_transit_routes(req: RouteSearchRequest):
    """Find multi-modal transit routes matching commuter mode preferences."""
    # Weights default by mode
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
        if w_unsh is None: w_unsh = 0.0
        if w_crowd is None: w_crowd = 0.0
        if w_trans is None: w_trans = 0.0

    cypher_query = """
    MATCH p = (start:HDBBlock {postal_code: $origin_postal})
              -[:SHELTERED_WALK|UNSHELTERED_WALK|TRANSIT_RIDE|STATION_TRANSFER*1..7]->
              (dest {postal_code: $dest_postal})
    WHERE ($strict_mode = false OR (
        ALL(r IN relationships(p) WHERE type(r) <> 'TRANSIT_RIDE' OR r.live_load <> 'LSD') AND
        ALL(r IN relationships(p) WHERE type(r) <> 'UNSHELTERED_WALK')
    ))
    WITH p,
         [r IN relationships(p) WHERE type(r) = 'TRANSIT_RIDE']     AS transit_legs,
         [r IN relationships(p) WHERE type(r) = 'UNSHELTERED_WALK']  AS unsheltered_walks,
         [r IN relationships(p) WHERE type(r) = 'SHELTERED_WALK']    AS sheltered_walks
    WITH p, transit_legs, unsheltered_walks, sheltered_walks,
         reduce(t = 0.0, r IN transit_legs | t + r.avg_duration_min) AS base_travel_time,
         reduce(u = 0.0, r IN unsheltered_walks | u + r.distance_m)   AS unsheltered_m,
         reduce(s = 0.0, r IN sheltered_walks | s + r.distance_m)     AS sheltered_m,
         size(transit_legs) - 1                                       AS transfer_count,
         size([r IN transit_legs WHERE r.live_load = 'LSD'])          AS lsd_leg_count
    RETURN
        [n IN nodes(p) | coalesce(n.name, n.postal_code, n.code)] AS itinerary,
        nodes(p) AS node_objs,
        relationships(p) AS rel_objs,
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

    params = {
        "origin_postal": req.origin_postal,
        "dest_postal": req.dest_postal,
        "strict_mode": req.strict_mode,
        "weight_unsheltered": float(w_unsh),
        "weight_crowd": float(w_crowd),
        "weight_transfer": float(w_trans)
    }

    results = []
    with get_neo4j_session() as session:
        records = list(session.run(cypher_query, params))

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

            if rtype == "SHELTERED_WALK":
                steps.append(ItineraryStep(
                    step_type="WALK",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=float(rel.get("distance_m", 50.0)),
                    duration_min=round(float(rel.get("distance_m", 50.0)) / 75.0, 1),
                    is_sheltered=True
                ))
            elif rtype == "UNSHELTERED_WALK":
                steps.append(ItineraryStep(
                    step_type="WALK",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=float(rel.get("distance_m", 50.0)),
                    duration_min=round(float(rel.get("distance_m", 50.0)) / 75.0, 1),
                    is_sheltered=False
                ))
            elif rtype == "TRANSIT_RIDE":
                steps.append(ItineraryStep(
                    step_type="TRANSIT",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    service=str(rel.get("service", "Transit")),
                    distance_m=round(float(rel.get("distance_km", 1.0)) * 1000.0, 0),
                    duration_min=float(rel.get("avg_duration_min", 3.0)),
                    is_sheltered=True,
                    live_load=str(rel.get("live_load", "SEA"))
                ))
            elif rtype == "STATION_TRANSFER":
                steps.append(ItineraryStep(
                    step_type="TRANSFER",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    duration_min=float(rel.get("walking_time_min", 2.0)),
                    is_sheltered=True
                ))

        results.append(RouteOption(
            route_index=idx,
            score=round(float(rec["score"]), 2),
            base_travel_time=round(float(rec["base_travel_time"]), 1),
            sheltered_m=round(float(rec["sheltered_m"]), 1),
            unsheltered_m=round(float(rec["unsheltered_m"]), 1),
            transfer_count=int(rec["transfer_count"]),
            lsd_leg_count=int(rec["lsd_leg_count"]),
            itinerary_nodes=[str(x) for x in rec["itinerary"]],
            steps=steps,
            coordinates=coords
        ))

    return results
