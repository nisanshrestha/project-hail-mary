"""Project Hail Mary — Combat Medic FHIR Assistant.

FastAPI application serving the offline triage backend and tactical frontend.
Run with: python -m backend.main
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import get_patient_summary, get_resources_by_type, init_db
from backend.routers import patients, triage, voice
from backend.seed_data import seed
from backend.services import denoiser_service, elevenlabs_service, llm_service

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== PROJECT HAIL MARY — Starting Up ===")

    init_db()
    seed()
    logger.info("Database initialized and seeded")

    denoiser_service.init()
    elevenlabs_service.init()
    llm_service.init()

    all_patients = get_resources_by_type("Patient")
    roster = []
    for p in all_patients:
        summary = get_patient_summary(p["id"])
        if summary:
            roster.append(summary)
    voice.set_soldier_roster(roster)
    logger.info("Loaded roster of %d soldiers", len(roster))

    unit_name = os.getenv("UNIT_NAME", "1st Platoon Alpha Co")
    llm_label = llm_service.get_llm_backend() or "off"
    logger.info("Unit: %s | AI Mode: %s | LLM: %s", unit_name, llm_service.get_mode(), llm_label)
    logger.info("Denoiser: %s | ElevenLabs: %s (Isolation: %s) | AI ready: %s",
                "ON" if denoiser_service.is_available() else "OFF",
                "ON" if elevenlabs_service.is_available() else "OFF",
                "ON" if elevenlabs_service.is_isolation_enabled() else "OFF",
                "ON" if llm_service.is_ai_available() else "OFF")
    logger.info("=== READY — Open http://localhost:8000 ===")

    yield

    logger.info("=== Shutting down ===")


app = FastAPI(
    title="Project Hail Mary",
    description="Combat Medic FHIR Assistant with TCCC Triage",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(triage.router)
app.include_router(voice.router)


@app.get("/api/mode")
async def get_mode():
    return {
        "mode": llm_service.get_mode(),
        "ai_available": llm_service.is_ai_available(),
        "llm_backend": llm_service.get_llm_backend(),
        "denoiser_available": denoiser_service.is_available(),
        "elevenlabs_available": elevenlabs_service.is_available(),
        "isolation_enabled": elevenlabs_service.is_isolation_enabled(),
        "unit_name": os.getenv("UNIT_NAME", "1st Platoon Alpha Co"),
    }


@app.post("/api/mode")
async def set_mode(body: dict):
    new_mode = body.get("mode", "rules")
    actual = llm_service.set_mode(new_mode)

    if "isolation" in body:
        elevenlabs_service.set_isolation_enabled(body["isolation"])

    return {
        "mode": actual,
        "ai_available": llm_service.is_ai_available(),
        "llm_backend": llm_service.get_llm_backend(),
        "isolation_enabled": elevenlabs_service.is_isolation_enabled(),
    }


@app.get("/api/scenarios")
async def get_scenarios():
    import json
    scenarios_file = Path(__file__).parent.parent / "demo" / "scenarios.json"
    if scenarios_file.exists():
        return json.loads(scenarios_file.read_text())
    return []


FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],
    )
