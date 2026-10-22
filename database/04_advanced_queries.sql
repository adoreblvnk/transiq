-- TRANSIQ: 6 Advanced SQL Patterns for INF2003

-- 1. Nested Subquery with NOT EXISTS: Find Unsheltered Bus Stops
-- Proves: Short-circuits on indexed lookup without scanning all access records; avoids NULL hazards of NOT IN.
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
ORDER BY ts.stop_name
LIMIT 20;

-- 2. Aggregate with GROUP BY / HAVING: Highly Congested Peak Stops
-- Proves: Aggregates over representative congestion logs and filters by group condition on crowd index.
SELECT
    ts.stop_name,
    hcl.pt_type,
    SUM(hcl.commuter_volume) AS total_morning_volume,
    ROUND(AVG(hcl.crowd_index), 2) AS avg_crowd_index,
    COUNT(*) AS record_count
FROM historical_congestion_log hcl
JOIN transit_stop ts ON hcl.stop_code = ts.stop_code
WHERE hcl.day_type = 'WEEKDAY'
  AND hcl.hour_of_day BETWEEN 7 AND 9
GROUP BY ts.stop_name, hcl.pt_type
HAVING AVG(hcl.crowd_index) >= 5
ORDER BY total_morning_volume DESC
LIMIT 10;

-- 3. Set Operation INTERSECT: Multi-Modal Sheltered Interchanges
-- Proves: Set-theoretic intersection between bus stops and MRT exits sharing sheltered walkway connections.
SELECT lsa.stop_code
FROM linkway_stop_access lsa
JOIN transit_stop ts ON lsa.stop_code = ts.stop_code
WHERE ts.stop_type = 'BUS_STOP' AND lsa.is_sheltered = TRUE

INTERSECT

SELECT lsa.stop_code
FROM linkway_stop_access lsa
JOIN transit_stop ts ON lsa.stop_code = ts.stop_code
WHERE ts.stop_type = 'MRT_EXIT' AND lsa.is_sheltered = TRUE;

-- 4. Recursive CTE: Multi-Hop Transit Baseline
-- Proves: Explores multi-hop transit paths with loop detection, tracking accumulated time and transfers.
WITH RECURSIVE TransitPath AS (
    SELECT from_stop_code, to_stop_code, service_no,
           est_travel_time_min AS total_time, 0 AS transfers,
           ARRAY[from_stop_code, to_stop_code] AS visited_stops
    FROM transit_route_segment
    WHERE from_stop_code = '28009'
    UNION ALL
    SELECT tp.from_stop_code, s.to_stop_code, s.service_no,
           tp.total_time + s.est_travel_time_min,
           tp.transfers + CASE WHEN tp.service_no = s.service_no THEN 0 ELSE 1 END,
           tp.visited_stops || s.to_stop_code
    FROM TransitPath tp
    JOIN transit_route_segment s ON tp.to_stop_code = s.from_stop_code
    WHERE NOT (s.to_stop_code = ANY(tp.visited_stops))
      AND tp.transfers <= 2
      AND tp.total_time <= 60
)
SELECT * FROM TransitPath
WHERE to_stop_code = '11389'
ORDER BY transfers ASC, total_time ASC
LIMIT 5;

-- 5. Window Functions: Rolling Hourly Congestion
-- Proves: Analytic windowing partitions by transit stop and calculates rolling 3-hour averages with dense rank.
SELECT
    stop_code, hour_of_day, commuter_volume,
    ROUND(AVG(commuter_volume) OVER (
        PARTITION BY stop_code ORDER BY hour_of_day
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ), 1) AS rolling_3hr_avg_volume,
    DENSE_RANK() OVER (
        PARTITION BY hour_of_day ORDER BY commuter_volume DESC
    ) AS peak_congestion_rank
FROM historical_congestion_log
WHERE day_type = 'WEEKDAY' AND hour_of_day BETWEEN 7 AND 9
LIMIT 20;

-- 6. PostGIS Spatial Buffer: HDB to Covered Walkways
-- Proves: GiST R-Tree index pruning with ST_DWithin and ST_ClosestPoint distance calculation.
SELECT
    h.postal_code, h.block_no, w.linkway_id, w.is_barrier_free,
    ROUND(ST_Distance(h.geom::geography,
          ST_ClosestPoint(w.geom, h.geom)::geography)::numeric, 1) AS distance_to_shelter_m
FROM hdb_building h
JOIN covered_linkway w ON ST_DWithin(h.geom::geography, w.geom::geography, 50)
WHERE h.postal_code = '640183'
ORDER BY distance_to_shelter_m ASC
LIMIT 10;
