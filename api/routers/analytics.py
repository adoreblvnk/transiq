"""Router for analytical views and crowd density telemetry."""

from typing import Optional
from fastapi import APIRouter, Query
from api.services.db import get_pg_connection

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Views"])


@router.get("/sheltered_access")
def get_sheltered_access(postal_code: str = "640183"):
    """Query View 1: v_sheltered_access."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT postal_code, block_no, town, linkway_id, is_barrier_free, roof_condition, walk_distance_m, is_sheltered
                FROM v_sheltered_access
                WHERE postal_code = %s
                LIMIT 10;
                """,
                (postal_code,)
            )
            rows = cur.fetchall()
            return [
                {
                    "postal_code": r[0],
                    "block_no": r[1],
                    "town": r[2],
                    "linkway_id": r[3],
                    "is_barrier_free": r[4],
                    "roof_condition": r[5],
                    "walk_distance_m": float(r[6]),
                    "is_sheltered": r[7]
                }
                for r in rows
            ]

@router.post("/refresh_materialized_views")
def refresh_materialized_views():
    """Trigger CONCURRENT refresh of mv_sheltered_access."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT refresh_sheltered_access();")
            conn.commit()
    return {"status": "success", "refreshed": "mv_sheltered_access"}


@router.get("/peak_congestion")
def get_peak_congestion(
    limit: int = 15,
    search: Optional[str] = None,
    mode: Optional[str] = None
):
    """Query View 2: v_peak_congestion with window functions and parameterized station search."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            if search and search.strip():
                clean_search = f"%{search.strip()}%"
                mode_clause = ""
                if mode and mode.upper() in ("MRT", "BUS"):
                    mode_clause = "AND ts.stop_type IN ('MRT_STATION', 'MRT_EXIT')" if mode.upper() == "MRT" else "AND ts.stop_type = 'BUS_STOP'"

                query = f"""
                    SELECT 
                        vpc.stop_code, ts.stop_name, ts.stop_type,
                        MAX(vpc.hour_of_day) AS hour_of_day,
                        MAX(vpc.commuter_volume) AS commuter_volume,
                        MAX(vpc.crowd_index) AS crowd_index,
                        ROUND(AVG(vpc.rolling_3hr_avg)::numeric, 1) AS rolling_3hr_avg,
                        MIN(vpc.congestion_rank) AS congestion_rank
                    FROM v_peak_congestion vpc
                    JOIN transit_stop ts ON vpc.stop_code = ts.stop_code
                    WHERE (ts.stop_name ILIKE %s OR ts.stop_code ILIKE %s) {mode_clause}
                    GROUP BY vpc.stop_code, ts.stop_name, ts.stop_type
                    ORDER BY MIN(vpc.congestion_rank) ASC, MAX(vpc.commuter_volume) DESC
                    LIMIT %s;
                """
                cur.execute(query, (clean_search, clean_search, limit))
            else:
                mode_clause = ""
                if mode and mode.upper() in ("MRT", "BUS"):
                    mode_clause = "WHERE ts.stop_type IN ('MRT_STATION', 'MRT_EXIT')" if mode.upper() == "MRT" else "WHERE ts.stop_type = 'BUS_STOP'"

                query = f"""
                    SELECT 
                        vpc.stop_code, ts.stop_name, ts.stop_type,
                        vpc.hour_of_day, vpc.commuter_volume, vpc.crowd_index,
                        ROUND(vpc.rolling_3hr_avg::numeric, 1) AS rolling_3hr_avg,
                        vpc.congestion_rank
                    FROM v_peak_congestion vpc
                    JOIN transit_stop ts ON vpc.stop_code = ts.stop_code
                    {mode_clause}
                    ORDER BY vpc.congestion_rank ASC, vpc.commuter_volume DESC
                    LIMIT %s;
                """
                cur.execute(query, (limit,))

            rows = cur.fetchall()
            return [
                {
                    "stop_code": r[0],
                    "stop_name": r[1],
                    "stop_type": r[2],
                    "hour": r[3],
                    "commuter_volume": r[4],
                    "crowd_index": r[5],
                    "rolling_3hr_avg": float(r[6]),
                    "congestion_rank": r[7]
                }
                for r in rows
            ]


@router.get("/comfort_routes")
def get_comfort_routes():
    """Query View 3: v_comfort_routes."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_id, route_name, stop_code, leg_mode, stop_order, stop_name
                FROM v_comfort_routes
                ORDER BY route_id, stop_order;
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "route_id": r[0],
                    "route_name": r[1],
                    "stop_code": r[2],
                    "leg_mode": r[3],
                    "stop_order": r[4],
                    "stop_name": r[5]
                }
                for r in rows
            ]


@router.get("/live_crowd")
def get_live_crowd_summary():
    """Get live crowd summary across transit modes."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    load_level, 
                    count(*) AS count
                FROM (
                    SELECT DISTINCT ON (stop_code) stop_code, load_level
                    FROM live_crowd_snapshot
                    ORDER BY stop_code, recorded_at DESC
                ) latest
                GROUP BY load_level;
                """
            )
            distribution = {r[0]: r[1] for r in cur.fetchall()}
            return {"distribution": distribution}
