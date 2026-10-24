#!/usr/bin/env python3
"""
TRANSIQ — Query Optimization & Benchmarking Suite
Executes and compares:
1. Five query pairs using PostgreSQL EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) & Neo4j Profiler:
   - Pair 1: Unsheltered Bus Stops (NOT IN vs NOT EXISTS)
   - Pair 2: Sheltered Interchanges (INTERSECT vs INNER JOIN)
   - Pair 3: Peak Congestion Ranking (Correlated Self-Join vs Window Function)
   - Pair 4: Proximity Search (ST_Distance vs ST_DWithin with GiST index)
   - Pair 5: Multi-Hop Transit Route (Recursive SQL CTE vs Neo4j Native Cypher)
2. Three Head-to-Head empirical experiments:
   - Experiment 1: Multi-Hop Route Finding Latency
   - Experiment 2: Live Crowd Update Throughput (Batched UPDATE vs Cypher UNWIND)
   - Experiment 3: Spatial Proximity Search Latency Distribution (p50/p95/p99)
"""

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import psycopg
from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

PG_USER = os.getenv("POSTGRES_USER", "transiq")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "transiq_secret")
PG_DB = os.getenv("POSTGRES_DB", "transiq_db")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
CONN_STR = f"dbname={PG_DB} user={PG_USER} password={PG_PASS} host={PG_HOST} port={PG_PORT}"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "transiq_secret")


def run_pg_explain(conn, query: str, params: tuple | None = None) -> Dict[str, Any]:
    with conn.cursor() as cur:
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
        cur.execute(explain_sql, params or ())
        row = cur.fetchone()
        plan_json = row[0][0] if row else {}
        return plan_json


# ---------------------------------------------------------------------------
# Part 1: The Five Query Optimization Benchmark Pairs
# ---------------------------------------------------------------------------

def benchmark_pair_1(conn):
    print("\n-----------------------------------------------------------")
    print("Benchmark 1: Unsheltered Bus Stops (NOT IN vs NOT EXISTS)")
    print("-----------------------------------------------------------")

    # Formulation A: NOT IN subquery
    q_a = """
    SELECT ts.stop_code, ts.stop_name, ts.stop_type
    FROM transit_stop ts
    WHERE ts.stop_type = 'BUS_STOP'
      AND ts.stop_code NOT IN (
          SELECT lsa.stop_code FROM linkway_stop_access lsa
          JOIN covered_linkway l ON lsa.linkway_id = l.linkway_id
          WHERE lsa.is_sheltered = TRUE AND lsa.walk_distance_m <= 200
      )
    ORDER BY ts.stop_name;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]
    hits_a = plan_a["Plan"].get("Shared Hit Blocks", 0)

    # Formulation B: Correlated NOT EXISTS with index
    q_b = """
    SELECT ts.stop_code, ts.stop_name, ts.stop_type
    FROM transit_stop ts
    WHERE ts.stop_type = 'BUS_STOP'
      AND NOT EXISTS (
          SELECT 1 FROM linkway_stop_access lsa
          JOIN covered_linkway l ON lsa.linkway_id = l.linkway_id
          WHERE lsa.stop_code = ts.stop_code
            AND lsa.is_sheltered = TRUE
            AND lsa.walk_distance_m <= 200
      )
    ORDER BY ts.stop_name;
    """
    plan_b = run_pg_explain(conn, q_b)
    t_b = plan_b["Execution Time"]
    hits_b = plan_b["Plan"].get("Shared Hit Blocks", 0)

    speedup = t_a / max(0.001, t_b)
    print(f"  Formulation A (NOT IN):     {t_a:.2f} ms | Buffer Hits: {hits_a}")
    print(f"  Formulation B (NOT EXISTS): {t_b:.2f} ms | Buffer Hits: {hits_b}")
    print(f"  Result: Formulation B is {speedup:.1f}x faster.")
    return {"pair": 1, "name": "Unsheltered Bus Stops", "time_a": t_a, "time_b": t_b, "speedup": speedup}


def benchmark_pair_2(conn):
    print("\n-----------------------------------------------------------")
    print("Benchmark 2: Sheltered Interchanges (INTERSECT vs INNER JOIN)")
    print("-----------------------------------------------------------")

    # Formulation A: INTERSECT set operation
    q_a = """
    SELECT lsa.linkway_id
    FROM linkway_stop_access lsa
    JOIN transit_stop ts ON lsa.stop_code = ts.stop_code
    WHERE ts.stop_type = 'BUS_STOP' AND lsa.is_sheltered = TRUE
    INTERSECT
    SELECT lsa.linkway_id
    FROM linkway_stop_access lsa
    JOIN transit_stop ts ON lsa.stop_code = ts.stop_code
    WHERE ts.stop_type = 'MRT_EXIT' AND lsa.is_sheltered = TRUE;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]

    # Formulation B: INNER JOIN on composite keys
    q_b = """
    SELECT DISTINCT b.linkway_id
    FROM linkway_stop_access b
    JOIN transit_stop ts_b ON b.stop_code = ts_b.stop_code AND ts_b.stop_type = 'BUS_STOP'
    JOIN linkway_stop_access m ON b.linkway_id = m.linkway_id
    JOIN transit_stop ts_m ON m.stop_code = ts_m.stop_code AND ts_m.stop_type = 'MRT_EXIT'
    WHERE b.is_sheltered = TRUE AND m.is_sheltered = TRUE;
    """
    plan_b = run_pg_explain(conn, q_b)
    t_b = plan_b["Execution Time"]

    speedup = t_a / max(0.001, t_b)
    print(f"  Formulation A (INTERSECT):  {t_a:.2f} ms")
    print(f"  Formulation B (INNER JOIN): {t_b:.2f} ms")
    print(f"  Result: Formulation B is {speedup:.1f}x faster.")
    return {"pair": 2, "name": "Sheltered Interchanges", "time_a": t_a, "time_b": t_b, "speedup": speedup}


