# TRANSIQ — Door-to-Door Sheltered Transit Routing Engine

**Course:** INF2003 Database Systems  
**Group:** G42  
**Weightage:** 50% of Final Grade (25% Relational + 25% Non-Relational)  
**Target Grade:** A+ (>=80%, Excellent Band)

---

## 1. Executive Summary

Existing urban navigation platforms (Google Maps, Apple Maps, Citymapper) optimize strictly for shortest travel time in Euclidean space. In Singapore's tropical climate, this routes commuters through open plazas, scorching concrete walkways, and torrential downpours to save negligible seconds, or herds passengers onto crush-load (`LSD`) transit when seated options exist. Singapore's Land Transport Authority (LTA) has constructed over 100 kilometers of covered linkways under the Walk2Ride Programme, yet no commercial routing engine models or prioritizes them.

**TRANSIQ** is a door-to-door, multi-modal routing engine that navigates commuters from HDB void decks to destination lobbies via covered linkways, real-time crowding telemetry, and sheltered transit interchanges. It is built on a **dual-database architecture**: **PostgreSQL 16 with PostGIS 3.4** as the ACID system of record, and **Neo4j 5 Community** as an automated query-optimized graph projection.

![System Architecture](diagrams/architecture.png)

---

## 2. Dual-Database Justification & Division of Labor

A dual-database design is essential because relational engines and graph databases exhibit fundamentally different computational complexities for spatial network problems:

```
┌───────────────────────────────────────────────┐        ┌──────────────────────────────────────────────┐
│     PostgreSQL 16 + PostGIS 3.4               │        │     Neo4j 5 Community                        │
│     (System of Record — Port 5432)            │        │     (Query-Optimized Graph — Port 7687)      │
├───────────────────────────────────────────────┤        ├──────────────────────────────────────────────┤
│ • Boyce-Codd Normal Form (12 Relations)       │        │ • Direct Walkway & Transit Topology          │
│ • Strict ACID Durability & Foreign Key Cascades│        │ • O(1) Index-Free Pointer Hopping            │
│ • Spatial R-Tree Indexing (GiST ST_DWithin)   │───────>│ • Multi-Objective Weighted Cypher Traversal  │
│ • Analytical Views & Window Functions         │  ETL   │ • Sub-25ms Multi-Hop Route Finding           │
│ • Commuter Profiles & Historical OD Logs      │        │ • Volatile Live Load Telemetry Updates       │
└───────────────────────────────────────────────┘        └──────────────────────────────────────────────┘
```

1. **System of Record (PostgreSQL + PostGIS):**
   - Enforces transactional consistency across 12 BCNF relations, foreign key cascades, and check constraints.
   - Computes spatial buffering (`ST_DWithin`) using two-dimensional GiST R-Tree indexes to pre-calculate pedestrian accessibility between HDB blocks, linkways, and transit stops.
   - Executes complex analytical window queries (`AVG() OVER (PARTITION BY)`) across 50,000+ congestion logs.

2. **Query-Optimized Projection (Neo4j):**
   - Relational recursive CTEs across 26,000 route segments require multi-table memory stack joins.
   - Neo4j navigates physical pointers directly between nodes (`:HDBBlock`, `:BusStop`, `:MRTExit`, `:CommercialBuilding`) in constant time per hop.
   - Projected automatically from PostgreSQL views via batched Cypher `UNWIND` transactions (`scripts/sync_pg_to_neo4j.py`).

---

## 3. Authentic Singapore Datasets

TRANSIQ ingests authentic datasets from Singapore government open repositories (LTA DataMall, Data.gov.sg, OneMap):

