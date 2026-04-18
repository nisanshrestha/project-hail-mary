"""SQLite FHIR R4 JSON blob storage engine.

Stores FHIR resources as validated JSON in a single table with indexed
resource_type and subject_id columns for fast offline lookups.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "data" / "hailmary.db"


def _ensure_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables and indexes if they don't exist."""
    _ensure_dir()
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fhir_resources (
                id            TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                subject_id    TEXT,
                data          TEXT NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_resource_type
            ON fhir_resources(resource_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subject_id
            ON fhir_resources(subject_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_type_subject
            ON fhir_resources(resource_type, subject_id)
        """)


def upsert_resource(resource_id: str, resource_type: str, data: dict,
                    subject_id: str | None = None):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO fhir_resources (id, resource_type, subject_id, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                data = excluded.data,
                subject_id = excluded.subject_id
        """, (resource_id, resource_type, subject_id, json.dumps(data)))


def get_resource(resource_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data FROM fhir_resources WHERE id = ?", (resource_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None


def get_resources_by_type(resource_type: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT data FROM fhir_resources WHERE resource_type = ?",
            (resource_type,)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]


def get_resources_for_subject(subject_id: str,
                              resource_type: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if resource_type:
            rows = conn.execute(
                "SELECT data FROM fhir_resources "
                "WHERE subject_id = ? AND resource_type = ?",
                (subject_id, resource_type)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data FROM fhir_resources WHERE subject_id = ?",
                (subject_id,)
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]


def search_patients_by_name(query: str) -> list[dict]:
    """Fuzzy name search across Patient resources."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT data FROM fhir_resources WHERE resource_type = 'Patient'"
        ).fetchall()

    results = []
    query_lower = query.lower().strip()
    for row in rows:
        patient = json.loads(row["data"])
        names = patient.get("name", [])
        for name_obj in names:
            family = (name_obj.get("family") or "").lower()
            givens = [g.lower() for g in (name_obj.get("given") or [])]
            full = f"{' '.join(givens)} {family}"
            if (query_lower in family or
                    any(query_lower in g for g in givens) or
                    query_lower in full):
                results.append(patient)
                break
    return results


def _ext(patient: dict, url_fragment: str, key: str = "valueString") -> str | None:
    for ext in patient.get("extension", []):
        if url_fragment in ext.get("url", ""):
            return ext.get(key) or ext.get("valueString") or ext.get("valueDecimal")
    return None


def get_patient_summary(patient_id: str) -> dict[str, Any] | None:
    """Return a denormalized summary of a patient and all linked resources."""
    patient = get_resource(patient_id)
    if not patient:
        return None

    allergies = get_resources_for_subject(patient_id, "AllergyIntolerance")
    conditions = get_resources_for_subject(patient_id, "Condition")
    medications = get_resources_for_subject(patient_id, "MedicationStatement")
    observations = get_resources_for_subject(patient_id, "Observation")

    name_obj = (patient.get("name") or [{}])[0]
    given = " ".join(name_obj.get("given", []))
    family = name_obj.get("family", "")

    # Compute age from DOB
    age = None
    dob = patient.get("birthDate")
    if dob:
        from datetime import date
        try:
            born = date.fromisoformat(dob)
            today = date.today()
            age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        except ValueError:
            pass

    # Extract extensions
    blood_type = _ext(patient, "blood-type")
    rank = _ext(patient, "military-rank")
    mos = _ext(patient, "mos")
    last_deployment = _ext(patient, "last-deployment")
    tetanus_date = _ext(patient, "tetanus-date")
    height_cm = _ext(patient, "height-cm", "valueDecimal")
    weight_kg = _ext(patient, "weight-kg", "valueDecimal")

    # DoD ID from identifiers
    dod_id = None
    for ident in patient.get("identifier", []):
        if "10001.100001.12" in (ident.get("system") or ""):
            dod_id = ident.get("value")

    # Allergies with reaction details
    allergy_list = []
    for a in allergies:
        code_obj = a.get("code", {})
        codings = code_obj.get("coding", [])
        display = codings[0].get("display", "Unknown") if codings else code_obj.get("text", "Unknown")
        severity = "unknown"
        reaction_text = ""
        for reaction in a.get("reaction", []):
            severity = reaction.get("severity", severity)
            for manif in reaction.get("manifestation", []):
                for coding in manif.get("coding", []):
                    if coding.get("display"):
                        reaction_text = coding["display"]
        allergy_list.append({
            "substance": display,
            "severity": severity,
            "reaction": reaction_text,
        })

    # Conditions with clinical notes
    condition_list = []
    for c in conditions:
        code_obj = c.get("code", {})
        codings = code_obj.get("coding", [])
        display = codings[0].get("display", "Unknown") if codings else code_obj.get("text", "Unknown")
        note = ""
        for n in c.get("note", []):
            note = n.get("text", "")
        condition_list.append({"name": display, "note": note})

    # Medications
    med_list = []
    for m in medications:
        med_code = m.get("medicationCodeableConcept", {})
        codings = med_code.get("coding", [])
        display = codings[0].get("display", "Unknown") if codings else med_code.get("text", "Unknown")
        med_list.append(display)

    # Baseline vitals from Observations
    vitals = {}
    vital_map = {
        "8867-4": "hr",
        "8480-6": "bp_sys",
        "8462-4": "bp_dia",
        "9279-1": "rr",
        "2708-6": "spo2",
        "8310-5": "temp",
    }
    for obs in observations:
        for coding in obs.get("code", {}).get("coding", []):
            loinc = coding.get("code", "")
            if loinc in vital_map:
                vq = obs.get("valueQuantity", {})
                vitals[vital_map[loinc]] = {
                    "value": vq.get("value"),
                    "unit": vq.get("unit", ""),
                    "display": coding.get("display", ""),
                }

    gender = patient.get("gender", "unknown")

    return {
        "id": patient_id,
        "name": f"{given} {family}".strip(),
        "rank": rank,
        "gender": gender,
        "age": age,
        "dob": dob,
        "dod_id": dod_id,
        "blood_type": blood_type,
        "mos": mos,
        "last_deployment": last_deployment,
        "tetanus_date": tetanus_date,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "allergies": allergy_list,
        "conditions": condition_list,
        "medications": med_list,
        "vitals": vitals,
        "fhir_patient": patient,
    }


def is_seeded() -> bool:
    if not DB_PATH.exists():
        return False
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM fhir_resources WHERE resource_type = 'Patient'"
        ).fetchone()
        return row["cnt"] >= 12
