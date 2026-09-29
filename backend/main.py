"""FastAPI application: serves the API under /api and the built frontend at /.

Run with: uv run uvicorn backend.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Urban Green Planner API", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Mounted last so /api routes take precedence. One origin means a single ngrok tunnel for the demo.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
