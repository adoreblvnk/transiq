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
                WHERE postal_code IN ('640183', '560101', '520101', '730101', '100001', '310001', '010001')
                   OR town IN ('Jurong West', 'Tampines', 'Woodlands', 'Ang Mo Kio', 'Bedok', 'Toa Payoh')
                ORDER BY town, block_no
                LIMIT 15;
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
        {"postal_code": "579837", "label": "Junction 8 Bishan (579837)", "latitude": 1.3506, "longitude": 103.8488, "type": "DESTINATION"},
        {"postal_code": "138683", "label": "Fusionopolis One-North (138683)", "latitude": 1.2989, "longitude": 103.7876, "type": "DESTINATION"},
    ]

    return {"origins": hdbs, "destinations": commercial_destinations + hdbs}


@router.post("/search", response_model=List[RouteOption])
def search_transit_routes(req: RouteSearchRequest):
    """Find multi-modal transit routes matching commuter mode preferences."""
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
         size(transit_legs) - 1 AS transfer_count,
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
    cypher_long = """
    MATCH (start {postal_code: $origin_postal})
    MATCH (dest {postal_code: $dest_postal})

    MATCH (start)-[w1:SHELTERED_WALK|UNSHELTERED_WALK]->(s1)
    WHERE (s1:BusStop OR s1:MRTExit) AND ($strict_mode = false OR type(w1) = 'SHELTERED_WALK')
    WITH start, dest, s1, w1 ORDER BY w1.distance_m ASC LIMIT 2

    MATCH (s2)-[w2:SHELTERED_WALK|UNSHELTERED_WALK]->(dest)
    WHERE (s2:BusStop OR s2:MRTExit) AND ($strict_mode = false OR type(w2) = 'SHELTERED_WALK')
    WITH start, dest, s1, w1, s2, w2 ORDER BY w2.distance_m ASC LIMIT 4

    MATCH p = shortestPath((s1)-[:TRANSIT_RIDE|STATION_TRANSFER*..20]->(s2))

    WITH start, dest, w1, p, w2,
         [r IN relationships(p) WHERE type(r) = 'TRANSIT_RIDE'] AS transit_legs
    WHERE ($strict_mode = false OR ALL(r IN transit_legs WHERE r.live_load <> 'LSD'))
    WITH start, dest, w1, p, w2, transit_legs,
         reduce(t = 0.0, r IN transit_legs | t + r.avg_duration_min) AS base_travel_time,
         (CASE WHEN type(w1) = 'UNSHELTERED_WALK' THEN w1.distance_m ELSE 0.0 END +
          CASE WHEN type(w2) = 'UNSHELTERED_WALK' THEN w2.distance_m ELSE 0.0 END) AS unsheltered_m,
         (CASE WHEN type(w1) = 'SHELTERED_WALK' THEN w1.distance_m ELSE 0.0 END +
          CASE WHEN type(w2) = 'SHELTERED_WALK' THEN w2.distance_m ELSE 0.0 END) AS sheltered_m,
         size(transit_legs) - 1 AS transfer_count,
         size([r IN transit_legs WHERE r.live_load = 'LSD']) AS lsd_leg_count

    RETURN
        [start] + nodes(p) + [dest] AS node_objs,
        [w1] + relationships(p) + [w2] AS rel_objs,
        [n IN ([start] + nodes(p) + [dest]) | coalesce(n.name, n.postal_code, n.code)] AS itinerary,
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

    records = []
    with get_neo4j_session() as session:
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

        # For short journeys (<= 3.5km), try local transit hops first
        if dist_m <= 3500.0:
            local_res = list(session.run(cypher_local, params))
            if local_res:
                records.extend(local_res)

        # For cross-town journeys or if no local hops found, use long-distance shortestPath
        if not records:
            long_res = list(session.run(cypher_long, params))
            records.extend(long_res)
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

            if rtype == "SHELTERED_WALK":
                dist = float(rel.get("distance_m", 50.0))
                steps.append(ItineraryStep(
                    step_type="WALK",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=dist,
                    duration_min=round(dist / 75.0, 1),
                    is_sheltered=True
                ))
            elif rtype == "UNSHELTERED_WALK":
                dist = float(rel.get("distance_m", 50.0))
                steps.append(ItineraryStep(
                    step_type="WALK",
                    from_name=str(from_name),
                    to_name=str(to_name),
                    distance_m=dist,
                    duration_min=round(dist / 75.0, 1),
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
            transfer_count=max(0, int(rec["transfer_count"])),
            lsd_leg_count=int(rec["lsd_leg_count"]),
            itinerary_nodes=[str(x) for x in rec["itinerary"]],
            steps=steps,
            coordinates=coords
        ))

    return results
