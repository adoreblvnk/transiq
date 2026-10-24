#!/usr/bin/env python3
"""
TRANSIQ — PostgreSQL to Neo4j Graph Projection Engine
Projects relational transit topology and spatial buffers into Neo4j:
- Nodes: (:HDBBlock), (:BusStop), (:MRTExit), (:CommercialBuilding)
- Edges:
  - [:TRANSIT_RIDE {service, avg_duration_min, distance_km, live_load}]
  - [:SHELTERED_WALK {distance_m, is_covered: true, has_ramp: true, barrier_free: true}]
  - [:UNSHELTERED_WALK {distance_m, is_covered: false}]
  - [:STATION_TRANSFER {walking_time_min, is_sheltered: true, escalator_count}]

Uses batched Cypher UNWIND transactions for optimal throughput.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import psycopg
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Setup root directory
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

sys.path.insert(0, str(ROOT_DIR))
from scripts.mrt_data import get_interchange_transfers

BATCH_SIZE = 2000


def get_pg_conn():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "transiq_db"),
        user=os.getenv("POSTGRES_USER", "transiq"),
        password=os.getenv("POSTGRES_PASSWORD", "transiq_secret"),
    )


def get_neo4j_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "transiq_secret")
    return GraphDatabase.driver(uri, auth=(user, password))


def setup_constraints(session):
    print("Setting up Neo4j constraints and indexes...")
    constraints = [
        "CREATE CONSTRAINT unique_hdb_postal IF NOT EXISTS FOR (h:HDBBlock) REQUIRE h.postal_code IS UNIQUE",
        "CREATE CONSTRAINT unique_bus_stop IF NOT EXISTS FOR (b:BusStop) REQUIRE b.code IS UNIQUE",
        "CREATE CONSTRAINT unique_mrt_exit IF NOT EXISTS FOR (m:MRTExit) REQUIRE m.id IS UNIQUE",
        "CREATE CONSTRAINT unique_comm_postal IF NOT EXISTS FOR (c:CommercialBuilding) REQUIRE c.postal_code IS UNIQUE",
        "CREATE INDEX idx_bus_stop_name IF NOT EXISTS FOR (b:BusStop) ON (b.name)",
        "CREATE INDEX idx_mrt_exit_stn IF NOT EXISTS FOR (m:MRTExit) ON (m.station_code)",
    ]
    for c in constraints:
        session.run(c)


def sync_nodes(pg_conn, session):
    print("\n--- Projecting Graph Nodes ---")
    with pg_conn.cursor() as cur:
        # 1. Bus Stops
        cur.execute("SELECT stop_code, stop_name, latitude, longitude FROM transit_stop WHERE stop_type = 'BUS_STOP';")
        bus_stops = [
            {"code": r[0], "name": r[1], "lat": float(r[2]), "lon": float(r[3])}
            for r in cur.fetchall()
        ]
        print(f"Projecting {len(bus_stops)} BusStop nodes...")
        for i in range(0, len(bus_stops), BATCH_SIZE):
            batch = bus_stops[i:i + BATCH_SIZE]
            session.run(
                """
                UNWIND $batch AS row
                MERGE (b:BusStop {code: row.code})
                SET b.name = row.name, b.lat = row.lat, b.lon = row.lon,
                    b.location = point({latitude: row.lat, longitude: row.lon})
                """,
                batch=batch,
            )

        # 2. MRT Exits / Stations
        cur.execute("SELECT stop_code, stop_name, mrt_line_code, latitude, longitude FROM transit_stop WHERE stop_type = 'MRT_EXIT';")
        mrt_exits = [
            {"id": r[0], "name": r[1], "stn_code": r[2] or "", "lat": float(r[3]), "lon": float(r[4])}
            for r in cur.fetchall()
        ]
        print(f"Projecting {len(mrt_exits)} MRTExit nodes...")
        for i in range(0, len(mrt_exits), BATCH_SIZE):
            batch = mrt_exits[i:i + BATCH_SIZE]
            session.run(
                """
                UNWIND $batch AS row
                MERGE (m:MRTExit {id: row.id})
                SET m.name = row.name, m.station_code = row.stn_code, m.lat = row.lat, m.lon = row.lon,
                    m.location = point({latitude: row.lat, longitude: row.lon})
                """,
                batch=batch,
            )

        # 3. HDB Blocks
        cur.execute("SELECT postal_code, block_no, street_name, town, latitude, longitude FROM hdb_building;")
        hdbs = [
            {"postal_code": r[0], "block_no": r[1], "street_name": r[2], "town": r[3], "lat": float(r[4]), "lon": float(r[5])}
            for r in cur.fetchall()
        ]
        print(f"Projecting {len(hdbs)} HDBBlock nodes...")
        for i in range(0, len(hdbs), BATCH_SIZE):
            batch = hdbs[i:i + BATCH_SIZE]
            session.run(
                """
                UNWIND $batch AS row
                MERGE (h:HDBBlock {postal_code: row.postal_code})
                SET h.block_no = row.block_no, h.street_name = row.street_name, h.town = row.town,
                    h.lat = row.lat, h.lon = row.lon,
                    h.location = point({latitude: row.lat, longitude: row.lon})
                """,
                batch=batch,
            )

        # 4. Commercial Buildings (from buildings.json)
        bldgs_file = ROOT_DIR / "data" / "raw" / "buildings.json"
        if bldgs_file.exists():
            with open(bldgs_file) as f:
                all_bldgs = json.load(f)

            comm_keywords = ["MALL", "CENTRE", "TOWER", "BUILDING", "PLAZA", "COMPLEX", "POINT", "HUB"]
            comm_list = []
            seen_postals = set()
            for b in all_bldgs:
                name = str(b.get("BUILDING", "")).strip().upper()
                postal = str(b.get("POSTAL", "")).strip().zfill(6)
                if len(postal) == 6 and postal.isdigit() and postal not in seen_postals:
                    if any(kw in name for kw in comm_keywords) and "HDB" not in name:
                        lat = float(b["LATITUDE"])
                        lon = float(b["LONGITUDE"])
                        if 1.0 <= lat <= 1.5 and 103.0 <= lon <= 104.5:
                            seen_postals.add(postal)
                            comm_list.append({
                                "postal_code": postal,
                                "name": name[:100],
                                "lat": lat,
                                "lon": lon,
                            })
                            if len(comm_list) >= 2000:
                                break

            print(f"Projecting {len(comm_list)} CommercialBuilding nodes...")
            for i in range(0, len(comm_list), BATCH_SIZE):
                batch = comm_list[i:i + BATCH_SIZE]
                session.run(
                    """
                    UNWIND $batch AS row
                    MERGE (c:CommercialBuilding {postal_code: row.postal_code})
                    SET c.name = row.name, c.lat = row.lat, c.lon = row.lon,
                        c.location = point({latitude: row.lat, longitude: row.lon})
                    """,
                    batch=batch,
                )


def sync_transit_rides(pg_conn, session):
    print("\n--- Projecting TRANSIT_RIDE Edges ---")
    with pg_conn.cursor() as cur:
        # Fetch transit route segments with live load levels
        cur.execute(
            """
            SELECT 
                trs.from_stop_code,
                trs.to_stop_code,
                trs.service_no,
                trs.direction,
                trs.est_travel_time_min,
                trs.distance_km,
                COALESCE(lcs.load_level, 'SEA') AS live_load,
                ts_from.stop_type AS from_type,
                ts_to.stop_type AS to_type
            FROM transit_route_segment trs
            JOIN transit_stop ts_from ON trs.from_stop_code = ts_from.stop_code
            JOIN transit_stop ts_to ON trs.to_stop_code = ts_to.stop_code
            LEFT JOIN (
                SELECT DISTINCT ON (stop_code) stop_code, load_level
                FROM live_crowd_snapshot
                ORDER BY stop_code, recorded_at DESC
            ) lcs ON trs.from_stop_code = lcs.stop_code;
            """
        )
        rows = cur.fetchall()

    bus_to_bus = []
    mrt_to_mrt = []

    for r in rows:
        item = {
            "from_code": r[0],
            "to_code": r[1],
            "service": str(r[2]),
            "duration": float(r[4]),
            "dist": float(r[5]),
            "load": r[6],
        }
        if r[7] == "BUS_STOP" and r[8] == "BUS_STOP":
            bus_to_bus.append(item)
        else:
            mrt_to_mrt.append(item)

    print(f"Projecting {len(bus_to_bus)} Bus-to-Bus TRANSIT_RIDE edges...")
    for i in range(0, len(bus_to_bus), BATCH_SIZE):
        batch = bus_to_bus[i:i + BATCH_SIZE]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (from:BusStop {code: row.from_code})
            MATCH (to:BusStop {code: row.to_code})
            MERGE (from)-[r:TRANSIT_RIDE {service: row.service}]->(to)
            SET r.avg_duration_min = row.duration,
                r.distance_km = row.dist,
                r.live_load = row.load
            """,
            batch=batch,
        )

    print(f"Projecting {len(mrt_to_mrt)} MRT-to-MRT TRANSIT_RIDE edges...")
    for i in range(0, len(mrt_to_mrt), BATCH_SIZE):
        batch = mrt_to_mrt[i:i + BATCH_SIZE]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (from:MRTExit {id: row.from_code})
            MATCH (to:MRTExit {id: row.to_code})
            MERGE (from)-[r:TRANSIT_RIDE {service: row.service}]->(to)
            SET r.avg_duration_min = row.duration,
                r.distance_km = row.dist,
                r.live_load = row.load
            """,
            batch=batch,
        )


def sync_station_transfers(session):
    print("\n--- Projecting STATION_TRANSFER Edges ---")
    transfers = get_interchange_transfers()
    print(f"Projecting {len(transfers)} interchange STATION_TRANSFER edges...")
    for i in range(0, len(transfers), BATCH_SIZE):
        batch = transfers[i:i + BATCH_SIZE]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (from:MRTExit {id: row.from_stop_code})
            MATCH (to:MRTExit {id: row.to_stop_code})
            MERGE (from)-[r:STATION_TRANSFER]->(to)
            SET r.walking_time_min = row.transfer_time_min,
                r.is_sheltered = row.is_sheltered,
                r.distance_m = row.walk_distance_m,
                r.escalator_count = 2
            """,
            batch=batch,
        )


