# TRANSIQ — Door-to-Door Sheltered Transit Routing Engine

**Course:** INF2003 Database Systems | **Group:** G42

## What It Does

Singapore navigation apps optimize for shortest travel time and ignore rain, sun and crush-load transit in the process. TRANSIQ is a door-to-door, multi-modal routing engine that paths commuters from an HDB void deck to a destination lobby over covered linkways, tracks live crowding telemetry (`SEA` / `SDA` / `LSD`), and lets commuters trade seconds of travel time for shelter, seats and fewer transfers.

It runs on a dual-database architecture: **PostgreSQL 16 + PostGIS 3.4** as the ACID system of record (12 BCNF relations, GiST spatial indexes, analytical views), and **Neo4j 5 Community** as an automated query-optimized graph projection built from PostgreSQL by `scripts/sync_pg_to_neo4j.py`.

![System Architecture](diagrams/architecture.png)
![ER Diagram](diagrams/er_diagram.png)

The full report lives in [`transiq.md`](transiq.md) (dataset strategy, BCNF functional dependency proofs, advanced SQL, Cypher traversal). The frontend design system lives in [`DESIGN.md`](DESIGN.md).

## Data

Ten authentic datasets from Singapore government repositories (LTA DataMall, Data.gov.sg, OneMap):

| Dataset | Source | Format | Records |
| :--- | :--- | :--- | ---: |
| Covered Linkway Network | LTA DataMall | Shapefile (ZIP) | 7,183 |
| HDB Property Information | Data.gov.sg | CSV | 13,389 |
| Singapore Building Geocodes | OneMap / DataMall | JSON | 141,726 |
| Bus Stops Islandwide | LTA DataMall | JSON | 5,209 |
| Bus Routes & Sequences | LTA DataMall | JSON | 26,036 |
| Bus Services | LTA DataMall | JSON | 808 |
| MRT/LRT Station Exits | Data.gov.sg | GeoJSON | 613 |
| MRT Network Sequences | LTA Operating Schedules | JSON | 326 |
| Historical Congestion Logs | LTA Passenger Volume OD | SQL COPY | 53,775 |
| Live Crowd Snapshots | LTA Platform Telemetry | Dynamic SQL | 1,000 |

## Results

Benchmarks across 5 query pairs, measured with `EXPLAIN (ANALYZE, BUFFERS)` on PostgreSQL and the Neo4j profiler:

| Optimization | Naive (A) | Optimized (B) | Speedup |
| :--- | ---: | ---: | ---: |
| Unsheltered stops (`NOT IN` → `NOT EXISTS`) | 16.07 ms | 9.34 ms | 1.7x |
| Sheltered interchanges (`INTERSECT` → `INNER JOIN`) | 4.46 ms | 3.87 ms | 1.2x |
| Peak congestion ranking (self-join → `AVG() OVER (PARTITION BY)`) | 1.53 ms | 0.45 ms | 3.4x |
| Proximity to linkway (`ST_Distance` → `ST_DWithin` + GiST) | 78.31 ms | 0.11 ms | 686.9x |
| Multi-hop route (recursive SQL CTE → Cypher traversal) | 219.26 ms | 17.85 ms | 12.3x |

## Quickstart

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, and [`uv`](https://docs.astral.sh/uv/) for host-side scripts.

```bash
# macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

1. Clone and configure:

```bash
git clone https://github.com/adoreblvnk/transiq.git
cd transiq
cp .env.example .env
```

2. Place the raw upstream datasets in `data/raw/`: `bus_stops.json`, `bus_routes.json`, `bus_services.json`, `buildings.json`, `hdb_property_info.csv`, `mrt_exits.geojson`, `CoveredLinkWay.zip`. Upstream government data is not committed to the repository.

3. Start the services (Postgres, Neo4j, FastAPI). Compose initializes the schema automatically:

```bash
docker compose up -d
```

4. Ingest the data and project the graph. Databases start empty; these fill them:

```bash
uv run scripts/ingest_lta.py        # load all datasets into PostgreSQL + PostGIS
uv run scripts/sync_pg_to_neo4j.py  # batched Cypher UNWIND projection into Neo4j
```

5. Verify:

```bash
uv run pytest tests/test_api.py -v
uv run scripts/smoke_verify.py
uv run scripts/benchmark_queries.py
```

Optional: `bash scripts/run_pgbench.sh` and `bash scripts/run_hyperfine.sh` for native concurrency and statistical query benchmarks.

## Access

| Interface | URL |
| :--- | :--- |
| Web application (FastAPI serves `frontend/`) | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 (`neo4j` / `transiq_secret`) |

The frontend offers five commuter modes: Fastest (default), Balanced (shelter + comfort), Fully Sheltered (100% covered, with a strict filter toggle), Less Crowd, and Fewer Transfers. It includes a Leaflet map on OneMap tiles, SVG congestion and benchmark charts, and a live WAL durability tester (`synchronous_commit` ON vs OFF).

## Teardown

```bash
docker compose down    # stops containers, keeps data volumes
docker compose down -v # also wipes database volumes for a fresh start
```

## Contributors (Team G42)

- **Joseph Poon (2501079)** — Data engineering, PostGIS spatial buffers, ingestion pipeline
- **Zayne Nicholas Lee (2503844)** — Relational modeling, BCNF normalization, PostgreSQL DDL
- **Tan Yan Qi (2500030)** — Neo4j graph projection, Cypher traversal, graph optimization
- **Annie Goh (2503469)** — FastAPI query backend, REST endpoints, psycopg3 connection pool
- **Ryan Ke (2501911)** — Frontend dashboard, Leaflet map integration, hyperfine benchmarking
