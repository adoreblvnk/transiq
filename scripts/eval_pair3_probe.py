#!/usr/bin/env python3
"""Evaluation probe: reproduce Pair 3 plan shapes and the recursive CTE plan
on a synthetic, scale-faithful seed (same schema + indexes as 01_schema.sql).
Writes findings to stdout only."""

import psycopg, os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
conn = psycopg.connect("dbname=transiq_db user=transiq password=transiq_secret host=localhost port=5432")
conn.autocommit = True
cur = conn.cursor()

# ---------------------------------------------------------------- seed
cur.execute("TRUNCATE historical_congestion_log, transit_route_segment, transit_service, transit_stop, hdb_building CASCADE")

cur.execute("""
    INSERT INTO transit_stop (stop_code, stop_name, stop_type, latitude, longitude, geom)
    SELECT 'S' || lpad(g::text, 5, '0'), 'Stop ' || g, 'BUS_STOP',
           1.2 + (g % 500) * 0.0005, 103.6 + (g % 900) * 0.0005,
           ST_SetSRID(ST_MakePoint(103.6 + (g % 900) * 0.0005, 1.2 + (g % 500) * 0.0005), 4326)
    FROM generate_series(1, 6000) g
""")

# 6,000 stops x (5 peak-shoulder weekday hours x 2 pt types) + (2 weekend hours x 2 pt types)
# = 60,000 rows; qualifying WEEKDAY + 7..9 = 36,000 rows
cur.execute("""
    INSERT INTO historical_congestion_log (stop_code, day_type, hour_of_day, pt_type, crowd_index, commuter_volume)
    SELECT s.stop_code,
           CASE WHEN h.good THEN 'WEEKDAY' ELSE 'WEEKEND' END,
           CASE WHEN h.good THEN h.h ELSE 12 + (g % 2) END,
           'BUS',
           1 + (g + h.h) % 10,
           100 + ((g * 31 + h.h * 17) % 4000)
    FROM transit_stop s
    CROSS JOIN LATERAL generate_series(0, 1) g
    CROSS JOIN (SELECT 6 AS h, true AS good UNION ALL SELECT 7, true UNION ALL
                SELECT 8, true UNION ALL SELECT 9, true UNION ALL
                SELECT 10, true UNION ALL SELECT 0, false UNION ALL SELECT 23, false) h
""")
cur.execute("ANALYZE historical_congestion_log")

cur.execute("SELECT count(*) FROM historical_congestion_log")
print("seeded congestion rows:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM historical_congestion_log WHERE day_type='WEEKDAY' AND hour_of_day BETWEEN 7 AND 9")
print("qualifying peak rows:", cur.fetchone()[0])

# ------------------------------------------------------- pair 3: fresh plan
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
LIMIT 1000;"""

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
LIMIT 1000;"""

# warm both once so cache state resembles the benchmark run
for q in (q_a, q_b):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) " + q)
    cur.fetchone()

def dump(n, d=0):
    t = n.get("Node Type")
    extra = ""
    if t == "Sort":
        extra = " [" + ", ".join(n.get("Sort Key") or ["<external>"]) + "]"
        extra += f" method={n.get('Sort Method')} space={n.get('Sort Space Used')}kB {n.get('Sort Space Type')}"
    if "Index Name" in n:
        extra = f" idx={n['Index Name']}"
    loops = n.get("Actual Loops", 0)
    print("  " * d + f"{t}{extra} rows={n.get('Actual Rows')} loops={loops} "
          f"time={n.get('Actual Total Time') or 0:.2f} hit={n.get('Shared Hit Blocks')}")
    for c in n.get("Plans", []):
        dump(c, d + 1)

for label, q in (("A) correlated self-join", q_a), ("B) window functions", q_b)):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + q)
    plan = cur.fetchone()[0][0]
    print(f"\n=== {label}")
    print(f"Execution {plan['Execution Time']:.2f} ms (Planning {plan['Planning Time']:.2f} ms, "
          f"buffers hit={plan['Plan'].get('Shared Hit Blocks')})")
    dump(plan["Plan"])

