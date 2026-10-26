"""Router for benchmark telemetry and query execution comparisons."""

import json
import subprocess
import sys
from pathlib import Path
import time
from fastapi import APIRouter
from pydantic import BaseModel
from api.services.db import get_pg_connection

router = APIRouter(prefix="/api/benchmarks", tags=["Query Benchmarks"])
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RESULTS_FILE = ROOT_DIR / "data" / "benchmark_results.json"


@router.get("/")
def get_benchmark_matrix():
    """Retrieve execution times and speedups for the 5 optimization pairs."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)
            if isinstance(data, dict) and "pairs" in data:
                return data["pairs"]
            return data
    return [
        {"pair": 1, "name": "Unsheltered Bus Stops", "time_a": 14.33, "time_b": 8.03, "speedup": 1.78},
        {"pair": 2, "name": "Sheltered Interchanges", "time_a": 4.24, "time_b": 4.03, "speedup": 1.05},
        {"pair": 3, "name": "Peak Congestion Ranking", "time_a": 1.90, "time_b": 0.46, "speedup": 4.15},
        {"pair": 4, "name": "Proximity to Linkway", "time_a": 94.87, "time_b": 0.20, "speedup": 481.56},
        {"pair": 5, "name": "Multi-Hop Transit Route", "time_sql": 219.60, "time_neo4j": 22.18, "speedup": 9.90}
    ]

@router.get("/all")
def get_all_benchmarks():
    """Retrieve full benchmark payload including head-to-head experiments."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return {"pairs": get_benchmark_matrix(), "head_to_head": []}

class DurabilityTestRequest(BaseModel):
    mode: str = "async"  # "sync" or "async"
    batch_size: int = 500

@router.post("/durability_test")
def test_durability_mode(req: DurabilityTestRequest):
    """Test WAL commit latency and update throughput under synchronous_commit = ON vs OFF."""
    sync_val = "on" if req.mode == "sync" else "off"
    batch_size = max(50, min(2000, req.batch_size))

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stop_code FROM transit_stop LIMIT %s;", (batch_size,))
            stops = [r[0] for r in cur.fetchall()]
            levels = ["SEA", "SDA", "LSD"]
            stops_arr = [stops[i % len(stops)] for i in range(batch_size)]
            loads_arr = [levels[i % 3] for i in range(batch_size)]

            t0 = time.perf_counter()
            cur.execute(f"SET LOCAL synchronous_commit = {sync_val};")
            cur.execute(
                """
                UPDATE live_crowd_snapshot AS lcs
                SET load_level = v.load_level, recorded_at = CURRENT_TIMESTAMP
                FROM (SELECT unnest(%s::varchar[]) AS stop_code, unnest(%s::varchar[]) AS load_level) AS v
                WHERE lcs.stop_code = v.stop_code;
                """,
                (stops_arr, loads_arr)
            )
            conn.commit()
            t_diff = time.perf_counter() - t0

    dur_ms = round(t_diff * 1000.0, 2)
    tps = round(batch_size / max(0.0001, t_diff), 1)

    return {
        "mode": req.mode,
        "synchronous_commit": sync_val.upper(),
        "updates_count": batch_size,
        "duration_ms": dur_ms,
        "updates_per_sec": tps,
        "durability_level": "Strict ACID (RPO = 0, synchronous disk fsync)" if sync_val == "on" else "High Throughput (RPO ~ 200ms, OS pagecache WAL append)",
        "wal_mechanism": "Forces synchronous WAL flush to disk on COMMIT" if sync_val == "on" else "Returns before fsync; background writer flushes every 3x wal_writer_delay"
    }


@router.post("/run")
def run_live_benchmark():
    """Trigger the live EXPLAIN ANALYZE benchmark suite across SQL and NoSQL."""
    script_path = ROOT_DIR / "scripts" / "benchmark_queries.py"
    res = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    if res.returncode == 0 and RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            return {"status": "success", "results": json.load(f)}
    return {"status": "error", "error": res.stderr}
