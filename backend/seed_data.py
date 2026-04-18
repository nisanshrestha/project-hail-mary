"""Seed the SQLite database with 12 mock soldiers as FHIR R4 resources.

Each soldier gets: Patient, AllergyIntolerance (if applicable),
Condition (if applicable), MedicationStatement (if applicable),
and baseline Observation resources.
"""

import uuid
from backend.database import init_db, upsert_resource, is_seeded

SOLDIERS = [
    {
        "id": "soldier-001", "rank": "SGT", "given": "James", "family": "Morrison",
        "dob": "1994-03-15", "gender": "male", "blood_type": "O+",
        "dod_id": "1234567890", "mos": "11B — Infantryman",
        "height_cm": 183, "weight_kg": 88,
        "last_deployment": "OIR — Syria, 2024",
        "tetanus_date": "2023-06-10",
        "baseline_vitals": {"hr": 68, "bp_sys": 122, "bp_dia": 78, "rr": 14, "spo2": 99, "temp": 36.7},
        "allergies": [],
        "conditions": [
            {"code": "127295002", "display": "Traumatic brain injury", "note": "Prior TBI sustained 2023 via IED blast, fully recovered, cleared for duty Jan 2024"}
        ],
        "medications": [],
    },
    {
        "id": "soldier-002", "rank": "CPL", "given": "Maria", "family": "Santos",
        "dob": "1997-08-22", "gender": "female", "blood_type": "A+",
        "dod_id": "2345678901", "mos": "68W — Combat Medic",
        "height_cm": 165, "weight_kg": 62,
        "last_deployment": "OFS — Afghanistan, 2023",
        "tetanus_date": "2022-11-15",
        "baseline_vitals": {"hr": 74, "bp_sys": 118, "bp_dia": 72, "rr": 16, "spo2": 98, "temp": 36.6},
        "allergies": [
            {"code": "764146007", "display": "Penicillin", "severity": "severe",
             "reaction": "Anaphylaxis — throat swelling, hypotension, requires epinephrine"}
        ],
        "conditions": [
            {"code": "195967001", "display": "Asthma", "note": "Exercise-induced, carries albuterol inhaler, last exacerbation Feb 2024"}
        ],
        "medications": [
            {"code": "372897005", "display": "Albuterol inhaler PRN"}
        ],
    },
    {
        "id": "soldier-003", "rank": "PFC", "given": "David", "family": "Kim",
        "dob": "1999-01-10", "gender": "male", "blood_type": "B+",
        "dod_id": "3456789012", "mos": "25U — Signal Support",
        "height_cm": 175, "weight_kg": 82,
        "last_deployment": "None — first deployment",
        "tetanus_date": "2024-01-20",
        "baseline_vitals": {"hr": 78, "bp_sys": 130, "bp_dia": 84, "rr": 16, "spo2": 97, "temp": 36.8},
        "allergies": [
            {"code": "387170002", "display": "Sulfonamide", "severity": "moderate",
             "reaction": "Diffuse skin rash, urticaria — develops within 2hrs of exposure"}
        ],
        "conditions": [
            {"code": "44054006", "display": "Type 2 diabetes mellitus", "note": "Controlled with metformin, last A1C 6.8, finger-stick glucose monitoring q12h"}
        ],
        "medications": [
            {"code": "372567009", "display": "Metformin 500mg PO BID"}
        ],
    },
    {
        "id": "soldier-004", "rank": "SSG", "given": "Rachel", "family": "Torres",
        "dob": "1991-11-03", "gender": "female", "blood_type": "O-",
        "dod_id": "4567890123", "mos": "11B — Infantryman",
        "height_cm": 170, "weight_kg": 68,
        "last_deployment": "OIR — Iraq, 2023",
        "tetanus_date": "2021-09-05",
        "baseline_vitals": {"hr": 64, "bp_sys": 116, "bp_dia": 70, "rr": 14, "spo2": 99, "temp": 36.5},
        "allergies": [],
        "conditions": [
            {"code": "239720000", "display": "ACL reconstruction", "note": "Right knee ACL repair Aug 2021, full return to duty, no functional limitation, wears knee brace during ruck marches"}
        ],
        "medications": [],
    },
    {
        "id": "soldier-005", "rank": "SPC", "given": "Marcus", "family": "Williams",
        "dob": "1998-06-30", "gender": "male", "blood_type": "AB+",
        "dod_id": "5678901234", "mos": "12B — Combat Engineer",
        "height_cm": 188, "weight_kg": 95,
        "last_deployment": "OIR — Syria, 2024",
        "tetanus_date": "2024-03-10",
        "baseline_vitals": {"hr": 70, "bp_sys": 126, "bp_dia": 80, "rr": 15, "spo2": 98, "temp": 36.6},
        "allergies": [
            {"code": "372756006", "display": "NSAID - Non-steroidal anti-inflammatory drug",
             "severity": "moderate", "reaction": "Upper GI bleeding — hospitalized 2022, avoid ibuprofen/naproxen/ketorolac"}
        ],
        "conditions": [],
        "medications": [],
    },
    {
        "id": "soldier-006", "rank": "CPT", "given": "Elena", "family": "Volkov",
        "dob": "1989-04-18", "gender": "female", "blood_type": "A-",
        "dod_id": "6789012345", "mos": "11A — Infantry Officer",
        "height_cm": 173, "weight_kg": 66,
        "last_deployment": "OFS — Afghanistan, 2022",
        "tetanus_date": "2023-02-14",
        "baseline_vitals": {"hr": 62, "bp_sys": 114, "bp_dia": 68, "rr": 13, "spo2": 99, "temp": 36.4},
        "allergies": [
            {"code": "373529000", "display": "Morphine", "severity": "severe",
             "reaction": "Respiratory depression and urticaria — documented ICU admission 2019, use ketamine for analgesia"}
        ],
        "conditions": [],
        "medications": [],
    },
    {
        "id": "soldier-007", "rank": "SPC", "given": "Aiden", "family": "O'Brien",
        "dob": "1996-12-05", "gender": "male", "blood_type": "B-",
        "dod_id": "7890123456", "mos": "19D — Cavalry Scout",
        "height_cm": 180, "weight_kg": 84,
        "last_deployment": "OIR — Iraq, 2024",
        "tetanus_date": "2024-05-01",
        "baseline_vitals": {"hr": 72, "bp_sys": 120, "bp_dia": 76, "rr": 15, "spo2": 98, "temp": 36.7},
        "allergies": [
            {"code": "111088007", "display": "Latex", "severity": "moderate",
             "reaction": "Contact dermatitis progressing to bronchospasm — USE NITRILE GLOVES ONLY"}
        ],
        "conditions": [],
        "medications": [],
    },
    {
        "id": "soldier-008", "rank": "SGT", "given": "Priya", "family": "Nair",
        "dob": "1995-09-14", "gender": "female", "blood_type": "O+",
        "dod_id": "8901234567", "mos": "35F — Intelligence Analyst",
        "height_cm": 163, "weight_kg": 58,
        "last_deployment": "OIR — Syria, 2024",
        "tetanus_date": "2023-08-20",
        "baseline_vitals": {"hr": 76, "bp_sys": 112, "bp_dia": 70, "rr": 16, "spo2": 99, "temp": 36.5},
        "allergies": [],
        "conditions": [
            {"code": "86859003", "display": "G6PD deficiency",
             "note": "Confirmed via enzyme assay. AVOID: primaquine, dapsone, rasburicase, methylene blue, high-dose vitamin C. Hemolytic crisis risk."}
        ],
        "medications": [],
    },
    {
        "id": "soldier-009", "rank": "CW2", "given": "Thomas", "family": "Blake",
        "dob": "1988-02-28", "gender": "male", "blood_type": "AB-",
        "dod_id": "9012345678", "mos": "153A — Rotary Wing Aviator",
        "height_cm": 178, "weight_kg": 80,
        "last_deployment": "OFS — Afghanistan, 2021",
        "tetanus_date": "2022-04-12",
        "baseline_vitals": {"hr": 66, "bp_sys": 128, "bp_dia": 82, "rr": 14, "spo2": 98, "temp": 36.6},
        "allergies": [
            {"code": "387494007", "display": "Codeine", "severity": "moderate",
             "reaction": "Severe nausea, confusion, and diaphoresis — avoid all codeine-containing compounds"}
        ],
        "conditions": [
            {"code": "47505003", "display": "Post-traumatic stress disorder",
             "note": "Diagnosed 2022 post-deployment, managed with sertraline. Behavioral health cleared for duty. Avoid tramadol (serotonin syndrome risk with sertraline)."}
        ],
        "medications": [
            {"code": "372594008", "display": "Sertraline 100mg PO daily"}
        ],
    },
    {
        "id": "soldier-010", "rank": "PFC", "given": "Juan", "family": "Ortega",
        "dob": "2000-07-21", "gender": "male", "blood_type": "A+",
        "dod_id": "0123456789", "mos": "11B — Infantryman",
        "height_cm": 172, "weight_kg": 76,
        "last_deployment": "None — first deployment",
        "tetanus_date": "2024-06-15",
        "baseline_vitals": {"hr": 74, "bp_sys": 118, "bp_dia": 74, "rr": 16, "spo2": 99, "temp": 36.6},
        "allergies": [
            {"code": "372809001", "display": "Tetracycline", "severity": "mild",
             "reaction": "Photosensitivity and GI upset — can use doxycycline with caution if no alternative"}
        ],
        "conditions": [],
        "medications": [],
    },
    {
        "id": "soldier-011", "rank": "SSG", "given": "Yuki", "family": "Tanaka",
        "dob": "1993-05-09", "gender": "male", "blood_type": "O+",
        "dod_id": "1122334455", "mos": "18D — Special Forces Medical Sergeant",
        "height_cm": 176, "weight_kg": 82,
        "last_deployment": "ODA 5133 — Niger, 2023",
        "tetanus_date": "2023-11-01",
        "baseline_vitals": {"hr": 58, "bp_sys": 118, "bp_dia": 72, "rr": 12, "spo2": 99, "temp": 36.5},
        "allergies": [],
        "conditions": [
            {"code": "36118008", "display": "Pneumothorax",
             "note": "Prior left-sided spontaneous pneumothorax 2020, resolved with chest tube drainage. HIGH RISK of recurrence on left side — low threshold for needle decompression."}
        ],
        "medications": [],
    },
    {
        "id": "soldier-012", "rank": "LT", "given": "Chris", "family": "Hawkins",
        "dob": "1992-10-12", "gender": "male", "blood_type": "B+",
        "dod_id": "2233445566", "mos": "11A — Infantry Officer",
        "height_cm": 185, "weight_kg": 90,
        "last_deployment": "OIR — Iraq, 2024",
        "tetanus_date": "2024-02-28",
        "baseline_vitals": {"hr": 66, "bp_sys": 124, "bp_dia": 78, "rr": 14, "spo2": 98, "temp": 36.7},
        "allergies": [
            {"code": "387458008", "display": "Aspirin", "severity": "moderate",
             "reaction": "Bronchospasm and angioedema — onset within 30min, requires bronchodilator"}
        ],
        "conditions": [],
        "medications": [],
    },
]


