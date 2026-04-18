"""Patient API routes — offline FHIR R4 patient record access."""

from fastapi import APIRouter, HTTPException

from backend.database import (
    get_patient_summary,
    get_resources_by_type,
    search_patients_by_name,
)

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("")
async def list_patients():
    """List all soldiers in the unit with summary info."""
    patients = get_resources_by_type("Patient")
    summaries = []
    for p in patients:
        pid = p["id"]
        summary = get_patient_summary(pid)
        if summary:
            summaries.append(summary)
    summaries.sort(key=lambda s: s.get("name", ""))
    return {"patients": summaries, "count": len(summaries)}


@router.get("/search")
async def search_patients(q: str):
    """Search patients by name (fuzzy match)."""
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    matches = search_patients_by_name(q)
    summaries = []
    for p in matches:
        summary = get_patient_summary(p["id"])
        if summary:
            summaries.append(summary)
    return {"patients": summaries, "count": len(summaries), "query": q}


@router.get("/{patient_id}")
async def get_patient(patient_id: str):
    """Get full patient summary including allergies, conditions, medications."""
    summary = get_patient_summary(patient_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return summary