# ------------------------------------- semantic boundary divergence check
# A reads its +/-1h window from the RAW table (hours 6..10 exist in seed),
# B's frame sees only rows already filtered to 7..9. Compare hour=7 values.
cur.execute("""
    SELECT 'A: raw 6..8 window' AS source,
           round(avg(commuter_volume), 1) AS rolling_avg_at_hour7
    FROM historical_congestion_log
    WHERE stop_code = 'S00001' AND day_type = 'WEEKDAY' AND hour_of_day BETWEEN 6 AND 8
    UNION ALL
    SELECT 'B: filtered 7..8 (frame look at first partition row)',
           round(avg(commuter_volume), 1)
    FROM historical_congestion_log
    WHERE stop_code = 'S00001' AND day_type = 'WEEKDAY' AND hour_of_day BETWEEN 7 AND 9
      AND hour_of_day IN (7, 8)
""")
print("\nRolling average for stop S00001 at hour_of_day = 7:")
for src, val in cur.fetchall():
    print(f"  {src}: {val}")
print("  -> The two formulations disagree at peak-window boundary rows; Pair 3 is not a pure apples-to-apples pair.")

# ------------------------------------- pair 5 recursive CTE plan shape
cur.execute("""
    INSERT INTO transit_service (service_no, operator, mode)
    SELECT 'SVC' || lpad(g::text, 3, '0'), 'SBST', 'BUS' FROM generate_series(1, 40) g
""")
cur.execute("""
    INSERT INTO transit_route_segment (service_no, direction, stop_sequence, from_stop_code, to_stop_code,
                                       est_travel_time_min, distance_km)
    SELECT 'SVC' || lpad(((s % 40) + 1)::text, 3, '0'), 1, stop_seq,
           'S' || lpad(a::text, 5, '0'), 'S' || lpad(b::text, 5, '0'),
           2.0 + ((a + b) % 5), 1.0
    FROM (
        SELECT a, (a % 6000) + 1 + CASE WHEN i % 2 = 0 THEN i ELSE -i END AS b,
               i AS stop_seq, a % 40 AS s
        FROM generate_series(1, 1000) a
        CROSS JOIN generate_series(1, 4) i
    ) t
    WHERE b BETWEEN 1 AND 6000
    ON CONFLICT DO NOTHING
""")
cur.execute("ANALYZE transit_route_segment")

q_sql = """
WITH RECURSIVE TransitPath AS (
    SELECT from_stop_code, to_stop_code, service_no,
           est_travel_time_min::numeric AS total_time, 0 AS transfers,
           ARRAY[from_stop_code::varchar, to_stop_code::varchar]::varchar[] AS visited_stops
    FROM transit_route_segment
    WHERE from_stop_code = 'S00009'
    UNION ALL
    SELECT tp.from_stop_code, s.to_stop_code, s.service_no,
           tp.total_time + s.est_travel_time_min,
           tp.transfers + CASE WHEN tp.service_no = s.service_no THEN 0 ELSE 1 END,
           tp.visited_stops || s.to_stop_code
    FROM TransitPath tp
    JOIN transit_route_segment s ON tp.to_stop_code = s.from_stop_code
    WHERE NOT (s.to_stop_code = ANY(tp.visited_stops))
      AND tp.transfers <= 1
      AND tp.total_time <= 30
)
SELECT * FROM TransitPath
WHERE to_stop_code = 'S05999'
ORDER BY transfers ASC, total_time ASC
LIMIT 3;"""

cur.execute("EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) " + q_sql)
plan = cur.fetchone()[0][0]
print(f"\n=== Pair 5 SQL recursive CTE: Execution {plan['Execution Time']:.2f} ms")
dump(plan["Plan"])
conn.close()