def _make_patient(s: dict) -> dict:
    return {
        "resourceType": "Patient",
        "id": s["id"],
        "identifier": [
            {
                "system": "urn:oid:2.16.840.1.113883.3.42.10001.100001.12",
                "value": s["dod_id"],
            }
        ],
        "name": [{"family": s["family"], "given": [s["given"]]}],
        "gender": s["gender"],
        "birthDate": s["dob"],
        "extension": [
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/blood-type",
                "valueString": s["blood_type"],
            },
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/military-rank",
                "valueString": s["rank"],
            },
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/mos",
                "valueString": s.get("mos", ""),
            },
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/last-deployment",
                "valueString": s.get("last_deployment", ""),
            },
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/height-cm",
                "valueDecimal": s.get("height_cm", 0),
            },
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/weight-kg",
                "valueDecimal": s.get("weight_kg", 0),
            },
            {
                "url": "http://hl7.org/fhir/us/military/StructureDefinition/tetanus-date",
                "valueString": s.get("tetanus_date", ""),
            },
        ],
    }


def _make_allergy(soldier_id: str, allergy: dict) -> dict:
    rid = f"allergy-{soldier_id}-{uuid.uuid4().hex[:8]}"
    resource = {
        "resourceType": "AllergyIntolerance",
        "id": rid,
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                         "code": "active"}]
        },
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                         "code": "confirmed"}]
        },
        "type": "allergy",
        "category": ["medication"],
        "criticality": "high" if allergy["severity"] == "severe" else "low",
        "code": {
            "coding": [{"system": "http://snomed.info/sct",
                         "code": allergy["code"],
                         "display": allergy["display"]}]
        },
        "patient": {"reference": f"Patient/{soldier_id}"},
        "reaction": [
            {
                "manifestation": [{"coding": [{"display": allergy["reaction"]}]}],
                "severity": allergy["severity"],
            }
        ],
    }
    return resource


