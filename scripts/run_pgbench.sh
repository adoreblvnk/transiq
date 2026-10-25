#!/usr/bin/env bash
# ==============================================================================
# TRANSIQ — PostgreSQL Concurrency & Durability Benchmarks via pgbench
# Evaluates:
# 1. High-concurrency read throughput on mv_sheltered_access (Materialized View)
# 2. Transactional live crowd updates under synchronous_commit = ON vs OFF
# ==============================================================================

set -euo pipefail

CONTAINER_NAME="transiq_postgres"
DB_USER="transiq"
DB_NAME="transiq_db"

echo "================================================================="
echo "  TRANSIQ pgbench Concurrency & Durability Benchmark Suite       "
echo "================================================================="

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: ${CONTAINER_NAME} is not running! Run 'docker compose up -d' first."
    exit 1
fi

# ------------------------------------------------------------------------------
# Test 1: High-Concurrency Read Throughput (Materialized View mv_sheltered_access)
# ------------------------------------------------------------------------------
echo ""
echo "--- Test 1: Concurrent Materialized View Reads (Clients: 8, Threads: 4, Duration: 5s) ---"
docker exec -i "${CONTAINER_NAME}" pgbench -U "${DB_USER}" "${DB_NAME}" -n -T 5 -c 8 -j 4 -f - << 'EOF'
SELECT count(*) FROM mv_sheltered_access WHERE postal_code = '640183';
EOF

# ------------------------------------------------------------------------------
# Test 2: Live Crowd Updates under synchronous_commit = ON (Strict Durability)
# ------------------------------------------------------------------------------
echo ""
echo "--- Test 2: Live Crowd Update Transactions (synchronous_commit = ON) ---"
docker exec -i "${CONTAINER_NAME}" pgbench -U "${DB_USER}" "${DB_NAME}" -n -T 5 -c 4 -j 2 -f - << 'EOF'
BEGIN;
SET LOCAL synchronous_commit = on;
UPDATE live_crowd_snapshot
SET load_level = 'SDA', recorded_at = CURRENT_TIMESTAMP
WHERE stop_code = '01012';
COMMIT;
EOF

# ------------------------------------------------------------------------------
# Test 3: Live Crowd Updates under synchronous_commit = OFF (Asynchronous Commit)
# ------------------------------------------------------------------------------
echo ""
echo "--- Test 3: High-Throughput Live Crowd Updates (synchronous_commit = OFF) ---"
docker exec -i "${CONTAINER_NAME}" pgbench -U "${DB_USER}" "${DB_NAME}" -n -T 5 -c 4 -j 2 -f - << 'EOF'
BEGIN;
SET LOCAL synchronous_commit = off;
UPDATE live_crowd_snapshot
SET load_level = 'SEA', recorded_at = CURRENT_TIMESTAMP
WHERE stop_code = '01012';
COMMIT;
EOF

echo ""
echo "================================================================="
echo "  pgbench Concurrency & Durability Benchmarks Completed!        "
echo "================================================================="