def benchmark_pair_3(conn):
    print("\n-----------------------------------------------------------")
    print("Benchmark 3: Peak Congestion (Self-Join vs Window Function)")
    print("-----------------------------------------------------------")

    # Formulation A: Correlated self-join per hour
    q_a = """
    SELECT 
        h1.stop_code, h1.hour_of_day, h1.commuter_volume,
        (SELECT AVG(h2.commuter_volume)
         FROM historical_congestion_log h2
         WHERE h2.stop_code = h1.stop_code
           AND h2.day_type = 'WEEKDAY'
           AND h2.hour_of_day BETWEEN h1.hour_of_day - 1 AND h1.hour_of_day + 1
        ) AS rolling_avg
    FROM historical_congestion_log h1
    WHERE h1.day_type = 'WEEKDAY' AND h1.hour_of_day BETWEEN 7 AND 9
    LIMIT 1000;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]

    # Formulation B: Single-pass window function
    q_b = """
    SELECT 
        stop_code, hour_of_day, commuter_volume,
        AVG(commuter_volume) OVER (
            PARTITION BY stop_code ORDER BY hour_of_day
            ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
        ) AS rolling_avg,
        DENSE_RANK() OVER (
            PARTITION BY hour_of_day ORDER BY commuter_volume DESC
        ) AS congestion_rank
    FROM historical_congestion_log
    WHERE day_type = 'WEEKDAY' AND hour_of_day BETWEEN 7 AND 9
    LIMIT 1000;
    """
    plan_b = run_pg_explain(conn, q_b)
    t_b = plan_b["Execution Time"]

    speedup = t_a / max(0.001, t_b)
    print(f"  Formulation A (Self-Join):        {t_a:.2f} ms")
    print(f"  Formulation B (Window Function):  {t_b:.2f} ms")
    print(f"  Result: Formulation B is {speedup:.1f}x faster.")
    return {"pair": 3, "name": "Peak Congestion Ranking", "time_a": t_a, "time_b": t_b, "speedup": speedup}


def benchmark_pair_4(conn):
    print("\n-----------------------------------------------------------")
    print("Benchmark 4: Proximity Search (ST_Distance vs ST_DWithin GiST)")
    print("-----------------------------------------------------------")

    # Formulation A: Brute-force ST_Distance across all rows
    q_a = """
    SELECT h.postal_code, w.linkway_id
    FROM hdb_building h, covered_linkway w
    WHERE h.postal_code = '640183'
      AND ST_Distance(h.geom::geography, w.geom::geography) <= 50;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]

    # Formulation B: ST_DWithin using GiST R-Tree index
    q_b = """
    SELECT h.postal_code, w.linkway_id
    FROM hdb_building h
    JOIN covered_linkway w ON ST_DWithin(h.geom, w.geom, 0.00045)
    WHERE h.postal_code = '640183';
    """
    plan_b = run_pg_explain(conn, q_b)
    t_b = plan_b["Execution Time"]

    speedup = t_a / max(0.001, t_b)
    print(f"  Formulation A (ST_Distance):       {t_a:.2f} ms")
    print(f"  Formulation B (ST_DWithin + GiST): {t_b:.2f} ms")
    print(f"  Result: Formulation B is {speedup:.1f}x faster.")
    return {"pair": 4, "name": "Proximity to Linkway", "time_a": t_a, "time_b": t_b, "speedup": speedup}