def _make_condition(soldier_id: str, cond: dict) -> dict:
    rid = f"condition-{soldier_id}-{uuid.uuid4().hex[:8]}"
    return {
        "resourceType": "Condition",
        "id": rid,
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                         "code": "active"}]
        },
        "code": {
            "coding": [{"system": "http://snomed.info/sct",
                         "code": cond["code"],
                         "display": cond["display"]}],
            "text": cond["display"],
        },
        "subject": {"reference": f"Patient/{soldier_id}"},
        "note": [{"text": cond.get("note", "")}] if cond.get("note") else [],
    }


def _make_medication(soldier_id: str, med: dict) -> dict:
    rid = f"medstmt-{soldier_id}-{uuid.uuid4().hex[:8]}"
    return {
        "resourceType": "MedicationStatement",
        "id": rid,
        "status": "active",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://snomed.info/sct",
                         "code": med["code"],
                         "display": med["display"]}],
            "text": med["display"],
        },
        "subject": {"reference": f"Patient/{soldier_id}"},
    }


def _make_baseline_vitals(soldier_id: str, bv: dict | None = None) -> list[dict]:
    """Generate baseline vital sign Observations from per-soldier data."""
    bv = bv or {}
    vitals = [
        ("vital-hr", "8867-4", "Heart rate", str(bv.get("hr", 72)), "beats/minute"),
        ("vital-bp-sys", "8480-6", "Systolic blood pressure", str(bv.get("bp_sys", 120)), "mmHg"),
        ("vital-bp-dia", "8462-4", "Diastolic blood pressure", str(bv.get("bp_dia", 80)), "mmHg"),
        ("vital-rr", "9279-1", "Respiratory rate", str(bv.get("rr", 16)), "breaths/minute"),
        ("vital-spo2", "2708-6", "Oxygen saturation", str(bv.get("spo2", 98)), "%"),
        ("vital-temp", "8310-5", "Body temperature", str(bv.get("temp", 36.6)), "°C"),
    ]
    resources = []
    for suffix, loinc, display, value, unit in vitals:
        rid = f"{suffix}-{soldier_id}"
        resources.append({
            "resourceType": "Observation",
            "id": rid,
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                       "code": "vital-signs"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]},
            "subject": {"reference": f"Patient/{soldier_id}"},
            "valueQuantity": {"value": float(value), "unit": unit,
                              "system": "http://unitsofmeasure.org"},
        })
    return resources


def seed():
    """Seed the database with all 12 soldiers and their FHIR resources."""
    init_db()
    if is_seeded():
        return

    for s in SOLDIERS:
        sid = s["id"]

        patient = _make_patient(s)
        upsert_resource(sid, "Patient", patient)

        for allergy in s["allergies"]:
            res = _make_allergy(sid, allergy)
            upsert_resource(res["id"], "AllergyIntolerance", res, subject_id=sid)

        for cond in s["conditions"]:
            res = _make_condition(sid, cond)
            upsert_resource(res["id"], "Condition", res, subject_id=sid)

        for med in s["medications"]:
            res = _make_medication(sid, med)
            upsert_resource(res["id"], "MedicationStatement", res, subject_id=sid)

        for obs in _make_baseline_vitals(sid, s.get("baseline_vitals")):
            upsert_resource(obs["id"], "Observation", obs, subject_id=sid)


if __name__ == "__main__":
    seed()
    print("Database seeded with 12 soldiers.")
