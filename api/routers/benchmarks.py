"""Router for benchmark telemetry and query execution comparisons."""

import json
import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter
from api.services.db import get_pg_connection

router = APIRouter(prefix="/api/benchmarks", tags=["Query Benchmarks"])
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RESULTS_FILE = ROOT_DIR / "data" / "benchmark_results.json"


@router.get("/")
def get_benchmark_matrix():
    """Retrieve execution times and speedups for the 5 optimization pairs."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return [
        {"pair": 1, "name": "Unsheltered Bus Stops", "time_a": 14.33, "time_b": 8.03, "speedup": 1.78},
        {"pair": 2, "name": "Sheltered Interchanges", "time_a": 4.24, "time_b": 4.03, "speedup": 1.05},
        {"pair": 3, "name": "Peak Congestion Ranking", "time_a": 1.90, "time_b": 0.46, "speedup": 4.15},
        {"pair": 4, "name": "Proximity to Linkway", "time_a": 94.87, "time_b": 0.20, "speedup": 481.56},
        {"pair": 5, "name": "Multi-Hop Transit Route", "time_sql": 219.60, "time_neo4j": 22.18, "speedup": 9.90}
    ]


@router.post("/run")
def run_live_benchmark():
    """Trigger the live EXPLAIN ANALYZE benchmark suite across SQL and NoSQL."""
    script_path = ROOT_DIR / "scripts" / "benchmark_queries.py"
    res = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    if res.returncode == 0 and RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            return {"status": "success", "results": json.load(f)}
    return {"status": "error", "error": res.stderr}