| # | Dataset | Source | Format | Records | Role in TRANSIQ |
| :- | :--- | :--- | :--- | :--- | :--- |
| 1 | Covered Linkway Network | LTA DataMall (Static) | Shapefile (ZIP) | 7,183 linkways | Sheltered pedestrian walkway geometry |
| 2 | HDB Property Information | Data.gov.sg (Public API) | CSV | 13,389 blocks | Origin and destination residential anchors |
| 3 | Singapore Building Geocodes | OneMap & DataMall | JSON | 141,726 geocodes | Postal code to WGS84 coordinates |
| 4 | Bus Stops Islandwide | LTA DataMall (REST API) | JSON | 5,209 stops | Complete bus network stop coordinates |
| 5 | Bus Routes & Sequences | LTA DataMall (REST API) | JSON | 26,036 segments | Official stop sequences and road distances |
| 6 | Bus Services | LTA DataMall (REST API) | JSON | 808 services | Public bus operator and service registry |
| 7 | MRT/LRT Station Exits | Data.gov.sg (Public API) | GeoJSON | 613 exits | Exact street exits for 188 stations |
| 8 | MRT Network Sequences | LTA Operating Schedules | Python/JSON | 326 segments | Station sequences for EWL, NSL, NEL, CCL, DTL, TEL |
| 9 | Historical Congestion Logs | LTA Passenger Volume OD | SQL COPY | 53,775 rows | Representative peak-hour crowding indices |
| 10 | Live Crowd Snapshots | LTA Platform Telemetry | Dynamic SQL | 1,000 snapshots | Live load levels (`SEA`, `SDA`, `LSD`) |

---

## 4. Relational Architecture & BCNF Normalization

All 12 relations in PostgreSQL satisfy **Boyce-Codd Normal Form (BCNF)**: for every non-trivial functional dependency $X \rightarrow Y$, $X$ is a superkey.

![ER Diagram](diagrams/er_diagram.png)

### BCNF Decomposition & Functional Dependencies

| Table | Primary Key | Functional Dependencies | BCNF Satisfied |
| :--- | :--- | :--- | :--- |
| `hdb_building` | `postal_code` | `postal_code` $\rightarrow$ `block_no`, `street_name`, `town`, `lat`, `lon`, `geom` | Yes (PK) |
| `covered_linkway` | `linkway_id` | `linkway_id` $\rightarrow$ `length_meters`, `is_barrier_free`, `roof_condition`, `geom` | Yes (PK) |
| `transit_stop` | `stop_code` | `stop_code` $\rightarrow$ `stop_name`, `stop_type`, `mrt_line_code`, `has_lift`, `lat`, `lon`, `geom` | Yes (PK) |
| `transit_service` | `service_no` | `service_no` $\rightarrow$ `operator`, `mode` | Yes (PK) |
| `transit_route_segment` | `(service_no, direction, stop_sequence)` | `(service_no, direction, stop_sequence)` $\rightarrow$ `from_stop`, `to_stop`, `time_min`, `dist_km` | Yes (Composite PK) |
| `linkway_stop_access` | `(linkway_id, stop_code)` | `(linkway_id, stop_code)` $\rightarrow$ `walk_distance_m`, `is_sheltered` | Yes (Composite PK) |
| `commuter_profile` | `user_id` | `user_id` $\rightarrow$ `email`, `preferred_mode`; `email` $\rightarrow$ `user_id` | Yes (Both Superkeys) |
| `saved_route` | `route_id` | `route_id` $\rightarrow$ `route_name`, `origin_postal`, `dest_postal`, `preferred_mode` | Yes (PK) |
| `commuter_saved_route` | `(user_id, route_id)` | `(user_id, route_id)` $\rightarrow$ `saved_at` | Yes (Composite PK) |
| `saved_route_stop` | `(route_id, stop_code, stop_order)` | `(route_id, stop_code, stop_order)` $\rightarrow$ `leg_mode` | Yes (Composite PK) |
| `historical_congestion_log` | `log_id` | `log_id` $\rightarrow$ `stop_code`, `day_type`, `hour_of_day`, `pt_type`, `crowd_index`, `volume` | Yes (PK) |
| `live_crowd_snapshot` | `snapshot_id` | `snapshot_id` $\rightarrow$ `stop_code`, `service_no`, `load_level`, `recorded_at` | Yes (PK) |

### Analytical Views
1. `v_sheltered_access`: Pre-computes HDB-to-transit pedestrian shelter within 500m via PostGIS GiST index.
2. `v_peak_congestion`: Computes rolling 3-hour moving averages and hourly congestion ranks using window functions (`AVG() OVER (PARTITION BY ...)`).
3. `v_comfort_routes`: Filtered route itinerary view joining saved routes, commuter profiles, and transit stops for comfort-seeking commuters.

