# ==============================================================================
# TRANSIQ — PostgreSQL Concurrency & Durability Benchmarks (PowerShell / Windows)
# ==============================================================================

$ContainerName = "transiq_postgres"
$DbUser = "transiq"
$DbName = "transiq_db"

Write-Host "================================================================="
Write-Host "  TRANSIQ pgbench Concurrency & Durability Benchmark Suite (Win) "
Write-Host "================================================================="

# Check container
$running = docker ps --format '{{.Names}}' | Select-String "^${ContainerName}$"
if (-not $running) {
    Write-Error "Error: $ContainerName is not running. Run 'docker compose up -d' first."
    exit 1
}

Write-Host ""
Write-Host "--- Test 1: Concurrent Materialized View Reads (Clients: 8, Threads: 4, 5s) ---"
docker exec -i $ContainerName bash -c "pgbench -U $DbUser $DbName -n -T 5 -c 8 -j 4 -f - << 'EOF'
SELECT count(*) FROM mv_sheltered_access WHERE postal_code = '640183';
EOF"

Write-Host ""
Write-Host "--- Test 2: Live Crowd Updates (synchronous_commit = ON) ---"
docker exec -i $ContainerName bash -c "pgbench -U $DbUser $DbName -n -T 5 -c 4 -j 2 -f - << 'EOF'
BEGIN;
SET LOCAL synchronous_commit = on;
UPDATE live_crowd_snapshot SET load_level = 'SDA', recorded_at = CURRENT_TIMESTAMP WHERE stop_code = '01012';
COMMIT;
EOF"

Write-Host ""
Write-Host "--- Test 3: High-Throughput Live Crowd Updates (synchronous_commit = OFF) ---"
docker exec -i $ContainerName bash -c "pgbench -U $DbUser $DbName -n -T 5 -c 4 -j 2 -f - << 'EOF'
BEGIN;
SET LOCAL synchronous_commit = off;
UPDATE live_crowd_snapshot SET load_level = 'SEA', recorded_at = CURRENT_TIMESTAMP WHERE stop_code = '01012';
COMMIT;
EOF"

Write-Host ""
Write-Host "================================================================="
Write-Host "  pgbench Benchmarks Completed!                                  "
Write-Host "================================================================="
