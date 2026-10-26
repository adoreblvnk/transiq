# TRANSIQ Frontend

Self-contained Technical Editorial Brutalism web application for door-to-door sheltered transit routing in Singapore.

## Architecture

- **Entrypoint**: `frontend/index.html` (served at `http://localhost:8000/` via FastAPI).
- **Design System**: Fully specified in [`DESIGN.md`](../DESIGN.md).
- **Map Engine**: Leaflet 1.9 with official Singapore Land Authority (SLA) OneMap tiles.
- **Visualizations**: LayerCake-inspired responsive SVG coordinate scales (Journey timeline, Hourly congestion density, Benchmark latencies).
- **Syntax Highlighting**: Highlight.js for Neo4j Cypher and PostgreSQL CTE query inspection.
- **Accessibility**: 100/100 WCAG 2.2 AA compliant (high-contrast ratios $\ge 4.5:1$, single-border focus wrappers, accessible dialogs).

## Key Features

1. **Multi-Modal Router**:
   - Single-card active route display with proportional LayerCake timeline.
   - Pinned 100vh layout: top controls stay fixed while turn-by-turn directions scroll independently.
   - 5 commuter modes: `Fastest` (default), `Balanced` (shelter + comfort), `Fully Sheltered` (100% covered linkway hard cap), `Less Crowd`, and `Fewer Transfers`.
2. **Transit Crowding Telemetry**:
   - Hourly commuter density distribution column chart with 3-hour moving average line.
   - Station rankings with custom TRANSIQ-themed dropdown filters (`All Modes`, `MRT`, `Bus`).
   - Materialized view refresh with non-intrusive toast notification.
3. **Dual-Database Benchmarks**:
   - 5-pair optimization verification comparing Optimized Dual-DB latency vs Naive SQL baseline.
   - Live WAL durability benchmark runner testing commit throughput (`synchronous_commit = ON` vs `OFF`).
