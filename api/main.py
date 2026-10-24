"""
TRANSIQ — FastAPI Application Entrypoint
Exposes REST endpoints for multi-modal routing, commuter profiles,
analytical views, and database optimization benchmarks.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import routes, profiles, analytics, benchmarks

app = FastAPI(
    title="TRANSIQ API",
    description="Door-to-door sheltered transit routing engine using PostgreSQL+PostGIS & Neo4j",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)
app.include_router(profiles.router)
app.include_router(analytics.router)
app.include_router(benchmarks.router)


@app.get("/health")
def health_check():
    return {"status": "online", "system": "TRANSIQ Dual-Database Engine"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
