// Uniqueness constraints
CREATE CONSTRAINT unique_hdb_postal IF NOT EXISTS
FOR (h:HDBBlock) REQUIRE h.postal_code IS UNIQUE;

CREATE CONSTRAINT unique_bus_stop IF NOT EXISTS
FOR (b:BusStop) REQUIRE b.code IS UNIQUE;

CREATE CONSTRAINT unique_mrt_exit IF NOT EXISTS
FOR (m:MRTExit) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT unique_comm_postal IF NOT EXISTS
FOR (c:CommercialBuilding) REQUIRE c.postal_code IS UNIQUE;

// Indexes for fast spatial and name lookups
CREATE INDEX idx_bus_stop_name IF NOT EXISTS
FOR (b:BusStop) ON (b.name);

CREATE INDEX idx_mrt_exit_station IF NOT EXISTS
FOR (m:MRTExit) ON (m.station_code);