def benchmark_pair_5(conn, neo4j_driver):
    print("\n-----------------------------------------------------------")
    print("Benchmark 5: Multi-Hop Transit Route (SQL Recursive CTE vs Neo4j Cypher)")
    print("-----------------------------------------------------------")

    # Formulation A: SQL Recursive CTE across transit_route_segment
    q_sql = """
    WITH RECURSIVE TransitPath AS (
        SELECT from_stop_code, to_stop_code, service_no,
               est_travel_time_min::numeric AS total_time, 0 AS transfers,
               ARRAY[from_stop_code, to_stop_code]::varchar[] AS visited_stops
        FROM transit_route_segment
        WHERE from_stop_code = '28009'
        UNION ALL
        SELECT tp.from_stop_code, s.to_stop_code, s.service_no,
               (tp.total_time + s.est_travel_time_min)::numeric,
               tp.transfers + CASE WHEN tp.service_no = s.service_no THEN 0 ELSE 1 END,
               tp.visited_stops || s.to_stop_code
        FROM TransitPath tp
        JOIN transit_route_segment s ON tp.to_stop_code = s.from_stop_code
        WHERE NOT (s.to_stop_code = ANY(tp.visited_stops))
          AND tp.transfers <= 1
          AND tp.total_time <= 30
    )
    SELECT * FROM TransitPath
    WHERE to_stop_code = '11389'
    ORDER BY transfers ASC, total_time ASC
    LIMIT 3;
    """
    plan_sql = run_pg_explain(conn, q_sql)
    t_sql = plan_sql["Execution Time"]

    # Formulation B: Native Cypher variable-length traversal in Neo4j
    q_cypher = """
    MATCH p = (start:BusStop {code: '28009'})-[:TRANSIT_RIDE*1..4]->(dest:BusStop {code: '11389'})
    WITH p, [r IN relationships(p)] AS legs
    RETURN [n IN nodes(p) | n.code] AS path,
           size(legs) AS num_legs,
           reduce(t = 0.0, r IN legs | t + r.avg_duration_min) AS total_time
    LIMIT 3;
    """
    t0 = time.perf_counter()
    with neo4j_driver.session() as session:
        session.run(q_cypher).consume()
    t_neo4j = (time.perf_counter() - t0) * 1000.0

    speedup = t_sql / max(0.001, t_neo4j)
    print(f"  SQL Recursive CTE (PostgreSQL): {t_sql:.2f} ms")
    print(f"  Native Cypher Graph (Neo4j):    {t_neo4j:.2f} ms")
    print(f"  Result: Neo4j Graph traversal is {speedup:.1f}x faster for multi-hop pathfinding.")
    return {"pair": 5, "name": "Multi-Hop Transit Route", "time_sql": t_sql, "time_neo4j": t_neo4j, "speedup": speedup}


# ---------------------------------------------------------------------------
# Part 2: The Three Head-to-Head Empirical Experiments
# ---------------------------------------------------------------------------