---

## 5. Non-Relational Graph Model & Cypher Traversal

### Graph Projection Topology
- **Node Labels:**
  - `(:HDBBlock {postal_code, block_no, street_name, town, lat, lon})`
  - `(:BusStop {code, name, lat, lon})`
  - `(:MRTExit {id, name, station_code, lat, lon})`
  - `(:CommercialBuilding {postal_code, name, lat, lon})`
- **Relationship Types:**
  - `[:SHELTERED_WALK {distance_m, is_covered: true, barrier_free: true}]`
  - `[:UNSHELTERED_WALK {distance_m, is_covered: false}]`
  - `[:TRANSIT_RIDE {service, avg_duration_min, distance_km, live_load}]`
  - `[:STATION_TRANSFER {walking_time_min, is_sheltered: true, escalator_count}]`

### Multi-Objective Weighted Scoring Formula
Commuter paths are scored and discovered through soft penalty weighting:
$$\text{Score} = \text{BaseTime} + (d_{\text{unsheltered}} \times W_{\text{unsh}}) + (N_{\text{lsd}} \times W_{\text{crowd}}) + (N_{\text{transfers}} \times W_{\text{trans}})$$

| Commuter Mode | Optimization Goal | $W_{\text{unsh}}$ | $W_{\text{crowd}}$ | $W_{\text{trans}}$ | Optional Strict Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Rain & Sun Shield** | Maximize covered linkways | 0.08 min/m | 2.0 min | 5.0 min | Rejects any route with unsheltered walking |
| **Comfort & Seats** | Avoid crush-load buses | 0.02 min/m | 20.0 min | 5.0 min | Rejects any route containing `LSD` transit legs |
| **Least Transfers** | Minimize step count & lines | 0.02 min/m | 5.0 min | 25.0 min | Hard cap on transfers, enforces barrier-free ramps |
| **Fastest** | Shortest journey duration | 0.005 min/m | 0.5 min | 1.0 min | Pure minimum elapsed transit time |

---

## 6. Query Optimization & EXPLAIN ANALYZE Matrix

To fulfill module requirements on execution plan optimization, TRANSIQ benchmarks 5 query pairs comparing alternative implementations using PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` and Neo4j profiler:

| # | Optimization Objective | Formulation A (Naive) | Formulation B (Optimized) | Runtime A | Runtime B | Measured Speedup | Execution Plan Evidence |
| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | Unsheltered Bus Stops | `NOT IN` subquery | Correlated `NOT EXISTS` | 16.07 ms | 9.34 ms | **1.7x** | Eliminates full table scan & NULL hazard; buffer hits drop from 1,651 to 263. |
| **2** | Sheltered Interchanges | `INTERSECT` set operation | `INNER JOIN` on access keys | 4.46 ms | 3.87 ms | **1.2x** | Replaces temporary HashAggregate set operation with indexed B-Tree join. |
| **3** | Peak Congestion Ranking | Correlated self-join per hour | `AVG() OVER (PARTITION BY)` | 1.53 ms | 0.45 ms | **3.4x** | Eliminates $O(N^2)$ repetitive scans; executes in a single sequential pass. |
| **4** | Proximity to Linkway | Brute-force `ST_Distance` | `ST_DWithin` with GiST index | 78.31 ms | 0.11 ms | **686.9x** | Bypasses 7,183 polygon distance calculations via GiST R-Tree bounding box pruning. |
| **5** | Multi-Hop Transit Route | Recursive SQL CTE | Native Cypher Graph Traversal | 219.26 ms | 17.85 ms | **12.3x** | Avoids recursive SQL memory stack joins via physical pointer hopping in Neo4j. |

---

## 7. Quickstart Guide

### Prerequisites
- Linux / macOS / Windows WSL2
- Python 3.14 (managed via `uv`)
- Docker & Docker Compose

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/adoreblvnk/transiq.git
cd transiq

# Copy environment variables (LTA DataMall & DB credentials pre-configured)
cp .env.example .env
```

