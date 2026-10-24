#!/usr/bin/env python3
"""
TRANSIQ — Query Optimization & Benchmarking Suite
Executes and compares the 5 query pairs and 3 head-to-head benchmarks
using PostgreSQL EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and Neo4j profiling.
Outputs detailed metrics on runtime, planning time, and buffer page accesses.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

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


def benchmark_pair_1(conn):
    print("\n-----------------------------------------------------------")
    print("Benchmark 1: Unsheltered Bus Stops (NOT IN vs NOT EXISTS)")
    print("-----------------------------------------------------------")

    # Formulation A: NOT IN subquery (Full table scan & NULL hazard)
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

    # Formulation B: NOT EXISTS with index pushdown
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
    SELECT lsa.stop_code
    FROM linkway_stop_access lsa
    JOIN transit_stop ts ON lsa.stop_code = ts.stop_code
    WHERE ts.stop_type = 'BUS_STOP' AND lsa.is_sheltered = TRUE
    INTERSECT
    SELECT lsa.stop_code
    FROM linkway_stop_access lsa
    JOIN transit_stop ts ON lsa.stop_code = ts.stop_code
    WHERE ts.stop_type = 'MRT_EXIT' AND lsa.is_sheltered = TRUE;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]

    # Formulation B: INNER JOIN on composite keys
    q_b = """
    SELECT DISTINCT b.stop_code
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
    LIMIT 500;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]

    # Formulation B: Window Function AVG() OVER (PARTITION BY)
    q_b = """
    SELECT
        stop_code, hour_of_day, commuter_volume,
        AVG(commuter_volume) OVER (
            PARTITION BY stop_code ORDER BY hour_of_day
            ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
        ) AS rolling_3hr_avg
    FROM historical_congestion_log
    WHERE day_type = 'WEEKDAY' AND hour_of_day BETWEEN 7 AND 9
    LIMIT 500;
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

    # Formulation A: Brute force ST_Distance calculation
    q_a = """
    SELECT h.postal_code, w.linkway_id
    FROM hdb_building h
    JOIN covered_linkway w 
      ON ST_Distance(h.geom::geography, w.geom::geography) <= 40
    WHERE h.postal_code = '640183'
    LIMIT 5;
    """
    plan_a = run_pg_explain(conn, q_a)
    t_a = plan_a["Execution Time"]

    # Formulation B: ST_DWithin with GiST Index
    q_b = """
    SELECT h.postal_code, w.linkway_id
    FROM hdb_building h
    JOIN covered_linkway w 
      ON ST_DWithin(h.geom::geography, w.geom::geography, 40)
    WHERE h.postal_code = '640183'
    LIMIT 5;
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


def run_all_benchmarks():
    print("=========================================================")
    print("  TRANSIQ — Automated Query Optimization Benchmark Suite ")
    print("=========================================================")
    conn = psycopg.connect(CONN_STR)
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    results = []
    try:
        results.append(benchmark_pair_1(conn))
        results.append(benchmark_pair_2(conn))
        results.append(benchmark_pair_3(conn))
        results.append(benchmark_pair_4(conn))
        results.append(benchmark_pair_5(conn, neo4j_driver))

        out_path = ROOT_DIR / "data" / "benchmark_results.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nAll benchmark results saved to {out_path}")
    finally:
        conn.close()
        neo4j_driver.close()


if __name__ == "__main__":
    run_all_benchmarks()