def run_experiment_1_multihop(conn, neo4j_driver) -> Dict[str, Any]:
    print("\n-----------------------------------------------------------")
    print("Experiment 1: Multi-Hop Route Finding (Warm Latency Across 10 Runs)")
    print("-----------------------------------------------------------")
    sql_times = []
    neo4j_times = []

    q_sql = """
    WITH RECURSIVE TransitPath AS (
        SELECT from_stop_code, to_stop_code, service_no, est_travel_time_min::numeric AS total_time, 0 AS transfers,
               ARRAY[from_stop_code, to_stop_code]::varchar[] AS visited_stops
        FROM transit_route_segment WHERE from_stop_code = '28009'
        UNION ALL
        SELECT tp.from_stop_code, s.to_stop_code, s.service_no, (tp.total_time + s.est_travel_time_min)::numeric,
               tp.transfers + 1, tp.visited_stops || s.to_stop_code
        FROM TransitPath tp
        JOIN transit_route_segment s ON tp.to_stop_code = s.from_stop_code
        WHERE NOT (s.to_stop_code = ANY(tp.visited_stops)) AND tp.transfers <= 1 AND tp.total_time <= 30
    )
    SELECT * FROM TransitPath WHERE to_stop_code = '11389' LIMIT 3;
    """
    q_cypher = """
    MATCH p = (start:BusStop {code: '28009'})-[:TRANSIT_RIDE*1..4]->(dest:BusStop {code: '11389'})
    RETURN [n IN nodes(p) | n.code] AS path LIMIT 3;
    """

    for _ in range(10):
        # SQL run
        t0 = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(q_sql)
            cur.fetchall()
        sql_times.append((time.perf_counter() - t0) * 1000.0)

        # Neo4j run
        t0 = time.perf_counter()
        with neo4j_driver.session() as session:
            session.run(q_cypher).consume()
        neo4j_times.append((time.perf_counter() - t0) * 1000.0)

    avg_sql = float(np.mean(sql_times))
    avg_neo = float(np.mean(neo4j_times))
    print(f"  SQL Average Latency:   {avg_sql:.2f} ms")
    print(f"  Neo4j Average Latency: {avg_neo:.2f} ms")
    print(f"  Speedup:               {avg_sql / max(0.01, avg_neo):.1f}x")
    return {
        "experiment": 1,
        "name": "Multi-Hop Route Finding Latency",
        "sql_avg_ms": round(avg_sql, 2),
        "neo4j_avg_ms": round(avg_neo, 2),
        "speedup": round(avg_sql / max(0.01, avg_neo), 1),
    }


def run_experiment_2_throughput(conn, neo4j_driver) -> Dict[str, Any]:
    print("\n-----------------------------------------------------------")
    print("Experiment 2: Live Crowd Update Throughput (1,000 Stop Telemetry Mutations)")
    print("-----------------------------------------------------------")

    with conn.cursor() as cur:
        cur.execute("SELECT stop_code FROM transit_stop LIMIT 1000;")
        stops = [r[0] for r in cur.fetchall()]

    updates = [(s, random.choice(["SEA", "SDA", "LSD"])) for s in stops]

    # PostgreSQL: Group Commit via UPDATE FROM (VALUES ...)
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        values_str = ", ".join(f"('{s}', '{l}')" for s, l in updates)
        sql = f"""
        UPDATE live_crowd_snapshot AS lcs
        SET load_level = v.load_level, recorded_at = NOW()
        FROM (VALUES {values_str}) AS v(stop_code, load_level)
        WHERE lcs.stop_code = v.stop_code;
        """
        cur.execute(sql)
        conn.commit()
    t_sql_sec = time.perf_counter() - t0
    sql_rate = len(updates) / max(0.001, t_sql_sec)

    # Neo4j: Batched Cypher UNWIND write transaction
    neo_batch = [{"stop_code": s, "load_level": l} for s, l in updates]
    t0 = time.perf_counter()
    with neo4j_driver.session() as session:
        session.run(
            """
            UNWIND $batch AS item
            MATCH (:BusStop {code: item.stop_code})-[r:TRANSIT_RIDE]->()
            SET r.live_load = item.load_level
            """,
            batch=neo_batch,
        ).consume()
    t_neo_sec = time.perf_counter() - t0
    neo_rate = len(updates) / max(0.001, t_neo_sec)

    print(f"  PostgreSQL UPDATE FROM VALUES: {sql_rate:.1f} updates/sec ({t_sql_sec*1000:.1f} ms total)")
    print(f"  Neo4j Cypher UNWIND:           {neo_rate:.1f} updates/sec ({t_neo_sec*1000:.1f} ms total)")
    return {
        "experiment": 2,
        "name": "Live Crowd Update Throughput",
        "updates_count": len(updates),
        "sql_updates_per_sec": round(sql_rate, 1),
        "sql_duration_ms": round(t_sql_sec * 1000.0, 1),
        "neo4j_updates_per_sec": round(neo_rate, 1),
        "neo4j_duration_ms": round(t_neo_sec * 1000.0, 1),
    }


