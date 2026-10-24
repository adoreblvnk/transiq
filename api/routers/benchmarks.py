"""Router for benchmark telemetry and query execution comparisons."""

import json
from pathlib import Path
from fastapi import APIRouter
from api.services.db import get_pg_connection

router = APIRouter(prefix="/api/benchmarks", tags=["Query Benchmarks"])
RESULTS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark_results.json"


@router.get("/")
def get_benchmark_matrix():
    """Retrieve execution times and speedups for the 5 optimization pairs."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return [
        {"pair": 1, "name": "Unsheltered Bus Stops", "time_a": 10.01, "time_b": 8.65, "speedup": 1.2},
        {"pair": 2, "name": "Sheltered Interchanges", "time_a": 4.59, "time_b": 4.02, "speedup": 1.1},
        {"pair": 3, "name": "Peak Congestion Ranking", "time_a": 1.52, "time_b": 0.46, "speedup": 3.3},
        {"pair": 4, "name": "Proximity to Linkway", "time_a": 79.74, "time_b": 0.12, "speedup": 693.4},
        {"pair": 5, "name": "Multi-Hop Transit Route", "time_sql": 236.44, "time_neo4j": 84.01, "speedup": 2.8}
    ]
