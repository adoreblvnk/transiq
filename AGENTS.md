# INF2003 Agent Instructions

## Professor Profile & Assessment Style

### Dr. Tong Rong (Module Lead & Project Examiner)
- Focus: Evaluates core database competency: relational modeling, normalization, indexing, query optimization, and dual-database justification.
- Normalization: Demands formal BCNF verification with functional dependencies. Emphasizes identifying insertion and deletion anomalies on unnormalized tables.
- Query Optimization: Looks for relational algebra equivalents (selection and projection pushdown, avoiding unnecessary attributes). Evaluates execution plans (`EXPLAIN (ANALYZE, BUFFERS)`) comparing actual runtime, buffer page hits, and row estimates against naive formulations. Flags unindexed full table scans (`type: ALL`).
- Dual-Database Rubric: Requires explicit justification for both relational (PostgreSQL + PostGIS) and non-relational (Neo4j) databases. Checks whether NoSQL is independent or an automated projection derived from SQL.
- Penalties: Rejects superficial AI fluff, toy mock data, unindexed hot paths, or embedded toy databases (strictly hates SQLite).

## How the Human Wants Work Done

- Lean first output: Keep documents concise, direct, and readable.
- Zero AI markers: Do not use horizontal triple dashes (`---`), em dashes, or decorative ASCII comment banners.
- Proof over claims: Render diagrams via `plantuml` CLI, test SQL with `EXPLAIN (ANALYZE, BUFFERS)`, and run scripts to verify output before claiming completion.
- Architecture: Maintain a strict 3-tier setup (Streamlit UI -> FastAPI backend -> PostgreSQL + PostGIS and Neo4j).
- Tooling: Use `uv` for Python environments and package management.
- Authentic data: Ingest authentic datasets from LTA DataMall, Data.gov.sg, and OneMap. Use representative peak-hour sampling for large OD trip volumes.
