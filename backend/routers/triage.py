"""Triage API routes — TCCC MARCH-based injury prioritization."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from backend.database import get_patient_summary
from backend.services import llm_service
from backend.services.triage_engine import (
    prioritize_casualties,
    triage_casualty,
)

router = APIRouter(prefix="/api/triage", tags=["triage"])


class CasualtyInput(BaseModel):
    soldier_id: str
    injury_description: str
    injury_key: str | None = None


class TriageRequest(BaseModel):
    casualties: list[CasualtyInput]


@router.post("")
async def triage_casualties(request: TriageRequest):
    """Triage a list of casualties and return prioritized care queue."""
    results = []
    errors = []

    for cas in request.casualties:
        summary = get_patient_summary(cas.soldier_id)
        if not summary:
            errors.append({"soldier_id": cas.soldier_id, "error": "Patient not found"})
            continue

        raw_conds = summary.get("conditions", [])
        cond_names = [c["name"] if isinstance(c, dict) else c for c in raw_conds]

        result = triage_casualty(
            soldier_id=cas.soldier_id,
            soldier_name=summary["name"],
            rank=summary.get("rank", ""),
            blood_type=summary.get("blood_type", "Unknown"),
            injury_description=cas.injury_description,
            allergies=summary.get("allergies", []),
            conditions=cond_names,
            injury_key_override=cas.injury_key,
        )
        results.append(result)

    prioritized = prioritize_casualties(results)

    response_text = await llm_service.generate_response(prioritized)

    return {
        "triage_queue": [asdict(r) for r in prioritized],
        "response_text": response_text,
        "mode": llm_service.get_mode(),
        "errors": errors,
    }
