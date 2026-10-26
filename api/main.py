"""
TRANSIQ — FastAPI Application Entrypoint
Exposes REST endpoints for multi-modal routing, commuter profiles,
analytical views, and database optimization benchmarks.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from api.routers import routes, profiles, analytics, benchmarks

ROOT_DIR = Path(__file__).resolve().parent.parent

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

# Mount modular frontend asset directories
app.mount("/css", StaticFiles(directory=ROOT_DIR / "frontend" / "css"), name="css")
app.mount("/js", StaticFiles(directory=ROOT_DIR / "frontend" / "js"), name="js")


@app.get("/health")
def health_check():
    return {"status": "online", "system": "TRANSIQ Dual-Database Engine"}


@app.get("/")
@app.get("/index.html")
def serve_index():
    frontend_path = ROOT_DIR / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return FileResponse(ROOT_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
