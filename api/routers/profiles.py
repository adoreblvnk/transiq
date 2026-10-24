"""Router for Commuter Profiles and Saved Routes (Relational CRUD)."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from api.services.db import get_pg_connection

router = APIRouter(prefix="/api/profiles", tags=["Profiles & Saved Routes"])


class ProfileCreate(BaseModel):
    email: str
    preferred_mode: str = "RAIN_SHIELD"
    max_uncovered_walk_m: int = 50
    require_barrier_free: bool = False


class RouteCreate(BaseModel):
    user_id: int
    route_name: str
    origin_postal: str
    dest_postal: str
    preferred_mode: str = "RAIN_SHIELD"
    stops: List[str] = []


@router.get("/")
def list_profiles():
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, email, preferred_mode, max_uncovered_walk_m, require_barrier_free, created_at
                FROM commuter_profile
                ORDER BY user_id;
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "user_id": r[0],
                    "email": r[1],
                    "preferred_mode": r[2],
                    "max_uncovered_walk_m": r[3],
                    "require_barrier_free": r[4],
                    "created_at": str(r[5])
                }
                for r in rows
            ]


@router.post("/")
def create_profile(p: ProfileCreate):
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO commuter_profile (email, preferred_mode, max_uncovered_walk_m, require_barrier_free)
                    VALUES (%s, %s, %s, %s)
                    RETURNING user_id, created_at;
                    """,
                    (p.email, p.preferred_mode, p.max_uncovered_walk_m, p.require_barrier_free)
                )
                res = cur.fetchone()
                conn.commit()
                return {"user_id": res[0], "email": p.email, "created_at": str(res[1])}
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.get("/{user_id}/saved_routes")
def get_user_saved_routes(user_id: int):
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sr.route_id, sr.route_name, sr.origin_postal, sr.dest_postal, sr.preferred_mode, csr.saved_at
                FROM commuter_saved_route csr
                JOIN saved_route sr ON csr.route_id = sr.route_id
                WHERE csr.user_id = %s
                ORDER BY csr.saved_at DESC;
                """,
                (user_id,)
            )
            rows = cur.fetchall()
            return [
                {
                    "route_id": r[0],
                    "route_name": r[1],
                    "origin_postal": r[2],
                    "dest_postal": r[3],
                    "preferred_mode": r[4],
                    "saved_at": str(r[5])
                }
                for r in rows
            ]


@router.post("/save_route")
def save_route(r: RouteCreate):
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO saved_route (route_name, origin_postal, dest_postal, preferred_mode)
                    VALUES (%s, %s, %s, %s)
                    RETURNING route_id;
                    """,
                    (r.route_name, r.origin_postal, r.dest_postal, r.preferred_mode)
                )
                route_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO commuter_saved_route (user_id, route_id)
                    VALUES (%s, %s);
                    """,
                    (r.user_id, route_id)
                )

                for idx, stop_code in enumerate(r.stops, 1):
                    cur.execute(
                        """
                        INSERT INTO saved_route_stop (route_id, stop_code, stop_order, leg_mode)
                        VALUES (%s, %s, %s, 'TRANSIT')
                        ON CONFLICT DO NOTHING;
                        """,
                        (route_id, stop_code, idx)
                    )

                conn.commit()
                return {"status": "success", "route_id": route_id}
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))