### 2. Start Services via Docker Compose
```bash
docker compose up -d
```
This spins up:
- `transiq_postgres` (Port 5432) — PostgreSQL 16 with PostGIS 3.4
- `transiq_neo4j` (Ports 7474, 7687) — Neo4j 5 Community
- `transiq_api` (Port 8000) — FastAPI Query Backend
- `transiq_ui` (Port 8501) — Streamlit Interactive Dashboard

### 3. Ingest Data & Project Graph (Automated)
```bash
# Ingest 10 authentic Singapore datasets into PostgreSQL + PostGIS
uv run python scripts/ingest_lta.py

# Project relational tables into Neo4j graph via batched UNWIND
uv run python scripts/sync_pg_to_neo4j.py

# Run benchmark query suite
uv run python scripts/benchmark_queries.py
```

### 4. Run Verification Suite
```bash
# Run comprehensive pytest suite (9 tests)
uv run pytest tests/test_api.py -v

# Run full system smoke verification
uv run python scripts/smoke_verify.py
```

### 5. Access Interfaces
- **Streamlit Dashboard:** http://localhost:8501
- **FastAPI Interactive Docs:** http://localhost:8000/docs
- **Neo4j Browser:** http://localhost:7474 (User: `neo4j`, Password: `transiq_secret`)

---

## 8. Streamlit Dashboard Design System

The frontend dashboard strictly adheres to the boxy, high-contrast visual standard required by Dr. Tong Rong and the course specification:
- **Palette:** Clean slate background (`#F8FAFC`), pure white surface cards (`#FFFFFF`), slate typography (`#0F172A`), muted secondary labels (`#64748B`).
- **Geometry:** 4px crisp border-radius, clean 1px border (`#E2E8F0`), zero decorative AI bubbles or generic widgets.
- **Color Accents:** Sheltered walking green (`#16A34A`), transit blue (`#0284C7`), crowded amber (`#D97706`), crush-load red (`#DC2626`).
- **Interactive Features:**
  - Interactive Folium map with GeoJSON polylines and crowd badges.
  - 3 commuter modes switcher with strict filtering toggle.
  - Side-by-side SQL vs NoSQL benchmark viewer with live re-execution capability.
  - Commuter profile switcher and route saving (relational CRUD).

---

## 9. Deliverables & Rubric Compliance Matrix

| Rubric Component | Weight | Standard | TRANSIQ Evidence & Implementation |
| :--- | :--- | :--- | :--- |
| **Project Quality & Implementation** | **40%** | Innovative, sufficient authentic data, dual-DB | Door-to-door sheltered router; 10 authentic datasets (LTA & Data.gov.sg); 12 BCNF tables, 3 views, 6 SQL patterns; Neo4j graph with 22,000 nodes & 244,000 edges; 5-pair EXPLAIN ANALYZE matrix with up to 686x speedup. |
| **Final Report Quality** | **25%** | Comprehensive, implementation details, analysis | Complete DDL schema, ERD, formal BCNF functional dependency proofs for all 12 relations, Cypher traversal formulations, and scalability analysis. |
| **Presentation Quality** | **25%** | Clear, logical, results, conclusions | Streamlit live dashboard, interactive mode selector, side-by-side latency viewer, and clear trade-off analysis. |
| **Project Proposal** | **10%** | Clear scope, planning, coverage | 2-page proposal aligned, Gantt timeline, and team member task allocations. |

---

## 10. Contributors (Team G42)

- **Joseph Poon (2501079)** — Data Engineering, PostGIS Spatial Buffers, Ingestion Pipeline
- **Zayne Nicholas Lee (2503844)** — Relational Modeling, BCNF Normalization, PostgreSQL DDL
- **Tan Yan Qi (2500030)** — Neo4j Graph Projection, Cypher Traversal, Graph Optimization
- **Annie Goh (2503469)** — FastAPI Query Backend, REST Endpoints, psycopg3 Connection Pool
- **Ryan Ke (2501911)** — Streamlit UI Dashboard, Folium Map Integration, Hyperfine Benchmarking