def run_experiment_3_proximity(conn, neo4j_driver) -> Dict[str, Any]:
    print("\n-----------------------------------------------------------")
    print("Experiment 3: Spatial Proximity Search Latency Distribution (50 Points)")
    print("-----------------------------------------------------------")

    with conn.cursor() as cur:
        cur.execute("SELECT latitude, longitude FROM hdb_building LIMIT 50;")
        coords = [(float(r[0]), float(r[1])) for r in cur.fetchall()]

    sql_latencies = []
    neo_latencies = []

    q_sql = """
    SELECT stop_code FROM transit_stop
    WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326), 0.0045)
    LIMIT 10;
    """
    q_neo = """
    MATCH (b:BusStop)
    WHERE point.distance(b.location, point({latitude: $lat, longitude: $lon})) <= 500
    RETURN b.code LIMIT 10;
    """

    for lat, lon in coords:
        # SQL GiST query
        t0 = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(q_sql, (lon, lat))
            cur.fetchall()
        sql_latencies.append((time.perf_counter() - t0) * 1000.0)

        # Neo4j spatial point.distance query
        t0 = time.perf_counter()
        with neo4j_driver.session() as session:
            session.run(q_neo, lat=lat, lon=lon).consume()
        neo_latencies.append((time.perf_counter() - t0) * 1000.0)

    p50_sql, p95_sql, p99_sql = np.percentile(sql_latencies, [50, 95, 99])
    p50_neo, p95_neo, p99_neo = np.percentile(neo_latencies, [50, 95, 99])

    print(f"  PostGIS GiST R-Tree: p50={p50_sql:.2f} ms | p95={p95_sql:.2f} ms | p99={p99_sql:.2f} ms")
    print(f"  Neo4j point.distance: p50={p50_neo:.2f} ms | p95={p95_neo:.2f} ms | p99={p99_neo:.2f} ms")
    return {
        "experiment": 3,
        "name": "Spatial Proximity Search Latency Distribution",
        "sample_points": len(coords),
        "postgis": {
            "p50_ms": round(float(p50_sql), 2),
            "p95_ms": round(float(p95_sql), 2),
            "p99_ms": round(float(p99_sql), 2),
        },
        "neo4j": {
            "p50_ms": round(float(p50_neo), 2),
            "p95_ms": round(float(p95_neo), 2),
            "p99_ms": round(float(p99_neo), 2),
        },
    }


def run_all_benchmarks():
    print("=========================================================")
    print("  TRANSIQ — Automated Query Optimization Benchmark Suite ")
    print("=========================================================")
    conn = psycopg.connect(CONN_STR)
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    results = []
    head_to_head = []
    try:
        # Part 1: Five Optimization Pairs
        results.append(benchmark_pair_1(conn))
        results.append(benchmark_pair_2(conn))
        results.append(benchmark_pair_3(conn))
        results.append(benchmark_pair_4(conn))
        results.append(benchmark_pair_5(conn, neo4j_driver))

        # Part 2: Three Head-to-Head Experiments
        head_to_head.append(run_experiment_1_multihop(conn, neo4j_driver))
        head_to_head.append(run_experiment_2_throughput(conn, neo4j_driver))
        head_to_head.append(run_experiment_3_proximity(conn, neo4j_driver))

        out_data = {
            "pairs": results,
            "head_to_head": head_to_head,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        out_path = ROOT_DIR / "data" / "benchmark_results.json"
        with open(out_path, "w") as f:
            json.dump(out_data, f, indent=2)
        print(f"\nAll benchmark results and experiments saved to {out_path}")
    finally:
        conn.close()
        neo4j_driver.close()


if __name__ == "__main__":
    run_all_benchmarks()