def sync_walkway_connections(pg_conn, session):
    print("\n--- Projecting SHELTERED_WALK & UNSHELTERED_WALK Edges ---")
    with pg_conn.cursor() as cur:
        # A. Sheltered Walkways (HDB to Bus Stops connected via covered linkways)
        print("Fetching sheltered HDB-to-BusStop links from PostGIS...")
        t0 = time.time()
        cur.execute(
            """
            SELECT DISTINCT
                h.postal_code,
                ts.stop_code,
                GREATEST(10.0, ROUND(ST_Distance(h.geom::geography, ts.geom::geography)::numeric, 1)) AS distance_m
            FROM hdb_building h
            JOIN transit_stop ts ON ST_DWithin(h.geom, ts.geom, 0.0030)
            JOIN linkway_stop_access lsa ON lsa.stop_code = ts.stop_code
            WHERE ts.stop_type = 'BUS_STOP'
            LIMIT 25000;
            """
        )
        sheltered_hdb_bus = [
            {"hdb_postal": r[0], "stop_code": r[1], "dist": float(r[2])}
            for r in cur.fetchall()
        ]
        print(f"  Found {len(sheltered_hdb_bus)} sheltered HDB-to-Bus links in {time.time()-t0:.2f}s.")

        print("Projecting SHELTERED_WALK (HDB <-> BusStop) edges...")
        for i in range(0, len(sheltered_hdb_bus), BATCH_SIZE):
            batch = sheltered_hdb_bus[i:i + BATCH_SIZE]
            session.run(
                """
                UNWIND $batch AS row
                MATCH (h:HDBBlock {postal_code: row.hdb_postal})
                MATCH (b:BusStop {code: row.stop_code})
                MERGE (h)-[r1:SHELTERED_WALK]->(b)
                SET r1.distance_m = row.dist, r1.is_covered = true, r1.has_ramp = true, r1.barrier_free = true
                MERGE (b)-[r2:SHELTERED_WALK]->(h)
                SET r2.distance_m = row.dist, r2.is_covered = true, r2.has_ramp = true, r2.barrier_free = true
                """,
                batch=batch,
            )

        # B. Sheltered Walkways (HDB to MRT Exits)
        print("Fetching sheltered HDB-to-MRTExit links from PostGIS...")
        cur.execute(
            """
            SELECT DISTINCT
                h.postal_code,
                ts.stop_code,
                GREATEST(10.0, ROUND(ST_Distance(h.geom::geography, ts.geom::geography)::numeric, 1)) AS distance_m
            FROM hdb_building h
            JOIN transit_stop ts ON ST_DWithin(h.geom, ts.geom, 0.0040)
            JOIN linkway_stop_access lsa ON lsa.stop_code = ts.stop_code
            WHERE ts.stop_type = 'MRT_EXIT'
            LIMIT 15000;
            """
        )
        sheltered_hdb_mrt = [
            {"hdb_postal": r[0], "stop_code": r[1], "dist": float(r[2])}
            for r in cur.fetchall()
        ]
        print(f"  Found {len(sheltered_hdb_mrt)} sheltered HDB-to-MRT links.")

        print("Projecting SHELTERED_WALK (HDB <-> MRTExit) edges...")
        for i in range(0, len(sheltered_hdb_mrt), BATCH_SIZE):
            batch = sheltered_hdb_mrt[i:i + BATCH_SIZE]
            session.run(
                """
                UNWIND $batch AS row
                MATCH (h:HDBBlock {postal_code: row.hdb_postal})
                MATCH (m:MRTExit {id: row.stop_code})
                MERGE (h)-[r1:SHELTERED_WALK]->(m)
                SET r1.distance_m = row.dist, r1.is_covered = true, r1.has_ramp = true, r1.barrier_free = true
                MERGE (m)-[r2:SHELTERED_WALK]->(h)
                SET r2.distance_m = row.dist, r2.is_covered = true, r2.has_ramp = true, r2.barrier_free = true
                """,
                batch=batch,
            )

        # C. Sheltered Walkways (CommercialBuilding to MRT Exits)
        session.run(
            """
            MATCH (c:CommercialBuilding), (m:MRTExit)
            WHERE point.distance(c.location, m.location) <= 300
            MERGE (m)-[r1:SHELTERED_WALK]->(c)
            SET r1.distance_m = round(point.distance(c.location, m.location)),
                r1.is_covered = true, r1.has_ramp = true, r1.barrier_free = true
            MERGE (c)-[r2:SHELTERED_WALK]->(m)
            SET r2.distance_m = round(point.distance(c.location, m.location)),
                r2.is_covered = true, r2.has_ramp = true, r2.barrier_free = true
            """
        )

        # D. Unsheltered Walkways (HDB to nearby Bus Stops NOT covered by linkways)
        print("Fetching unsheltered HDB-to-BusStop links from PostGIS...")
        cur.execute(
            """
            SELECT DISTINCT
                h.postal_code,
                ts.stop_code,
                GREATEST(10.0, ROUND(ST_Distance(h.geom::geography, ts.geom::geography)::numeric, 1)) AS distance_m
            FROM hdb_building h
            JOIN transit_stop ts ON ST_DWithin(h.geom, ts.geom, 0.0020)
            WHERE ts.stop_type = 'BUS_STOP'
              AND ts.stop_code NOT IN (SELECT stop_code FROM linkway_stop_access)
            LIMIT 15000;
            """
        )
        unsheltered_hdb_bus = [
            {"hdb_postal": r[0], "stop_code": r[1], "dist": float(r[2])}
            for r in cur.fetchall()
        ]
        print(f"  Found {len(unsheltered_hdb_bus)} unsheltered HDB-to-Bus links.")

        print("Projecting UNSHELTERED_WALK edges...")
        for i in range(0, len(unsheltered_hdb_bus), BATCH_SIZE):
            batch = unsheltered_hdb_bus[i:i + BATCH_SIZE]
            session.run(
                """
                UNWIND $batch AS row
                MATCH (h:HDBBlock {postal_code: row.hdb_postal})
                MATCH (b:BusStop {code: row.stop_code})
                MERGE (h)-[r1:UNSHELTERED_WALK]->(b)
                SET r1.distance_m = row.dist, r1.is_covered = false
                MERGE (b)-[r2:UNSHELTERED_WALK]->(h)
                SET r2.distance_m = row.dist, r2.is_covered = false
                """,
                batch=batch,
            )


def main():
    print("=========================================================")
    print("  TRANSIQ — PostgreSQL to Neo4j Graph Projection Engine  ")
    print("=========================================================")
    t_start = time.time()

    pg_conn = get_pg_conn()
    driver = get_neo4j_driver()

    try:
        with driver.session() as session:
            setup_constraints(session)
            sync_nodes(pg_conn, session)
            sync_transit_rides(pg_conn, session)
            sync_station_transfers(session)
            sync_walkway_connections(pg_conn, session)

            # Verification Counts
            res = session.run("MATCH (n) RETURN count(n) AS total_nodes").single()
            total_nodes = res["total_nodes"] if res else 0

            res_r = session.run("MATCH ()-[r]->() RETURN count(r) AS total_rels").single()
            total_rels = res_r["total_rels"] if res_r else 0

            print(f"\nGraph Projection complete! Verified Neo4j State:")
            print(f"  Total Nodes: {total_nodes}")
            print(f"  Total Relationships: {total_rels}")
            print(f"Total time elapsed: {time.time()-t_start:.1f}s")
    finally:
        pg_conn.close()
        driver.close()


if __name__ == "__main__":
    main()
