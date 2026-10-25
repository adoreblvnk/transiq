#!/usr/bin/env bash
# ==============================================================================
# TRANSIQ — Multi-Engine Statistical Query Benchmarks via hyperfine
# Measures: Mean, median, standard deviation, P95/P99 latency distribution
# Exports: data/hyperfine_results.json
# ==============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

RESULTS_DIR="${ROOT_DIR}/data"
mkdir -p "${RESULTS_DIR}"

if ! command -v hyperfine &> /dev/null; then
    echo "Error: hyperfine is not installed on host. Run 'brew install hyperfine'."
    exit 1
fi

echo "================================================================="
echo "  TRANSIQ hyperfine Statistical Benchmark Suite                  "
echo "================================================================="

# Benchmark Pair 4: Proximity Search (Brute force ST_Distance vs PostGIS GiST ST_DWithin)
echo ""
echo "--- Benchmark: Proximity to Linkway (ST_Distance vs PostGIS GiST) ---"
hyperfine \
  --warmup 2 \
  --runs 5 \
  --export-json "${RESULTS_DIR}/hyperfine_pair4.json" \
  --command-name "ST_Distance_Unindexed" \
  "docker exec -i transiq_postgres psql -U transiq -d transiq_db -c \"SELECT h.postal_code, count(w.linkway_id) FROM hdb_building h JOIN covered_linkway w ON ST_Distance(h.geom::geography, w.geom::geography) < 50 WHERE h.postal_code = '640183' GROUP BY h.postal_code;\"" \
  --command-name "ST_DWithin_GiST_Indexed" \
  "docker exec -i transiq_postgres psql -U transiq -d transiq_db -c \"SELECT h.postal_code, count(w.linkway_id) FROM hdb_building h JOIN covered_linkway w ON ST_DWithin(h.geom, w.geom, 0.00045) WHERE h.postal_code = '640183' GROUP BY h.postal_code;\""

# Benchmark Pair 1: Unsheltered Bus Stops (NOT IN vs Correlated NOT EXISTS)
echo ""
echo "--- Benchmark: Unsheltered Bus Stops (NOT IN vs NOT EXISTS) ---"
hyperfine \
  --warmup 2 \
  --runs 5 \
  --export-json "${RESULTS_DIR}/hyperfine_pair1.json" \
  --command-name "NOT_IN_Subquery" \
  "docker exec -i transiq_postgres psql -U transiq -d transiq_db -c \"SELECT ts.stop_code, ts.stop_name FROM transit_stop ts WHERE ts.stop_type = 'BUS_STOP' AND ts.stop_code NOT IN (SELECT stop_code FROM linkway_stop_access WHERE walk_distance_m <= 200) LIMIT 20;\"" \
  --command-name "NOT_EXISTS_Indexed" \
  "docker exec -i transiq_postgres psql -U transiq -d transiq_db -c \"SELECT ts.stop_code, ts.stop_name FROM transit_stop ts WHERE ts.stop_type = 'BUS_STOP' AND NOT EXISTS (SELECT 1 FROM linkway_stop_access lsa WHERE lsa.stop_code = ts.stop_code AND lsa.walk_distance_m <= 200) LIMIT 20;\""

echo ""
echo "================================================================="
echo "  hyperfine Benchmarks Complete! Saved to data/                  "
echo "================================================================="
