-- View 1: Sheltered Walkway Access around HDBs
CREATE OR REPLACE VIEW v_sheltered_access AS
SELECT
    h.postal_code, h.block_no, h.town,
    l.linkway_id, l.is_barrier_free, l.roof_condition,
    lsa.walk_distance_m, lsa.is_sheltered
FROM hdb_building h
JOIN linkway_stop_access lsa ON lsa.stop_code IN (
    SELECT stop_code FROM transit_stop
    WHERE ST_DWithin(h.geom::geography, geom::geography, 500)
)
JOIN covered_linkway l ON l.linkway_id = lsa.linkway_id;

-- View 2: Peak Hour Congestion with Window Functions
CREATE OR REPLACE VIEW v_peak_congestion AS
SELECT
    stop_code,
    hour_of_day,
    commuter_volume,
    crowd_index,
    AVG(commuter_volume) OVER (
        PARTITION BY stop_code ORDER BY hour_of_day
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS rolling_3hr_avg,
    DENSE_RANK() OVER (
        PARTITION BY hour_of_day ORDER BY commuter_volume DESC
    ) AS congestion_rank
FROM historical_congestion_log
WHERE day_type = 'WEEKDAY' AND hour_of_day BETWEEN 7 AND 9;

-- View 3: Saved Comfort Routes & Stops
CREATE OR REPLACE VIEW v_comfort_routes AS
SELECT
    sr.route_id, sr.route_name, srs.stop_code, srs.leg_mode,
    srs.stop_order, ts.stop_name
FROM saved_route sr
JOIN saved_route_stop srs ON sr.route_id = srs.route_id
JOIN transit_stop ts ON srs.stop_code = ts.stop_code
WHERE sr.preferred_mode = 'COMFORT_SEATS'
ORDER BY sr.route_id, srs.stop_order;
