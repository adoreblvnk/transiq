# AGENTS.md — TRANSIQ Engineering Standards

Mission: Build TRANSIQ (Sheltered Transit Router) to secure an A+ grade (≥80%, Excellent Band) in INF2003 Database Systems. Standard implementation rubrics cap baseline deliverables at Good (B+); this document defines the extra-credit standards required to reach the Excellent band.

## Context Pointers
- Architecture, BCNF DDL, Neo4j schema, and Cypher specs: read `transiq.md`.
- Course rubric and final report expectations: read `../project/Project Final Report.pdf` and `../project/FAQ.pdf`.
- Performance relevance and batch commit mechanisms: read `../project/.agents/db_optimizations_relevance.md`.

## The A+ Standard (Beyond Baseline Rubrics)
Standard grading evaluates basic CRUD, foreign keys, and working frontends. The Excellent (A+) band requires rigorous database engineering:
1. **Physical & Logical Optimization:** Every core read path must be backed by an index (B-tree on foreign keys and composite lookups; GiST R-tree on PostGIS geometries). Zero sequential scans on hot tables.
2. **Execution Plan Evidence:** Every query optimization claim must be validated via `EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL and `PROFILE` in Neo4j, demonstrating buffer hit rates, row estimate accuracy, and cost reductions.
3. **Dual-Database Parity:** Prove structural justification between SQL (PostgreSQL system of record) and NoSQL (Neo4j query projection). The projection script (`sync_pg_to_neo4j.py`) must be deterministic, automated, and batched.
4. **Algorithmic Complexity Control:** Prevent combinatorial path explosion in multi-modal routing by pre-computing walk edges via PostGIS and bounding Cypher traversal depth ($1..8$).
5. **Head-to-Head Benchmarking:** Empirical comparison across 3 core experiments using `hyperfine` with warmups, standard deviations, and latency percentiles (p50/p95/p99).

## Architecture & Technology Contracts
- **3-Tier Separation:** Streamlit UI (port 8501) → FastAPI application layer (port 8000) → PostgreSQL 16 + PostGIS 3.4 (port 5432) & Neo4j 5 Community (port 7687).
- **PostgreSQL Stack:** Image `postgis/postgis:16-3.4`. Access via raw `psycopg3` with native `ConnectionPool`. Bypasses heavyweight ORM abstraction to preserve query plan fidelity.
- **Neo4j Stack:** Image `neo4j:5-community`. Access via official `neo4j` Python driver. Native Cypher variable-length traversal with weighted penalty scoring.
- **Decoupled Linkage:** Cross-database entities link strictly via immutable natural keys (`stop_code`, `postal_code`). Engine-level cross-database foreign keys do not exist.

## Invariant Implementation Rules

### 1. Database Writes & Telemetry Ingestion
- Batch write operations inside explicit transactions. Use `UPDATE ... FROM (VALUES ...)` in PostgreSQL and `UNWIND $batch` in Cypher.
- Set `SET LOCAL synchronous_commit = off` for high-frequency telemetry ingestion (live crowd snapshots) to reduce WAL flush stalls. Maintain full durability (`synchronous_commit = on`) for master infrastructure and user profiles.

### 2. Query Formulation & Optimization
- Formulate all SQL queries to be SARGable: isolate indexed columns from expressions or function calls on the left-hand side of predicates.
- Enforce projection pushdown: enumerate explicit column names (`SELECT stop_code, stop_name ...`); omit wildcard projections (`SELECT *`).
- Prefer correlated `EXISTS` over `COUNT(*) > 0` for short-circuit evaluation.

### 3. Spatial Queries & Indexing
- Wrap all spatial proximity searches in `ST_DWithin(geom1::geography, geom2::geography, distance_m)` to leverage GiST R-tree spatial indexing.
- Use `ST_AsGeoJSON()` within PostgreSQL queries to offload spatial serialization from Python to the database engine.

## Step-by-Step Delivery Roadmap

Each milestone has clear, checkable completion criteria. Do not proceed to the next milestone until all completion criteria are verified.

### Phase 1: Environment & Orchestration
1. Create `docker-compose.yml` defining `postgres` (`postgis/postgis:16-3.4`), `neo4j` (`neo4j:5-community`), `api` (FastAPI), and `ui` (Streamlit).
2. Configure persistent volumes, environment bindings from `.env`, and container health checks.
- **Completion Criterion:** `docker compose up -d` brings all 4 containers to healthy state; `pg_isready` succeeds on 5432; Neo4j Cypher shell responds on 7687.

### Phase 2: Relational DDL & Constraints
1. Implement `database/schema.sql` defining all 12 BCNF tables, primary keys, `ON DELETE CASCADE` foreign keys, tuple/domain CHECK constraints, and GiST indexes.
2. Implement `database/views.sql` defining the 3 analytical views (`v_sheltered_access`, `v_peak_congestion`, `v_comfort_routes`).
- **Completion Criterion:** Running `psql -f database/schema.sql` creates all 12 tables and 3 views with zero syntax errors and passes constraint verification checks.

### Phase 3: Data Ingestion & Graph Projection
1. Implement `scripts/ingest_lta.py` to fetch, clean, and sample LTA DataMall, Data.gov.sg, and OneMap datasets into PostgreSQL master tables.
2. Implement `scripts/sync_pg_to_neo4j.py` to project relational master data into Neo4j nodes and pre-computed `:SHELTERED_WALK` / `:TRANSIT_RIDE` relationships via Cypher `UNWIND`.
- **Completion Criterion:** `SELECT COUNT(*) FROM transit_stop;` matches Neo4j `MATCH (n:BusStop) RETURN count(n);`; pathfinding query returns valid routes between test HDB and MRT coordinates.

### Phase 4: Query Benchmark Harness & API Layer
1. Implement FastAPI routes for multi-modal pathfinding, user profile CRUD, and live crowd ingestion.
2. Implement `scripts/benchmark_queries.py` executing the 5 query optimization pairs, outputting `EXPLAIN (ANALYZE, BUFFERS)` JSON plans and execution statistics.
- **Completion Criterion:** Benchmark script generates a reproducible markdown table and JSON artifact comparing Naive vs Optimized query runtime and buffer counts.

### Phase 5: Interactive Interface & Verification
1. Implement Streamlit interactive app with origin/destination input, mode sliders (Rain Shield, Comfort & Seats, Least Transfers), route map display, and benchmark inspector.
2. Verify all edge cases: direct walk only, transfer required, strict mode fallback when shelter is absent.
- **Completion Criterion:** User can select any origin postal code, choose a mode, receive 3 ranked transit itineraries with sheltered distance breakdowns, and inspect live `EXPLAIN ANALYZE` metrics.
