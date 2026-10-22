CREATE EXTENSION IF NOT EXISTS postgis;

-- 1. HDB Buildings
CREATE TABLE IF NOT EXISTS hdb_building (
    postal_code VARCHAR(6) PRIMARY KEY,
    block_no    VARCHAR(10)  NOT NULL,
    street_name VARCHAR(100) NOT NULL,
    town        VARCHAR(50)  NOT NULL,
    latitude    NUMERIC(9,6) NOT NULL,
    longitude   NUMERIC(9,6) NOT NULL,
    geom        GEOMETRY(Point, 4326) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_postal_len CHECK (LENGTH(postal_code) = 6),
    CONSTRAINT chk_lat_range  CHECK (latitude  BETWEEN 1.0 AND 1.5),
    CONSTRAINT chk_lon_range  CHECK (longitude BETWEEN 103.0 AND 104.5)
);
CREATE INDEX IF NOT EXISTS idx_hdb_geom ON hdb_building USING GIST (geom);

-- 2. Covered Linkways
CREATE TABLE IF NOT EXISTS covered_linkway (
    linkway_id        VARCHAR(50) PRIMARY KEY,
    length_meters     NUMERIC(6,2) NOT NULL CHECK (length_meters > 0),
    is_barrier_free   BOOLEAN DEFAULT TRUE,
    roof_condition    VARCHAR(20) DEFAULT 'GOOD'
        CHECK (roof_condition IN ('GOOD', 'DAMAGED', 'UNDER_MAINTENANCE')),
    geom              GEOMETRY(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_linkway_geom ON covered_linkway USING GIST (geom);

-- 3. Transit Stops
CREATE TABLE IF NOT EXISTS transit_stop (
    stop_code       VARCHAR(20) PRIMARY KEY,
    stop_name       VARCHAR(100) NOT NULL,
    stop_type       VARCHAR(10)  NOT NULL
        CHECK (stop_type IN ('BUS_STOP', 'MRT_EXIT', 'LRT_STOP')),
    mrt_line_code   VARCHAR(5),
    has_lift_access BOOLEAN DEFAULT TRUE,
    latitude        NUMERIC(9,6) NOT NULL,
    longitude   NUMERIC(9,6) NOT NULL,
    geom            GEOMETRY(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transit_stop_geom ON transit_stop USING GIST (geom);

-- 4. Transit Services
CREATE TABLE IF NOT EXISTS transit_service (
    service_no  VARCHAR(10) PRIMARY KEY,
    operator    VARCHAR(20) NOT NULL
        CHECK (operator IN ('SBST', 'SMRT', 'Tower', 'SLRT')),
    mode        VARCHAR(5)  NOT NULL
        CHECK (mode IN ('BUS', 'MRT', 'LRT'))
);

-- 5. Transit Route Segments
CREATE TABLE IF NOT EXISTS transit_route_segment (
    service_no          VARCHAR(10) NOT NULL
        REFERENCES transit_service(service_no) ON DELETE CASCADE,
    direction           INT NOT NULL CHECK (direction IN (1, 2)),
    stop_sequence       INT NOT NULL CHECK (stop_sequence > 0),
    from_stop_code      VARCHAR(20) NOT NULL
        REFERENCES transit_stop(stop_code) ON DELETE CASCADE,
    to_stop_code        VARCHAR(20) NOT NULL
        REFERENCES transit_stop(stop_code) ON DELETE CASCADE,
    est_travel_time_min NUMERIC(4,1) NOT NULL CHECK (est_travel_time_min > 0),
    distance_km         NUMERIC(5,2) NOT NULL CHECK (distance_km > 0),
    PRIMARY KEY (service_no, direction, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_route_seg_from ON transit_route_segment (from_stop_code);
CREATE INDEX IF NOT EXISTS idx_route_seg_to ON transit_route_segment (to_stop_code);

-- 6. Linkway Stop Access (M:N junction)
CREATE TABLE IF NOT EXISTS linkway_stop_access (
    linkway_id      VARCHAR(50) NOT NULL
        REFERENCES covered_linkway(linkway_id) ON DELETE CASCADE,
    stop_code       VARCHAR(20) NOT NULL
        REFERENCES transit_stop(stop_code) ON DELETE CASCADE,
    walk_distance_m NUMERIC(5,1) NOT NULL CHECK (walk_distance_m > 0),
    is_sheltered    BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (linkway_id, stop_code)
);
CREATE INDEX IF NOT EXISTS idx_linkway_access_stop ON linkway_stop_access (stop_code);

-- 7. Commuter Profiles
CREATE TABLE IF NOT EXISTS commuter_profile (
    user_id              SERIAL PRIMARY KEY,
    email                VARCHAR(100) UNIQUE NOT NULL,
    preferred_mode       VARCHAR(20) DEFAULT 'RAIN_SHIELD'
        CHECK (preferred_mode IN ('RAIN_SHIELD', 'COMFORT_SEATS', 'LEAST_TRANSFERS', 'FASTEST')),
    max_uncovered_walk_m INT DEFAULT 50 CHECK (max_uncovered_walk_m >= 0),
    require_barrier_free BOOLEAN DEFAULT FALSE,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Saved Routes
CREATE TABLE IF NOT EXISTS saved_route (
    route_id        SERIAL PRIMARY KEY,
    route_name      VARCHAR(100) NOT NULL,
    origin_postal   VARCHAR(6) NOT NULL
        REFERENCES hdb_building(postal_code),
    dest_postal     VARCHAR(6) NOT NULL
        REFERENCES hdb_building(postal_code),
    preferred_mode  VARCHAR(20) DEFAULT 'RAIN_SHIELD'
        CHECK (preferred_mode IN ('RAIN_SHIELD', 'COMFORT_SEATS', 'LEAST_TRANSFERS', 'FASTEST')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_origin_ne_dest CHECK (origin_postal <> dest_postal)
);
CREATE INDEX IF NOT EXISTS idx_saved_route_origin ON saved_route (origin_postal);
CREATE INDEX IF NOT EXISTS idx_saved_route_dest ON saved_route (dest_postal);

-- 9. Commuter Saved Routes (M:N junction)
CREATE TABLE IF NOT EXISTS commuter_saved_route (
    user_id    INT NOT NULL
        REFERENCES commuter_profile(user_id) ON DELETE CASCADE,
    route_id   INT NOT NULL
        REFERENCES saved_route(route_id) ON DELETE CASCADE,
    saved_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, route_id)
);

-- 10. Saved Route Stops (M:N junction)
CREATE TABLE IF NOT EXISTS saved_route_stop (
    route_id     INT NOT NULL
        REFERENCES saved_route(route_id) ON DELETE CASCADE,
    stop_code    VARCHAR(20) NOT NULL
        REFERENCES transit_stop(stop_code) ON DELETE CASCADE,
    stop_order   INT NOT NULL CHECK (stop_order > 0),
    leg_mode     VARCHAR(10) NOT NULL
        CHECK (leg_mode IN ('WALK', 'BUS', 'MRT', 'LRT')),
    PRIMARY KEY (route_id, stop_code, stop_order)
);
CREATE INDEX IF NOT EXISTS idx_saved_route_stop_code ON saved_route_stop (stop_code);

-- 11. Historical Congestion Log
CREATE TABLE IF NOT EXISTS historical_congestion_log (
    log_id           BIGSERIAL PRIMARY KEY,
    stop_code        VARCHAR(20) NOT NULL
        REFERENCES transit_stop(stop_code),
    day_type         VARCHAR(10) NOT NULL
        CHECK (day_type IN ('WEEKDAY', 'WEEKEND', 'HOLIDAY')),
    hour_of_day      INT NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    pt_type          VARCHAR(5) NOT NULL
        CHECK (pt_type IN ('BUS', 'TRAIN')),
    crowd_index      INT NOT NULL CHECK (crowd_index BETWEEN 1 AND 10),
    commuter_volume  INT NOT NULL CHECK (commuter_volume >= 0)
);
CREATE INDEX IF NOT EXISTS idx_congestion_lookup
    ON historical_congestion_log (stop_code, day_type, hour_of_day);

-- 12. Live Crowd Snapshot
CREATE TABLE IF NOT EXISTS live_crowd_snapshot (
    snapshot_id  BIGSERIAL PRIMARY KEY,
    stop_code    VARCHAR(20) NOT NULL
        REFERENCES transit_stop(stop_code),
    service_no   VARCHAR(10),
    load_level   VARCHAR(5) NOT NULL
        CHECK (load_level IN ('SEA', 'SDA', 'LSD', 'Low', 'Medium', 'High')),
    recorded_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_live_snapshot_stop ON live_crowd_snapshot (stop_code, recorded_at);
